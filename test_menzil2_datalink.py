from pathlib import Path

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


def _sample_udat_path():
    return Path(
        "Datalink Data From my Retarded Friend/datalink/"
        "UART-260625-021604/UART-260625-040328-040715.udat"
    )


def test_parse_datalink_udat_file_extracts_power_rpm_and_utip():
    parsed = menzil2.parse_datalink_udat_file(_sample_udat_path(), prop_diameter_inch=29.0)

    assert parsed["record_count"] > 1000
    assert parsed["active_motor_count_median"] == 4
    assert 15.0 <= parsed["sample_rate_hz"] <= 25.0
    assert 20.0 <= parsed["voltage_median_v"] <= 24.5
    assert parsed["power_median_w"] > 500.0
    assert 3000.0 <= parsed["rpm_median"] <= 7000.0
    assert 120.0 <= parsed["utip_median_ms"] <= 230.0
    assert len(parsed["samples"]) == parsed["record_count"]


def test_datalink_pph_consistency_rejects_bad_6ms_anchor():
    voltage_anchor = {"speed_ms": 6.0, "power_ratio": 0.91}
    observations = [
        {"label": "DataLink v~6.0", "speed_ms": 6.0, "power_ratio": 0.65, "weight": 10.0}
    ]

    qc = menzil2.evaluate_datalink_pph_consistency(observations, voltage_anchor)

    assert qc["fit_allowed"] is False
    assert any("6ms" in warning for warning in qc["warnings"])


def test_datalink_pph_consistency_accepts_matching_6ms_anchor():
    voltage_anchor = {"speed_ms": 6.0, "power_ratio": 0.91}
    observations = [
        {"label": "DataLink v~6.0", "speed_ms": 6.0, "power_ratio": 0.92, "weight": 10.0}
    ]

    qc = menzil2.evaluate_datalink_pph_consistency(observations, voltage_anchor)

    assert qc["fit_allowed"] is True
    assert qc["nearest_6ms"]["power_ratio"] == 0.92


def test_datalink_qc_uses_bauersfeld_log_target_when_stadium_anchor_is_outside_band():
    profile, *_ = _firfir_context()
    raw_voltage_anchor = {"speed_ms": 6.0, "power_ratio": 1.0645}

    qc_anchor = menzil2.build_datalink_pph_consistency_anchor(profile, raw_voltage_anchor)

    assert qc_anchor["source"] == "bauersfeld_log_6ms_sanity"
    assert qc_anchor["power_ratio"] == profile["p_endurance_ratio"]
    assert qc_anchor["raw_voltage_anchor"] == raw_voltage_anchor


def test_bin75_does_not_overlap_with_260625_datalink_session():
    bin_paths = menzil2.find_ardupilot_bin_log_paths(name_filter="00000075.BIN")
    assert bin_paths
    bin_span = menzil2.read_ardupilot_bin_time_span(bin_paths[0])
    session = menzil2.summarize_datalink_session(_sample_udat_path().parent)

    overlaps = menzil2.find_datalink_bin_overlaps([session], [bin_span])

    assert overlaps == []


def test_datalink_model_modes_use_datalink_observations_and_filenames(monkeypatch):
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()
    calls = {}

    def fake_datalink(profile, hover_power_w, voltage_anchor=None, **_kwargs):
        return {
            "fit_allowed": True,
            "observations": [
                {
                    "label": "DataLink v~6.0",
                    "speed_ms": 6.0,
                    "power_ratio": 0.91,
                    "weight": 18.0,
                    "source": "datalink",
                }
            ],
            "raw_observations": [],
            "qc": {"fit_allowed": True, "warnings": [], "nearest_6ms": {"power_ratio": 0.91}},
            "overlaps": [{"session": "fake", "bin": "fake.bin", "overlap_s": 120.0}],
            "utip_ms": 170.0,
        }

    def fake_range_plot(model_functions, hover_power_w, battery_wh, correction_factor,
                        output_path="range_time_vs_speed.png"):
        calls["range_output_path"] = output_path
        calls["range_model_names"] = list(model_functions)
        return Path(output_path).resolve()

    def fake_power_plot(model_functions, v_endurance, v_range,
                        pitch_speed=None, pitch_deg=None,
                        output_path="power_ratio_vs_speed.png",
                        extra_points=None,
                        show_bauersfeld_points=True):
        calls["power_output_path"] = output_path
        calls["power_model_names"] = list(model_functions)
        calls["extra_points"] = extra_points or []
        calls["show_bauersfeld_points"] = show_bauersfeld_points
        return Path(output_path).resolve()

    monkeypatch.setattr(menzil2, "build_datalink_power_observations", fake_datalink)
    monkeypatch.setattr(menzil2, "plot_range_time_vs_speed", fake_range_plot)
    monkeypatch.setattr(menzil2, "plot_power_ratio_vs_speed", fake_power_plot)

    summary = menzil2.run_independent_model_comparison(
        [6.0, 10.0, 15.0],
        profile,
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        make_graph=True,
        fit_mode="datalink_experimental_only",
    )

    expected_names = [
        "zeng_datalink_experimental_fit",
        "faessler_datalink_experimental_fit",
        "kirschstein_datalink_experimental_fit",
    ]
    assert summary["fit_mode"] == "datalink_experimental_only"
    assert summary["profile"]["utip_ms"] == 170.0
    assert list(summary["model_functions"]) == expected_names
    assert calls["power_model_names"] == expected_names
    assert calls["show_bauersfeld_points"] is False
    assert calls["range_output_path"] == "datalink_experimental_model_comparison_range_time.png"
    assert calls["power_output_path"] == "datalink_experimental_model_comparison_power_ratio.png"
    assert any(obs["label"] == "DataLink v~6.0" for obs in summary["observations"])
    assert any(point["label"] == "DataLink v~6.0" for point in calls["extra_points"])


def test_datalink_hover_reference_normalizes_speed_observations():
    joined = []
    for _ in range(4):
        joined.append({
            "speed_ms": 0.4,
            "power_w": 750.0,
            "power_ratio": 0.75,
            "rpm_median": 4400.0,
            "utip_ms": 170.0,
        })
    for _ in range(4):
        joined.append({
            "speed_ms": 5.8,
            "power_w": 765.0,
            "power_ratio": 0.765,
            "rpm_median": 4420.0,
            "utip_ms": 171.0,
        })

    hover_power_w = menzil2.estimate_datalink_hover_power(joined, min_samples=3)
    observations = menzil2.build_datalink_speed_observations(
        joined,
        min_speed_ms=5.0,
        max_speed_ms=6.5,
        min_samples=3,
        power_reference_w=hover_power_w,
    )

    assert hover_power_w == 750.0
    assert len(observations) == 1
    assert observations[0]["power_ratio"] == 765.0 / 750.0


def test_datalink_date_hint_uses_260624_session_with_measured_hover_reference():
    profile, _, hover_power_w, _, _ = _firfir_context()
    bin_paths = [
        path for path in menzil2.find_ardupilot_bin_log_paths()
        if Path(path).name in {"00000071.BIN", "00000072.BIN"}
    ]
    assert bin_paths

    result = menzil2.build_datalink_power_observations(
        profile,
        hover_power_w,
        voltage_anchor={"speed_ms": 6.0, "power_ratio": 0.914},
        bin_paths=bin_paths,
        session_date_hint="260624",
    )

    assert result["fit_allowed"] is True
    assert result["observations"]
    assert result["datalink_hover_power_w"] is not None
    assert 700.0 <= result["datalink_hover_power_w"] <= 820.0
    assert result["qc"]["nearest_6ms"]["power_ratio"] > 0.95
    assert all(
        overlap["session"].startswith("UART-260624")
        for overlap in result["overlaps"]
    )
