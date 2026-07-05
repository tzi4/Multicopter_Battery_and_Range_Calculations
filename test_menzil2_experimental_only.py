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


def _patch_plotters(monkeypatch):
    calls = {}

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

    monkeypatch.setattr(menzil2, "plot_range_time_vs_speed", fake_range_plot)
    monkeypatch.setattr(menzil2, "plot_power_ratio_vs_speed", fake_power_plot)
    return calls


def test_experimental_only_comparison_uses_logs_and_voltage_without_bauersfeld(monkeypatch):
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()
    calls = _patch_plotters(monkeypatch)

    summary = menzil2.run_independent_model_comparison(
        [6.0, 10.0, 15.0],
        profile,
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        make_graph=True,
        fit_mode="experimental_only",
    )

    expected_names = [
        "zeng_experimental_fit",
        "faessler_experimental_fit",
        "kirschstein_experimental_fit",
    ]
    assert summary["fit_mode"] == "experimental_only"
    assert list(summary["model_functions"]) == expected_names
    assert calls["power_model_names"] == expected_names
    assert calls["range_model_names"] == expected_names
    assert calls["show_bauersfeld_points"] is False
    assert calls["range_output_path"] == "experimental_only_model_comparison_range_time.png"
    assert calls["power_output_path"] == "experimental_only_model_comparison_power_ratio.png"
    assert [obs["label"] for obs in summary["observations"]] == ["stadium voltage lap"]
    assert any(point["label"] == "stadium voltage anchor" for point in calls["extra_points"])
    assert all("Bauersfeld" not in obs["label"] for obs in summary["observations"])


def test_all_data_comparison_keeps_bauersfeld_anchors_and_existing_filenames(monkeypatch):
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()
    calls = _patch_plotters(monkeypatch)

    summary = menzil2.run_independent_model_comparison(
        [6.0, 10.0, 15.0],
        profile,
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        make_graph=True,
    )

    expected_names = [
        "zeng_all_data_fit",
        "faessler_all_data_fit",
        "kirschstein_all_data_fit",
    ]
    assert summary["fit_mode"] == "all_data_with_bauersfeld"
    assert list(summary["model_functions"]) == expected_names
    assert calls["power_model_names"] == expected_names
    assert calls["show_bauersfeld_points"] is True
    assert calls["range_output_path"] == "independent_model_comparison_range_time.png"
    assert calls["power_output_path"] == "independent_model_comparison_power_ratio.png"
    assert any(obs["label"] == "Bauersfeld endurance" for obs in summary["observations"])
    assert any(obs["label"] == "Bauersfeld range" for obs in summary["observations"])
