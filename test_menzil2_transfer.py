import math

import pytest

import menzil2


FIT_HOVER_W = 758.0
# Mekanik olcek (DATALINK_RPM_SCALE sonrasi): eski ham-olcek 168 m/s -> ~80 m/s.
FIT_UTIP_MS = 80.0
FIT_V0_MS = math.sqrt(
    12.4 * 9.81 / (2.0 * 1.225 * 4.0 * math.pi * (28.0 * 0.0254 / 2.0) ** 2)
)


def _fit_profile():
    profile = dict(menzil2.FIRFIR_SPEED_PRESET)
    profile["utip_ms"] = FIT_UTIP_MS
    return profile


def _synthetic_observations():
    # Zeng-formlu "gercek" bir egriden uretilmis sentetik binler; fitler bu
    # egriyi geri bulur, boylece transfer ozdesligi gercekci parametrelerle test edilir.
    observations = []
    for speed in [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]:
        ratio = (
            0.82 * menzil2.zeng_profile_ratio(speed, FIT_UTIP_MS)
            + 0.18 * menzil2.zeng_induced_ratio(speed, FIT_V0_MS)
            + 6.0e-05 * speed**3
        )
        observations.append(
            {
                "label": f"DataLink v~{speed:.1f}",
                "speed_ms": speed,
                "power_ratio": ratio,
                "weight": 10.0,
                "sample_count": 500,
            }
        )
    return observations


def _fitted_suite():
    profile = _fit_profile()
    observations = _synthetic_observations()
    theoretical = menzil2.build_theoretical_zeng_params(profile, FIT_HOVER_W)
    faessler_attitude = {
        "body_cda_fit_m2": 0.15,
        "body_cd_fit": 0.8,
        "lambda_fit_n_per_ms": 1.3,
        "rho": 1.225,
    }
    zeng = menzil2.fit_observation_weighted_zeng(
        FIT_V0_MS, FIT_UTIP_MS, FIT_HOVER_W, theoretical, None, observations
    )
    faessler = menzil2.fit_faessler_drag_constrained_zeng(
        FIT_V0_MS,
        FIT_UTIP_MS,
        FIT_HOVER_W,
        theoretical,
        faessler_attitude,
        None,
        observations=observations,
    )
    kirschstein = menzil2.fit_kirschstein_all_data(
        profile, FIT_HOVER_W, FIT_V0_MS, observations, faessler_fit=faessler_attitude
    )
    return {
        "model_profile": profile,
        "power_reference_w": FIT_HOVER_W,
        "battery_parallel_arms": 2,
        "utip_ms": FIT_UTIP_MS,
        "model_params": {
            "zeng_datalink_fit": zeng,
            "faessler_datalink_fit": faessler,
            "kirschstein_datalink_fit": kirschstein,
        },
        "model_functions": {
            "zeng_datalink_fit": (
                lambda v, p=zeng: menzil2.power_ratio_bauersfeld_anchored_zeng(v, p)
            ),
            "faessler_datalink_fit": (
                lambda v, p=faessler: (
                    menzil2.power_ratio_faessler_drag_constrained_zeng(v, p)
                )
            ),
            "kirschstein_datalink_fit": (
                lambda v, p=kirschstein: menzil2.power_ratio_kirschstein_all_data(v, p)
            ),
        },
    }


def _grid():
    return [0.25 * i for i in range(1, 101)]


# --- Faz 3 duzeltmeleri -----------------------------------------------------


def test_fit_observation_weighted_zeng_empty_observations_has_no_keyerror():
    profile = _fit_profile()
    theoretical = menzil2.build_theoretical_zeng_params(profile, FIT_HOVER_W)

    params = menzil2.fit_observation_weighted_zeng(
        FIT_V0_MS, FIT_UTIP_MS, FIT_HOVER_W, theoretical, None, []
    )

    expected_k_par = (
        0.5 * theoretical["rho"] * theoretical["cda_body_m2"] / FIT_HOVER_W
    )
    assert params["k_par"] == pytest.approx(expected_k_par)
    assert 0.0 < params["f0"] < 1.0
    assert params["induced_fraction"] == pytest.approx(1.0 - params["f0"])


def test_fit_observation_weighted_zeng_empty_observations_prefers_attitude_prior():
    profile = _fit_profile()
    theoretical = menzil2.build_theoretical_zeng_params(profile, FIT_HOVER_W)
    attitude_fit = {"cda_m2": 0.30, "rho": 1.225, "speed_bins": []}

    params = menzil2.fit_observation_weighted_zeng(
        FIT_V0_MS, FIT_UTIP_MS, FIT_HOVER_W, theoretical, attitude_fit, []
    )

    assert params["k_par"] == pytest.approx(0.5 * 1.225 * 0.30 / FIT_HOVER_W)


def test_resolve_fit_power_reference_prefers_measured_then_fit_profile():
    fit_profile = {"theoretical_hover_power_w": 1124.0}

    assert (
        menzil2.resolve_fit_power_reference(757.9, fit_profile, 999.0) == 757.9
    )
    # Olculen hover yoksa GIRILEN aracin gucu degil, fit aracinin teorik
    # hover'i kullanilmali (yanlis referansla sessiz normalizasyon yok).
    assert menzil2.resolve_fit_power_reference(None, fit_profile, 999.0) == 1124.0
    assert menzil2.resolve_fit_power_reference(None, {}, 999.0) == 999.0


# --- Faz 4: fiziksel parametre transferi ------------------------------------


def test_transfer_identity_reproduces_fit_vehicle_curves():
    suite = _fitted_suite()
    apply_profile = {
        "vehicle_name": "Firfir (ozdeslik)",
        "mass_kg": 12.4,
        "num_rotors": 4,
        "prop_diameter_inch": 28.0,
        "rho": 1.225,
    }

    transfer = menzil2.build_transferred_model_suite(suite, apply_profile)

    assert transfer["apply_utip_ms"] == pytest.approx(FIT_UTIP_MS)
    for name in ("zeng_datalink_fit", "faessler_datalink_fit"):
        original = suite["model_functions"][name]
        rebuilt = transfer["model_functions"][name]
        for speed in _grid():
            assert rebuilt(speed) == pytest.approx(original(speed), abs=1e-9), name
    # Kirschstein arac-seviyesi tutarli baza yeniden oturtulur; ozdeslik kucuk
    # bir yeniden-fit kalintisiyla saglanir.
    original = suite["model_functions"]["kirschstein_datalink_fit"]
    rebuilt = transfer["model_functions"]["kirschstein_datalink_fit"]
    max_residual = max(abs(rebuilt(v) - original(v)) for v in _grid())
    assert max_residual < 0.02


def test_transfer_mass_changes_curve_shape_not_just_scale():
    suite = _fitted_suite()
    heavy_profile = {
        "vehicle_name": "Agir arac",
        "mass_kg": 24.8,
        "num_rotors": 4,
        "prop_diameter_inch": 28.0,
        "rho": 1.225,
    }

    transfer = menzil2.build_transferred_model_suite(suite, heavy_profile)

    zeng = transfer["model_params"]["zeng_datalink_fit"]
    # Kutle 2x -> disk yuku 2x -> v0 sqrt(2) katina cikar.
    assert zeng["v0_ms"] == pytest.approx(FIT_V0_MS * math.sqrt(2.0), rel=1e-6)
    # Induced guc W^1.5 ile buyur -> hover tahmini fit aracindan buyuk.
    assert zeng["transfer"]["hover_power_pred_w"] > FIT_HOVER_W * 2

    frozen = suite["model_functions"]["zeng_datalink_fit"]
    rebuilt = transfer["model_functions"]["zeng_datalink_fit"]
    # SEKIL degisir, sadece olcek degil: iki egri orantili olsaydi
    # rebuilt/frozen orani her hizda ayni olurdu.
    ratio_low = rebuilt(5.0) / frozen(5.0)
    ratio_high = rebuilt(15.0) / frozen(15.0)
    assert abs(ratio_low - ratio_high) > 0.005

    def optimum_range_speed(fn):
        return min(_grid(), key=lambda v: fn(v) / v)

    # Agir aracta menzil-optimum hizi saga kayar (frozen sekil bunu asla gosteremez).
    assert optimum_range_speed(rebuilt) > optimum_range_speed(frozen)


def test_theoretical_utip_similarity_identity_and_scaling():
    identity = menzil2.estimate_theoretical_utip_similarity(
        12.4, 4, 28.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    assert identity["utip_ms"] == pytest.approx(FIT_UTIP_MS)
    assert identity["pct_diff_vs_fit"] == pytest.approx(0.0, abs=1e-9)

    # Ayni kutlede 29" pervane: ayni itki icin daha yavas donus -> Utip x 28/29.
    g29 = menzil2.estimate_theoretical_utip_similarity(
        12.4, 4, 29.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    assert g29["utip_ms"] == pytest.approx(FIT_UTIP_MS * 28.0 / 29.0)
    assert g29["rpm"] == pytest.approx(
        g29["utip_ms"] * 60.0 / (math.pi * 29.0 * 0.0254)
    )

    # Kutle 2x -> rotor basina itki 2x -> Utip sqrt(2) katina cikar.
    heavy = menzil2.estimate_theoretical_utip_similarity(
        24.8, 4, 28.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    assert heavy["utip_ms"] == pytest.approx(FIT_UTIP_MS * math.sqrt(2.0))


def test_theoretical_utip_datasheet_identity_and_scale_discovery():
    # Fit noktasinda ozdeslik: ayni arac girilirse fit Utip'i birebir geri doner.
    identity = menzil2.estimate_theoretical_utip_datasheet(
        12.4, 4, 28.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    assert identity["utip_ms"] == pytest.approx(FIT_UTIP_MS)
    assert identity["pct_diff_vs_fit"] == pytest.approx(0.0, abs=1e-9)

    # Datasheet mutlak degerler: 3100 g @ G28x9.2 -> ~2216 RPM, ~82 m/s.
    assert identity["fit_rpm_datasheet"] == pytest.approx(2216.3, abs=1.0)
    assert identity["fit_utip_datasheet_ms"] == pytest.approx(82.5, abs=0.5)
    # Parser DATALINK_RPM_SCALE duzeltmesi sonrasi olcek ~1.0 (80 / 82.5 = 0.97).
    assert 0.9 < identity["datalink_scale"] < 1.05

    # 29" pervane, ayni kutle: oran datasheet egrilerinden gelir.
    g29 = menzil2.estimate_theoretical_utip_datasheet(
        12.4, 4, 29.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    rpm_g29, _ = menzil2.datasheet_rpm_from_thrust(29.0, 3100.0)
    expected_ratio = (rpm_g29 * 29.0) / (identity["fit_rpm_datasheet"] * 28.0)
    assert g29["utip_ms"] == pytest.approx(FIT_UTIP_MS * expected_ratio)


def test_datasheet_rpm_table_requires_supported_prop():
    with pytest.raises(ValueError):
        menzil2.datasheet_rpm_from_thrust(30.0, 3000.0)


def test_preset_fit_theoretical_datasheet_utip_mode_feeds_transfer(
    monkeypatch, capsys, tmp_path
):
    suite = _fitted_suite()
    suite.update(
        {
            "empirical_curve": {"measured_points": []},
            "observations": [],
            "measured_hover_power_w": FIT_HOVER_W,
            "battery_qc_report": {"warnings": [], "direct_current_fit_enabled": False},
            "battery_basis": menzil2.build_july3_firfir_battery_basis(),
            "sync_report": [],
            "source_result": {"graph_paths": {}},
        }
    )
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
    fit_profile = _fit_profile()
    fake_sonuc = {
        "optimal_endurance_speed_ms": 6.6,
        "optimal_speed_ms": 10.7,
        "vi_h": FIT_V0_MS,
    }
    apply_profile = {
        "vehicle_name": "Sim arac",
        "mass_kg": 18.6,
        "num_rotors": 4,
        "prop_diameter_inch": 29.0,
        "rho": 1.225,
    }

    result = menzil2.run_preset_fit_apply_to_vehicle(
        [6.0],
        fit_profile,
        fake_sonuc,
        "1",
        1500.0,
        1198.8,
        0.72,
        make_graph=False,
        apply_sonuc=fake_sonuc,
        apply_profile=apply_profile,
        apply_utip_mode="theoretical_datasheet",
    )

    expected = menzil2.estimate_theoretical_utip_datasheet(
        18.6, 4, 29.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    out = capsys.readouterr().out
    assert "TEORIK UTIP" in out
    assert "Datasheet mekanik RPM" in out
    assert (
        f"Kullanilan (fit olcegine capali) Utip = {expected['utip_ms']:.1f} m/s"
        in out
    )
    assert f"%{expected['pct_diff_vs_fit']:+.1f}" in out
    # Parser olcek duzeltmesi sonrasi datalink_scale ~0.97 -> olcek uyarisi
    # artik tetiklenmemeli.
    assert "UYARI: DataLink Utip'i" not in out
    # Teorik Utip transfere girdi olarak gecer.
    assert result["transfer"]["apply_utip_ms"] == pytest.approx(expected["utip_ms"])
    zeng = result["transfer"]["model_params"]["zeng_datalink_fit"]
    assert zeng["utip_ms"] == pytest.approx(expected["utip_ms"])


def test_transfer_requires_fitted_model_params():
    suite = {
        "model_profile": _fit_profile(),
        "power_reference_w": FIT_HOVER_W,
        "battery_parallel_arms": 2,
        "utip_ms": FIT_UTIP_MS,
        "model_params": {},
        "model_functions": {},
    }
    with pytest.raises(ValueError):
        menzil2.build_transferred_model_suite(
            suite, {"mass_kg": 12.4, "num_rotors": 4, "prop_diameter_inch": 28.0}
        )
