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
    # Mekanik olcek (DATALINK_RPM_SCALE sonrasi): datasheet capasi hover ~2216 RPM
    # -> Utip ~82.5 m/s; olculen medyan ~80 m/s beklenir.
    assert 78.0 <= result["utip_ms"] <= 86.0
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


def test_measured_curve_graph_mode_does_not_emit_voltage_graph(monkeypatch, tmp_path):
    observation = {
        "label": "DataLink v~6.0",
        "speed_ms": 6.0,
        "power_ratio": 1.0,
        "sample_count": 120,
        "raw_sample_count": 150,
        "stable_fraction": 0.8,
        "source_bins": ["00000076.BIN"],
        "source_sessions": ["UART-260703-120000"],
        "dt_s_max": 0.18,
        "extrapolation_region": "measured",
    }
    calls = {}

    monkeypatch.setattr(menzil2, "find_measured_curve_log_root", lambda log_root: tmp_path)
    monkeypatch.setattr(menzil2, "find_datalink_session_dirs", lambda _root: [])
    monkeypatch.setattr(
        menzil2, "filter_datalink_sessions_by_date_hint", lambda sessions, _hint: sessions
    )
    monkeypatch.setattr(menzil2, "find_datalink_bin_overlaps", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(menzil2, "annotate_joined_sample_stability", lambda samples: samples)
    monkeypatch.setattr(menzil2, "estimate_datalink_hover_power", lambda _samples: 760.0)
    monkeypatch.setattr(
        menzil2,
        "build_datalink_speed_observations",
        lambda *_args, **_kwargs: [observation],
    )
    monkeypatch.setattr(
        menzil2,
        "build_battery_qc_report",
        lambda *_args, **_kwargs: {"rows": [{"timestamp_utc": None, "voltr_v": 24.0}]},
    )
    monkeypatch.setattr(
        menzil2,
        "build_measured_curve_model_fit",
        lambda profile, *_args, **_kwargs: {
            "profile": dict(profile, utip_ms=81.4),
            "model_functions": {},
            "model_fit_residuals": {},
            "zeng_params": {},
            "faessler_params": {},
            "kirschstein_params": {},
            "fit_audit": {},
        },
    )
    monkeypatch.setattr(
        menzil2,
        "plot_empirical_datalink_power_curve",
        lambda *_args, **_kwargs: calls.setdefault("empirical_power", "empirical.png"),
    )
    monkeypatch.setattr(
        menzil2,
        "plot_measured_power_curve",
        lambda *_args, **_kwargs: calls.setdefault("diagnostic", "diagnostic.png"),
    )
    monkeypatch.setattr(
        menzil2,
        "write_scientific_fit_audit",
        lambda *_args, **_kwargs: calls.setdefault("audit", "audit.md"),
    )
    monkeypatch.setattr(
        menzil2,
        "plot_battery_voltage_timeline",
        lambda *_args, **_kwargs: calls.setdefault("battery", "battery.png"),
    )

    result = menzil2.run_datalink_measured_curve_analysis(
        {"prop_diameter_inch": 29.0},
        {},
        760.0,
        559.44,
        0.8,
        log_root=tmp_path,
        make_graph=True,
    )

    assert calls["empirical_power"] == "empirical.png"
    assert calls["diagnostic"] == "diagnostic.png"
    assert calls["audit"] == "audit.md"
    assert "battery" not in calls
    assert "battery" not in result["graph_paths"]


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

    # Legacy 12-pil (1198.8 Wh, 3.7 V/hucre liion) yorumu, CF ile bile dogru July3
    # (559 Wh) baseline'dan cok daha uzun bir sure verir -> loglardaki 40 dk
    # gerceginden sapar. Bu yuzden July3 usable kapasitesi kullanilir.
    # (legacy deger ~76.87 dk, baseline 39.86 dk)
    legacy_time_10_min = legacy_battery_wh / 757.891 * 60.0 * 0.72 * 1.125
    assert legacy_time_10_min == pytest.approx(76.87, abs=0.1)
    assert legacy_time_10_min > row["time_10_min"] * 1.5
    assert row["time_10_min"] == pytest.approx(39.86, abs=0.05)
    assert row["time_20_min"] == pytest.approx(35.43, abs=0.05)
    assert row["battery_basis_label"].startswith("6S1P (tek kol")


def test_datalink_fit_suite_reports_july3_battery_basis(monkeypatch):
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()

    fake_result = {
        "empirical_curve": {"measured_points": []},
        "speed_bin_observations": [],
        "power_reference_w": 757.891,
        "measured_hover_power_w": 757.891,
        "utip_ms": 82.9,
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
    # Basis + reserve TEK KOL (6S1P) tutarli kalir -> 40 dk baseline degismez
    assert suite["battery_basis"]["usable_energy_wh"] == pytest.approx(559.44, abs=0.01)
    assert reserve["hover_10_reserve_min"] == pytest.approx(39.86, abs=0.05)
    assert reserve["hover_20_reserve_min"] == pytest.approx(35.43, abs=0.05)
    # Legacy 12-pil yorumu dogru baseline'dan >1.5x uzun (legacy ~76.87 dk,
    # 3.7 V/hucre liion enerjisiyle)
    assert reserve["legacy_hover_10_reserve_min"] == pytest.approx(76.87, abs=0.1)
    assert reserve["legacy_hover_10_reserve_min"] > reserve["hover_10_reserve_min"] * 1.5

    # Sensor tek koldaydi: gercek arac hover ve full pack usable = x2 (6S2P, 12 pil).
    # Bu MUTLAK degerler fiziksel gercek (1516 W > teorik 1124 W), 40 dk oran-sabiti korunur.
    assert suite["battery_parallel_arms"] == 2
    assert suite["vehicle_measured_hover_power_w"] == pytest.approx(757.891 * 2, abs=0.01)
    assert suite["full_pack_usable_energy_wh"] == pytest.approx(559.44 * 2, abs=0.02)
    # Verim orani artik arac seviyesinde >1 (gercek hover teorigin ustunde -> fiziksel)
    assert suite["datalink_efficiency_ratio"] == pytest.approx(
        (757.891 * 2) / suite["fit_theoretical_hover_power_w"], rel=1e-6
    )
    assert suite["datalink_efficiency_ratio"] > 1.0


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


def test_preset_fit_console_summary_uses_measured_reference_and_reports_batt(
    monkeypatch, capsys, tmp_path
):
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
        "utip_ms": 81.4,
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
    monkeypatch.setattr(
        menzil2,
        "write_datalink_fit_method_report",
        lambda *_args, **_kwargs: tmp_path / "report.md",
    )

    menzil2.run_preset_fit_apply_to_vehicle(
        [6.0, 20.0],
        profile,
        sonuc,
        "1",
        760.0,
        battery_wh,
        correction_factor,
        make_graph=False,
        apply_sonuc=sonuc,
    )

    out = capsys.readouterr().out
    assert "DataLink fit suite" in out
    # Olculen hover tek kol (6S1P) olarak etiketlenir
    assert "P_hover(DataLink, olculen tek kol)=760.0 W" in out
    assert "Utip(DataLink RPM)=81.4 m/s" in out
    assert "BATT QC" in out
    assert "battery_current_scale_suspect" in out
    assert "zeng_datalink_fit" in out
    assert "v=6.00 m/s" in out
    assert "v=20.00 m/s" in out
    assert "datalink_empirical_pv" not in out


def test_preset_fit_application_uses_global_hover_scale_and_entered_battery_basis(
    monkeypatch, capsys, tmp_path
):
    profile, fit_sonuc, _hover_power_w, battery_wh, correction_factor = _firfir_context()
    observations = [
        {
            "label": "DataLink v~6.0",
            "speed_ms": 6.0,
            "power_ratio": 1.0,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
    ]
    suite = {
        "empirical_curve": menzil2.build_empirical_datalink_power_curve(observations),
        "observations": observations,
        "power_reference_w": 760.0,
        "measured_hover_power_w": 760.0,
        "utip_ms": 81.4,
        "model_functions": {"zeng_datalink_fit": lambda v: 1.0},
        "model_params": {},
        "battery_qc_report": {"warnings": [], "direct_current_fit_enabled": False},
        "battery_basis": menzil2.build_july3_firfir_battery_basis(),
        "datalink_efficiency_ratio": 1.25,
        "sync_report": [],
        "source_result": {"graph_paths": {}},
    }
    monkeypatch.setattr(
        menzil2,
        "build_datalink_fitted_model_suite",
        lambda *_args, **_kwargs: suite,
    )
    monkeypatch.setattr(
        menzil2,
        "write_datalink_fit_method_report",
        lambda *_args, **_kwargs: tmp_path / "report.md",
    )

    menzil2.run_preset_fit_apply_to_vehicle(
        [6.0],
        profile,
        fit_sonuc,
        "1",
        1000.0,
        battery_wh,
        correction_factor,
        make_graph=False,
        apply_sonuc=fit_sonuc,
    )

    out = capsys.readouterr().out
    # Model P/Ph orani Firfir'e tune edilir; ANA tablo/grafik ise girilen aracin
    # bataryasi ve global DataLink hover olcegi ile hesaplanir.
    expected_usable = battery_wh * menzil2.FIRFIR_BATTERY_USABLE_FRACTION
    assert "P=1250.0 W" in out
    assert "P_hover = 1250.0 W" in out
    assert f"{expected_usable:.1f} Wh usable" in out
    assert "DataLink-calibrated entered vehicle basis" in out
    # Firfir July3 calibrated basis hala tune-kaynagi bilgisi olarak gosterilir.
    assert "MODEL TUNE-KAYNAGI BASIS" in out
    assert "P_hover(Firfir calibrated) = 760.0 W" in out


def test_preset_fit_application_generates_datalink_graphs_with_global_hover_scale(
    monkeypatch, tmp_path
):
    profile, fit_sonuc, _hover_power_w, battery_wh, correction_factor = _firfir_context()
    observations = [
        {
            "label": "DataLink v~6.0",
            "speed_ms": 6.0,
            "power_ratio": 1.0,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
    ]
    suite = {
        "empirical_curve": menzil2.build_empirical_datalink_power_curve(observations),
        "observations": observations,
        "power_reference_w": 760.0,
        "measured_hover_power_w": 760.0,
        "utip_ms": 81.4,
        "model_functions": {"zeng_datalink_fit": lambda v: 1.0},
        "model_params": {},
        "battery_qc_report": {
            "warnings": [],
            "direct_current_fit_enabled": False,
            "rows": [{"timestamp_utc": None, "voltr_v": 24.0}],
        },
        "battery_basis": menzil2.build_july3_firfir_battery_basis(),
        "datalink_efficiency_ratio": 1.25,
        "sync_report": [],
        "source_result": {"graph_paths": {}},
    }
    calls = {}
    monkeypatch.setattr(
        menzil2,
        "build_datalink_fitted_model_suite",
        lambda *_args, **_kwargs: suite,
    )
    monkeypatch.setattr(
        menzil2,
        "write_datalink_fit_method_report",
        lambda *_args, **_kwargs: tmp_path / "report.md",
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_empirical_interpolation",
        lambda empirical_curve, output_path, bauersfeld_points=None: calls.setdefault(
            "empirical_output_path", output_path
        ),
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_power_ratio_comparison",
        lambda model_functions, empirical_curve, bauersfeld_points, output_path: calls.setdefault(
            "power_output_path", output_path
        ),
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_range_time_comparison",
        lambda model_functions, empirical_curve, bauersfeld_points, hover_power_w,
        battery_wh, correction_factor, output_path, battery_basis=None: (
            calls.setdefault("range_output_path", output_path),
            calls.setdefault("range_power_reference_w", hover_power_w),
            calls.setdefault("range_battery_basis", battery_basis),
        )[0],
    )
    monkeypatch.setattr(
        menzil2,
        "plot_battery_voltage_timeline",
        lambda battery_rows, sync_report, output_path="measured_datalink_battery_voltage.png": calls.setdefault(
            "battery_output_path", output_path
        ),
    )

    menzil2.run_preset_fit_apply_to_vehicle(
        [6.0],
        profile,
        fit_sonuc,
        "1",
        1000.0,
        battery_wh,
        correction_factor,
        make_graph=True,
        apply_sonuc=fit_sonuc,
    )

    # Empirical interpolation grafigi artik yalnizca menu-5 ham veri
    # gorselleyicisinde uretilir; preset akisi cizmez.
    assert "empirical_output_path" not in calls
    assert calls["power_output_path"] == "datalink_zeng_power_ratio.png"
    assert calls["range_output_path"] == "datalink_zeng_range_time.png"
    assert "battery_output_path" not in calls
    # Grafik/hesap girilen aracin hover gucu global DataLink olcegiyle kalibre
    # edilerek ve girilen bataryanin usable enerjisiyle yapilir.
    assert calls["range_power_reference_w"] == 1250.0
    expected_usable = battery_wh * menzil2.FIRFIR_BATTERY_USABLE_FRACTION
    assert calls["range_battery_basis"]["usable_energy_wh"] == pytest.approx(
        expected_usable, abs=0.01
    )


def test_preset_fit_application_uses_global_datalink_hover_scale(
    monkeypatch, capsys, tmp_path
):
    profile, fit_sonuc, _hover_power_w, battery_wh, correction_factor = _firfir_context()
    hover_scale = (757.891 * 2.0) / 1124.0
    observations = [
        {
            "label": "DataLink v~6.0",
            "speed_ms": 6.0,
            "power_ratio": 1.0,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
    ]
    suite = {
        "empirical_curve": menzil2.build_empirical_datalink_power_curve(observations),
        "observations": observations,
        "power_reference_w": 757.891,
        "measured_hover_power_w": 757.891,
        "utip_ms": 81.4,
        "model_functions": {"zeng_datalink_fit": lambda v: 1.0},
        "model_params": {},
        "battery_qc_report": {"warnings": [], "direct_current_fit_enabled": False},
        "battery_basis": menzil2.build_july3_firfir_battery_basis(),
        "datalink_efficiency_ratio": hover_scale,
        "sync_report": [],
        "source_result": {"graph_paths": {}},
    }
    monkeypatch.setattr(
        menzil2,
        "build_datalink_fitted_model_suite",
        lambda *_args, **_kwargs: suite,
    )
    monkeypatch.setattr(
        menzil2,
        "write_datalink_fit_method_report",
        lambda *_args, **_kwargs: tmp_path / "report.md",
    )

    menzil2.run_preset_fit_apply_to_vehicle(
        [6.0],
        profile,
        fit_sonuc,
        "1",
        1124.0,
        battery_wh,
        correction_factor,
        make_graph=False,
        apply_sonuc=fit_sonuc,
    )

    out = capsys.readouterr().out
    # Ozel arac tanima yok: girilen hover, Firfir DataLink gercek/teorik hover
    # olcegiyle global olarak kalibre edilir; batarya girilen LiIon enerjisinden gelir.
    expected_usable = battery_wh * menzil2.FIRFIR_BATTERY_USABLE_FRACTION
    assert "DataLink-calibrated entered vehicle basis" in out
    assert "P_hover = 1515.8 W" in out
    assert f"{expected_usable:.1f} Wh usable" in out
    # 1198.8 Wh liion -> 1118.9 Wh usable; 1515.8 W hover -> 44.3 dk pratik %0
    assert "%20=35.4 dk, %10=39.9 dk" in out
    # Firfir calibrated tek-kol basis hala tune-kaynagi bilgisi olarak gosterilir.
    assert "P_hover(Firfir calibrated) = 757.9 W" in out


def test_global_hover_scale_lowers_16ms_estimate_without_vehicle_special_case(
    monkeypatch, tmp_path
):
    profile, fit_sonuc, _hover_power_w, battery_wh, correction_factor = _firfir_context()
    hover_scale = (757.891 * 2.0) / 1124.0
    observations = [
        {
            "label": "DataLink v~6.0",
            "speed_ms": 6.0,
            "power_ratio": 1.0,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
    ]
    suite = {
        "empirical_curve": menzil2.build_empirical_datalink_power_curve(observations),
        "observations": observations,
        "power_reference_w": 757.891,
        "measured_hover_power_w": 757.891,
        "utip_ms": 81.4,
        "model_functions": {"zeng_datalink_fit": lambda _v: 1.1859},
        "model_params": {},
        "battery_qc_report": {"warnings": [], "direct_current_fit_enabled": False},
        "battery_basis": menzil2.build_july3_firfir_battery_basis(),
        "datalink_efficiency_ratio": hover_scale,
        "sync_report": [],
        "source_result": {"graph_paths": {}},
    }
    monkeypatch.setattr(
        menzil2,
        "build_datalink_fitted_model_suite",
        lambda *_args, **_kwargs: suite,
    )
    monkeypatch.setattr(
        menzil2,
        "write_datalink_fit_method_report",
        lambda *_args, **_kwargs: tmp_path / "report.md",
    )

    result = menzil2.run_preset_fit_apply_to_vehicle(
        [16.0],
        profile,
        fit_sonuc,
        "1",
        1124.0,
        battery_wh,
        correction_factor,
        make_graph=False,
        apply_sonuc=fit_sonuc,
    )

    basis = result["result_range_time_basis"]
    row = menzil2.calculate_flight_for_speed(
        16.0,
        1.1859,
        basis["power_reference_w"],
        battery_wh,
        correction_factor,
        battery_basis=basis["battery_basis"],
    )
    old_entered_basis = menzil2.build_applied_battery_basis(battery_wh)
    old_row = menzil2.calculate_flight_for_speed(
        16.0,
        1.1859,
        1124.0,
        battery_wh,
        correction_factor,
        battery_basis=old_entered_basis,
    )

    assert basis["mode"] == "datalink_calibrated_application"
    assert row["time_10_min"] == pytest.approx(33.61, abs=0.05)
    assert old_row["time_10_min"] == pytest.approx(45.33, abs=0.05)


def test_global_hover_scale_report_and_graph_use_same_result_basis(
    monkeypatch, tmp_path
):
    profile, fit_sonuc, _hover_power_w, battery_wh, correction_factor = _firfir_context()
    hover_scale = (757.891 * 2.0) / 1124.0
    observations = [
        {
            "label": "DataLink v~6.0",
            "speed_ms": 6.0,
            "power_ratio": 1.0,
            "sample_count": 120,
            "raw_sample_count": 150,
            "stable_fraction": 0.8,
            "source_bins": ["00000076.BIN"],
            "source_sessions": ["UART-260703-120000"],
            "dt_s_max": 0.18,
            "extrapolation_region": "measured",
        },
    ]
    suite = {
        "empirical_curve": menzil2.build_empirical_datalink_power_curve(observations),
        "observations": observations,
        "power_reference_w": 757.891,
        "measured_hover_power_w": 757.891,
        "utip_ms": 81.4,
        "model_functions": {"zeng_datalink_fit": lambda _v: 1.0},
        "model_params": {},
        "battery_qc_report": {"warnings": [], "direct_current_fit_enabled": False},
        "battery_basis": menzil2.build_july3_firfir_battery_basis(),
        "datalink_efficiency_ratio": hover_scale,
        "sync_report": [],
        "source_result": {"graph_paths": {}},
    }
    calls = {}
    monkeypatch.setattr(
        menzil2,
        "build_datalink_fitted_model_suite",
        lambda *_args, **_kwargs: suite,
    )
    monkeypatch.setattr(
        menzil2,
        "write_datalink_fit_method_report",
        lambda _suite, _selected, output_path=menzil2.DATALINK_FIT_REPORT_PATH,
        range_time_basis_override=None: (
            calls.setdefault("report_basis", range_time_basis_override),
            tmp_path / "report.md",
        )[1],
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_empirical_interpolation",
        lambda *_args, **_kwargs: tmp_path / "empirical.png",
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_power_ratio_comparison",
        lambda *_args, **_kwargs: tmp_path / "power.png",
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_range_time_comparison",
        lambda model_functions, empirical_curve, bauersfeld_points, hover_power_w,
        battery_wh, correction_factor, output_path, battery_basis=None: (
            calls.setdefault("graph_hover_power_w", hover_power_w),
            calls.setdefault("graph_battery_basis", battery_basis),
            tmp_path / "range.png",
        )[2],
    )

    result = menzil2.run_preset_fit_apply_to_vehicle(
        [6.0],
        profile,
        fit_sonuc,
        "1",
        1124.0,
        battery_wh,
        correction_factor,
        make_graph=True,
        apply_sonuc=fit_sonuc,
    )

    basis = result["result_range_time_basis"]
    report_basis = calls["report_basis"]
    assert calls["graph_hover_power_w"] == pytest.approx(basis["power_reference_w"])
    assert report_basis["power_reference_w"] == pytest.approx(basis["power_reference_w"])
    assert calls["graph_battery_basis"]["usable_energy_wh"] == pytest.approx(
        basis["battery_basis"]["usable_energy_wh"]
    )
    assert report_basis["battery_basis"]["usable_energy_wh"] == pytest.approx(
        basis["battery_basis"]["usable_energy_wh"]
    )
    report_text = menzil2.format_datalink_fit_method_report(
        suite,
        ["zeng_datalink_fit"],
        range_time_basis_override=basis,
    )
    assert "DataLink-calibrated entered vehicle basis" in report_text
    assert "1515.8 W" in report_text
    assert "1118.9 Wh" in report_text


def test_preset_fit_selection_generates_model_specific_graphs(monkeypatch, tmp_path):
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
        "utip_ms": 81.4,
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
    monkeypatch.setattr(
        menzil2,
        "write_datalink_fit_method_report",
        lambda *_args, **_kwargs: tmp_path / "report.md",
    )

    menzil2.run_preset_fit_apply_to_vehicle(
        [6.0, 20.0],
        profile,
        sonuc,
        "1",
        760.0,
        battery_wh,
        correction_factor,
        make_graph=True,
        apply_sonuc=sonuc,
    )

    assert calls["range_model_names"] == ["zeng_datalink_fit"]
    assert calls["power_model_names"] == ["zeng_datalink_fit"]
    # Empirical interpolation grafigi artik yalnizca menu-5 ham veri
    # gorselleyicisinde uretilir; preset akisi cizmez.
    assert "empirical_output_path" not in calls
    assert calls["power_output_path"] == "datalink_zeng_power_ratio.png"
    assert calls["range_output_path"] == "datalink_zeng_range_time.png"
    assert "battery_output_path" not in calls
    assert calls["range_power_reference_w"] == 760.0
    # Preset akisi girilen bataryayi July3 usable oraniyla olcekler.
    expected_usable = battery_wh * menzil2.FIRFIR_BATTERY_USABLE_FRACTION
    assert calls["range_battery_basis"]["usable_energy_wh"] == pytest.approx(
        expected_usable, abs=0.01
    )
    assert any(point["label"].startswith("Bauersfeld") for point in calls["power_bauersfeld_points"])
    assert any(point["label"].startswith("Bauersfeld") for point in calls["range_bauersfeld_points"])


def test_preset_fit_all_selection_uses_all_three_models(monkeypatch, tmp_path):
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
        "utip_ms": 81.4,
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

    monkeypatch.setattr(
        menzil2,
        "write_datalink_fit_method_report",
        lambda *_args, **_kwargs: tmp_path / "report.md",
    )

    menzil2.run_preset_fit_apply_to_vehicle(
        [6.0, 20.0],
        profile,
        sonuc,
        "4",
        760.0,
        battery_wh,
        correction_factor,
        make_graph=True,
        apply_sonuc=sonuc,
    )

    assert calls["power_model_names"] == [
        "zeng_datalink_fit",
        "faessler_datalink_fit",
        "kirschstein_datalink_fit",
    ]
    assert calls["range_output_path"] == "datalink_all_range_time.png"
    expected_usable = battery_wh * menzil2.FIRFIR_BATTERY_USABLE_FRACTION
    assert calls["range_battery_basis"]["usable_energy_wh"] == pytest.approx(
        expected_usable, abs=0.01
    )


def test_raw_datalink_viewer_is_the_only_voltage_graph_path(monkeypatch):
    import matplotlib.pyplot as plt

    calls = {}
    empirical_curve = menzil2.build_empirical_datalink_power_curve(
        [
            {
                "label": "DataLink v~6.0",
                "speed_ms": 6.0,
                "power_ratio": 1.0,
                "sample_count": 120,
                "raw_sample_count": 150,
                "stable_fraction": 0.8,
                "source_bins": ["00000076.BIN"],
                "source_sessions": ["UART-260703-120000"],
                "dt_s_max": 0.18,
                "extrapolation_region": "measured",
            },
        ]
    )
    fake_result = {
        "empirical_curve": empirical_curve,
        "battery_qc_report": {"rows": [{"timestamp_utc": None, "voltr_v": 24.0}]},
        "sync_report": [{"accepted_for_fit": True}],
    }
    monkeypatch.setattr(
        menzil2,
        "run_datalink_measured_curve_analysis",
        lambda *_args, **_kwargs: fake_result,
    )
    monkeypatch.setattr(
        menzil2,
        "plot_datalink_empirical_interpolation",
        lambda empirical_curve, output_path, bauersfeld_points=None: calls.setdefault(
            "empirical_output_path", output_path
        ),
    )
    monkeypatch.setattr(
        menzil2,
        "plot_battery_voltage_timeline",
        lambda battery_rows, sync_report, output_path="measured_datalink_battery_voltage.png": (
            calls.setdefault("battery_rows", battery_rows),
            calls.setdefault("sync_report", sync_report),
            calls.setdefault("battery_output_path", output_path),
        )[2],
    )
    monkeypatch.setattr(plt, "show", lambda: None)

    menzil2.run_datalink_raw_data_viewer(None, "260703")

    assert calls["empirical_output_path"] == "raw_datalink_empirical_interpolation.png"
    assert calls["battery_output_path"] == "raw_datalink_battery_voltage.png"
    assert calls["battery_rows"] == fake_result["battery_qc_report"]["rows"]
    assert calls["sync_report"] == fake_result["sync_report"]
