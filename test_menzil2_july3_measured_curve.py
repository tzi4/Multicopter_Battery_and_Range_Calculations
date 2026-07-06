from pathlib import Path
import math

import pytest

import menzil2


def _firfir_context():
    profile = menzil2.build_speed_model_profile("1", 12.4, 4, 29.0, 450.0)
    hover_power_w = (
        menzil2.get_power_from_thrust(12400.0 / 4.0, menzil2.u8lite_kv190_g29_data)
        * 4.0
    )
    battery_wh = menzil2.calculate_real_energy_wh(12, 27000, "liion")
    correction_factor = 0.72
    sonuc = menzil2.BauersfeldMenzilHesaplayici(
        hover_power_w,
        correction_factor,
        battery_wh,
        profile["mass_kg"],
        450.0,
        profile["prop_diameter_inch"],
        profile["num_rotors"],
    ).solve()
    return profile, sonuc, hover_power_w, battery_wh, correction_factor


def _july3_root():
    roots = [
        path for path in Path.cwd().iterdir()
        if path.is_dir() and path.name.startswith("3 Temmuz")
    ]
    assert roots
    return roots[0]


def test_july3_measured_curve_builds_sync_battery_and_model_reports():
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()

    result = menzil2.run_datalink_measured_curve_analysis(
        profile,
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        log_root=_july3_root(),
        date_hint="260703",
        make_graph=False,
    )

    accepted = [row for row in result["sync_report"] if row["accepted_for_fit"]]
    assert result["fit_mode"] == "measured_datalink_power_curve"
    assert result["joined_sample_count"] > 40000
    assert len(accepted) == 2
    assert {row["bin"] for row in accepted} == {"00000076.BIN", "00000077.BIN"}
    assert all(row["timestamp_mode"] == "filename_trt" for row in accepted)
    assert any(
        row["timestamp_mode"] == "filename_utc" and not row["accepted_for_fit"]
        for row in result["sync_report"]
    )

    assert 700.0 <= result["measured_hover_power_w"] <= 820.0
    assert 170.0 <= result["utip_ms"] <= 180.0
    observations = result["speed_bin_observations"]
    assert len([obs for obs in observations if 2.0 <= obs["speed_ms"] <= 12.5]) >= 8
    assert all(obs["power_ratio"] > 0.0 for obs in observations)
    assert all(obs["stable_fraction"] >= 0.5 for obs in observations)
    assert all(obs["sample_count"] >= 80 for obs in observations)
    assert all(obs["raw_sample_count"] >= obs["sample_count"] for obs in observations)
    assert all(obs["source_bins"] for obs in observations)
    assert all(obs["source_sessions"] for obs in observations)
    assert all(obs["dt_s_max"] <= 0.35 for obs in observations)
    assert any(obs["extrapolation_region"] == "measured" for obs in observations)

    empirical_curve = result["empirical_curve"]
    assert empirical_curve["kind"] == "datalink_empirical_pv"
    assert empirical_curve["min_speed_ms"] < 3.0
    assert empirical_curve["max_speed_ms"] < 13.0
    assert empirical_curve["raw_sample_count_total"] >= empirical_curve["sample_count_total"]
    in_range = menzil2.evaluate_empirical_datalink_power_ratio(empirical_curve, 6.0)
    assert in_range["available"] is True
    assert in_range["basis"] in {"measured_bin", "linear_interpolation"}
    out_of_range = menzil2.evaluate_empirical_datalink_power_ratio(empirical_curve, 20.0)
    assert out_of_range["available"] is False
    assert out_of_range["reason"] == "out_of_measured_range"

    battery_qc = result["battery_qc_report"]
    assert battery_qc["bat_rows"] > 20000
    assert battery_qc["direct_current_fit_enabled"] is False
    assert any("battery_current_scale_suspect" in warning for warning in battery_qc["warnings"])
    assert battery_qc["datalink_energy_wh"] > 400.0

    residuals = result["model_fit_residuals"]
    assert {"zeng_measured_fit", "faessler_measured_fit", "kirschstein_measured_fit"} <= set(residuals)
    assert result["fit_audit"]["fit_family"] == "diagnostic_surrogate_fits"
    assert result["fit_audit"]["models"]["faessler_measured_fit"]["params"]["lambda_source"] == "attitude_log"
    for rows in residuals.values():
        assert rows
        assert all(math.isfinite(row["error"]) for row in rows)


def test_july3_battery_monitor_is_voltage_sanity_not_direct_power_fit():
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()

    result = menzil2.run_datalink_measured_curve_analysis(
        profile,
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        log_root=_july3_root(),
        date_hint="260703",
        make_graph=False,
    )

    battery_qc = result["battery_qc_report"]
    assert battery_qc["voltr_start_v"] > battery_qc["voltr_end_v"]
    assert battery_qc["battery_energy_delta_raw"] < 1.0
    assert battery_qc["datalink_energy_wh"] > 100.0 * battery_qc["battery_energy_delta_raw"]
    assert battery_qc["direct_current_fit_enabled"] is False


def test_datalink_flight_time_uses_july3_6s_usable_capacity_not_legacy_cf():
    legacy_battery_wh = menzil2.calculate_real_energy_wh(12, 27000, "liion")
    battery_basis = menzil2.build_july3_firfir_battery_basis()

    row = menzil2.calculate_flight_for_speed(
        0.1,
        1.0,
        757.891,
        legacy_battery_wh,
        0.72,
        battery_basis=battery_basis,
    )

    legacy_time_10_min = legacy_battery_wh / 757.891 * 60.0 * 0.72 * 1.125
    assert legacy_time_10_min > 75.0
    assert row["time_10_min"] == pytest.approx(39.86, abs=0.05)
    assert row["time_20_min"] == pytest.approx(35.43, abs=0.05)
    assert row["battery_basis_label"].startswith("6S 25.2Ah")


def test_datalink_fit_suite_reports_july3_battery_basis(monkeypatch):
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()

    fake_result = {
        "empirical_curve": {"measured_points": []},
        "speed_bin_observations": [],
        "power_reference_w": 757.891,
        "measured_hover_power_w": 757.891,
        "utip_ms": 174.0,
        "model_profile": profile,
        "model_functions": {
            "zeng_measured_fit": lambda v: 1.0,
            "faessler_measured_fit": lambda v: 1.0,
            "kirschstein_measured_fit": lambda v: 1.0,
        },
        "model_params": {
            "zeng_measured_fit": {},
            "faessler_measured_fit": {},
            "kirschstein_measured_fit": {},
        },
        "fit_audit": {"models": {}},
        "battery_qc_report": {},
        "sync_report": [],
    }
    monkeypatch.setattr(
        menzil2,
        "run_datalink_measured_curve_analysis",
        lambda *_args, **_kwargs: fake_result,
    )

    suite = menzil2.build_datalink_fitted_model_suite(
        profile,
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
    )

    reserve = suite["battery_reserve_report"]
    assert suite["battery_basis"]["usable_energy_wh"] == pytest.approx(559.44, abs=0.01)
    assert reserve["hover_10_reserve_min"] == pytest.approx(39.86, abs=0.05)
    assert reserve["hover_20_reserve_min"] == pytest.approx(35.43, abs=0.05)
    assert reserve["legacy_hover_10_reserve_min"] > 75.0


def test_empirical_datalink_curve_refuses_extrapolation_and_reports_sources():
    observations = [
        {
            "label": "DataLink v~5.0",
            "speed_ms": 5.0,
            "power_ratio": 0.92,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
        {
            "label": "DataLink v~7.0",
            "speed_ms": 7.0,
            "power_ratio": 0.98,
            "sample_count": 200,
            "raw_sample_count": 220,
            "stable_fraction": 0.91,
            "source_bins": ["00000076.BIN", "00000077.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.22,
            "extrapolation_region": "measured",
        },
        {
            "label": "DataLink v~18.0",
            "speed_ms": 18.0,
            "power_ratio": 1.4,
            "sample_count": 30,
            "raw_sample_count": 60,
            "stable_fraction": 0.5,
            "source_bins": ["00000077.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.3,
            "extrapolation_region": "extrapolation",
        },
    ]

    curve = menzil2.build_empirical_datalink_power_curve(observations)

    assert curve["min_speed_ms"] == 5.0
    assert curve["max_speed_ms"] == 7.0
    assert curve["sample_count_total"] == 320
    assert curve["source_bins"] == ["00000076.BIN", "00000077.BIN"]
    assert menzil2.evaluate_empirical_datalink_power_ratio(curve, 6.0)["power_ratio"] == 0.95
    assert menzil2.evaluate_empirical_datalink_power_ratio(curve, 4.0)["available"] is False
    assert menzil2.evaluate_empirical_datalink_power_ratio(curve, 18.0)["available"] is False


def test_scientific_fit_audit_rejects_unphysical_free_parameters():
    audit = menzil2.audit_scientific_fit_parameters(
        "bad_fit",
        {
            "lambda_n_per_ms": -0.2,
            "lambda_source": "attitude_log",
            "utip_ms": 260.0,
            "utip_source": "fitted",
            "body_cd_fit": 12.0,
        },
    )

    assert audit["status"] == "rejected"
    assert "negative_lambda" in audit["reasons"]
    assert "utip_must_not_be_fitted" in audit["reasons"]
    assert "body_cd_unphysical" in audit["reasons"]


def test_datalink_empirical_pv_is_available_from_custom_speed_model_selection():
    assert menzil2.parse_datalink_model_selection("1") == ["zeng_datalink_fit"]
    assert menzil2.parse_datalink_model_selection("2") == ["faessler_datalink_fit"]
    assert menzil2.parse_datalink_model_selection("3") == ["kirschstein_datalink_fit"]
    assert menzil2.parse_datalink_model_selection("4") == [
        "zeng_datalink_fit",
        "faessler_datalink_fit",
        "kirschstein_datalink_fit",
    ]
    assert menzil2.parse_datalink_model_selection("all") == menzil2.parse_datalink_model_selection("4")
    assert menzil2.parse_datalink_model_selection("hepsi") == menzil2.parse_datalink_model_selection("4")
    assert menzil2.parse_datalink_model_selection("zeng") == ["zeng_datalink_fit"]


def test_custom_speed_datalink_fit_selection_uses_measured_reference_and_reports_batt(monkeypatch, capsys):
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()
    observations = [
        {
            "label": "DataLink v~5.0",
            "speed_ms": 5.0,
            "power_ratio": 0.92,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
        {
            "label": "DataLink v~7.0",
            "speed_ms": 7.0,
            "power_ratio": 0.98,
            "sample_count": 200,
            "raw_sample_count": 220,
            "stable_fraction": 0.91,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.22,
            "extrapolation_region": "measured",
        },
    ]
    empirical_curve = menzil2.build_empirical_datalink_power_curve(observations)
    suite = {
        "empirical_curve": empirical_curve,
        "observations": observations,
        "power_reference_w": 760.0,
        "measured_hover_power_w": 760.0,
        "utip_ms": 171.0,
        "model_functions": {
            "zeng_datalink_fit": lambda v: 1.0 + 0.01 * v,
            "faessler_datalink_fit": lambda v: 1.0 + 0.02 * v,
            "kirschstein_datalink_fit": lambda v: 1.0 + 0.03 * v,
        },
        "model_params": {
            "zeng_datalink_fit": {"f0": 0.8, "k_par": 0.00005},
        },
        "battery_qc_report": {
            "bat_rows": 42,
            "direct_current_fit_enabled": False,
            "warnings": ["battery_current_scale_suspect"],
            "voltr_start_v": 24.0,
            "voltr_end_v": 22.4,
            "datalink_energy_wh": 123.4,
            "battery_energy_delta_raw": 0.2,
        },
        "battery_basis": menzil2.build_july3_firfir_battery_basis(),
        "source_result": {"graph_paths": {}},
    }

    monkeypatch.setattr(
        menzil2,
        "build_datalink_fitted_model_suite",
        lambda *_args, **_kwargs: suite,
    )

    menzil2.run_custom_speed_models(
        [6.0, 20.0],
        profile,
        "1",
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        make_graph=False,
    )

    out = capsys.readouterr().out
    assert "DataLink fit suite" in out
    assert "P_hover(DataLink)=760.0 W" in out
    assert "Utip(DataLink RPM)=171.0 m/s" in out
    assert "BATT QC" in out
    assert "battery_current_scale_suspect" in out
    assert "zeng_datalink_fit" in out
    assert "v=6.00 m/s" in out
    assert "v=20.00 m/s" in out
    assert "datalink_empirical_pv" not in out


def test_custom_speed_datalink_selection_generates_three_model_specific_graphs(monkeypatch):
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()
    observations = [
        {
            "label": "DataLink v~5.0",
            "speed_ms": 5.0,
            "power_ratio": 0.92,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
        {
            "label": "DataLink v~7.0",
            "speed_ms": 7.0,
            "power_ratio": 0.98,
            "sample_count": 200,
            "raw_sample_count": 220,
            "stable_fraction": 0.91,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.22,
            "extrapolation_region": "measured",
        },
    ]
    empirical_curve = menzil2.build_empirical_datalink_power_curve(observations)
    calls = {}
    suite = {
        "empirical_curve": empirical_curve,
        "observations": observations,
        "power_reference_w": 760.0,
        "measured_hover_power_w": 760.0,
        "utip_ms": 171.0,
        "model_functions": {
            "zeng_datalink_fit": lambda v: 1.0 + 0.01 * v,
            "faessler_datalink_fit": lambda v: 1.0 + 0.02 * v,
            "kirschstein_datalink_fit": lambda v: 1.0 + 0.03 * v,
        },
        "model_params": {},
        "battery_qc_report": {
            "bat_rows": 42,
            "direct_current_fit_enabled": False,
            "warnings": [],
            "rows": [{"timestamp_utc": None, "voltr_v": 24.0}],
        },
        "battery_basis": menzil2.build_july3_firfir_battery_basis(),
        "sync_report": [],
        "source_result": {"graph_paths": {}},
    }

    monkeypatch.setattr(
        menzil2,
        "build_datalink_fitted_model_suite",
        lambda *_args, **_kwargs: suite,
    )

    def fake_empirical_plot(empirical_curve, output_path, bauersfeld_points=None):
        calls["empirical_output_path"] = output_path
        calls["empirical_bauersfeld_points"] = bauersfeld_points or []
        return Path(output_path).resolve()

    def fake_power_plot(model_functions, empirical_curve, bauersfeld_points,
                        output_path):
        calls["power_output_path"] = output_path
        calls["power_model_names"] = list(model_functions)
        calls["power_bauersfeld_points"] = bauersfeld_points
        return Path(output_path).resolve()

    def fake_range_plot(model_functions, empirical_curve, bauersfeld_points,
                        hover_power_w, battery_wh, correction_factor,
                        output_path, battery_basis=None):
        calls["range_output_path"] = output_path
        calls["range_model_names"] = list(model_functions)
        calls["range_bauersfeld_points"] = bauersfeld_points
        calls["range_power_reference_w"] = hover_power_w
        calls["range_battery_basis"] = battery_basis
        return Path(output_path).resolve()

    def fake_battery_plot(battery_rows, sync_report,
                          output_path="measured_datalink_battery_voltage.png"):
        calls["battery_output_path"] = output_path
        calls["battery_rows"] = battery_rows
        return Path(output_path).resolve()

    monkeypatch.setattr(menzil2, "plot_datalink_empirical_interpolation", fake_empirical_plot)
    monkeypatch.setattr(menzil2, "plot_datalink_power_ratio_comparison", fake_power_plot)
    monkeypatch.setattr(menzil2, "plot_datalink_range_time_comparison", fake_range_plot)
    monkeypatch.setattr(menzil2, "plot_battery_voltage_timeline", fake_battery_plot)

    menzil2.run_custom_speed_models(
        [6.0, 20.0],
        profile,
        "1",
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        make_graph=True,
    )

    assert calls["range_model_names"] == ["zeng_datalink_fit"]
    assert calls["power_model_names"] == ["zeng_datalink_fit"]
    assert calls["empirical_output_path"] == "datalink_zeng_empirical_interpolation.png"
    assert calls["power_output_path"] == "datalink_zeng_power_ratio.png"
    assert calls["range_output_path"] == "datalink_zeng_range_time.png"
    assert calls["battery_output_path"] == "datalink_zeng_battery_voltage.png"
    assert calls["battery_rows"] == suite["battery_qc_report"]["rows"]
    assert calls["range_power_reference_w"] == 760.0
    assert calls["range_battery_basis"]["usable_energy_wh"] == pytest.approx(559.44, abs=0.01)
    assert any(point["label"].startswith("Bauersfeld") for point in calls["power_bauersfeld_points"])
    assert any(point["label"].startswith("Bauersfeld") for point in calls["range_bauersfeld_points"])


def test_custom_speed_datalink_all_selection_uses_all_three_models(monkeypatch):
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()
    observations = [
        {
            "label": "DataLink v~5.0",
            "speed_ms": 5.0,
            "power_ratio": 0.92,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
        {
            "label": "DataLink v~7.0",
            "speed_ms": 7.0,
            "power_ratio": 0.98,
            "sample_count": 200,
            "raw_sample_count": 220,
            "stable_fraction": 0.91,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.22,
            "extrapolation_region": "measured",
        },
    ]
    suite = {
        "empirical_curve": menzil2.build_empirical_datalink_power_curve(observations),
        "observations": observations,
        "power_reference_w": 760.0,
        "measured_hover_power_w": 760.0,
        "utip_ms": 171.0,
        "model_functions": {
            "zeng_datalink_fit": lambda v: 1.0 + 0.01 * v,
            "faessler_datalink_fit": lambda v: 1.0 + 0.02 * v,
            "kirschstein_datalink_fit": lambda v: 1.0 + 0.03 * v,
        },
        "model_params": {},
        "battery_qc_report": {
            "bat_rows": 42,
            "direct_current_fit_enabled": False,
            "warnings": [],
        },
        "battery_basis": menzil2.build_july3_firfir_battery_basis(),
        "source_result": {"graph_paths": {}},
    }
    calls = {}
    monkeypatch.setattr(menzil2, "build_datalink_fitted_model_suite", lambda *_args, **_kwargs: suite)
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_empirical_interpolation",
        lambda empirical_curve, output_path, bauersfeld_points=None: Path(output_path).resolve(),
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_power_ratio_comparison",
        lambda model_functions, empirical_curve, bauersfeld_points, output_path: (
            calls.setdefault("power_model_names", list(model_functions)),
            Path(output_path).resolve(),
        )[1],
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_range_time_comparison",
        lambda model_functions, empirical_curve, bauersfeld_points, hover_power_w, battery_wh,
        correction_factor, output_path, battery_basis=None: (
            calls.setdefault("range_output_path", output_path),
            calls.setdefault("range_battery_basis", battery_basis),
            Path(output_path).resolve(),
        )[1],
    )
    monkeypatch.setattr(
        menzil2,
        "plot_battery_voltage_timeline",
        lambda battery_rows, sync_report, output_path="measured_datalink_battery_voltage.png": Path(
            output_path
        ).resolve(),
    )

    menzil2.run_custom_speed_models(
        [6.0, 20.0],
        profile,
        "4",
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        make_graph=True,
    )

    assert calls["power_model_names"] == [
        "zeng_datalink_fit",
        "faessler_datalink_fit",
        "kirschstein_datalink_fit",
    ]
    assert calls["range_output_path"] == "datalink_all_range_time.png"
    assert calls["range_battery_basis"]["usable_energy_wh"] == pytest.approx(559.44, abs=0.01)
