import math
from pathlib import Path
import sys

import pytest

import multicopter_range

# Examples are distributed as scripts, including their sibling imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
try:
    from analyze_mass_sensitivity import evaluate_mass_pair, fingerprint
finally:
    sys.path.pop(0)


FIT_HOVER_W = 758.0
# Mechanical scale after DATALINK_RPM_SCALE: old raw scale 168 m/s -> ~80 m/s.
FIT_UTIP_MS = 80.0
FIT_V0_MS = math.sqrt(
    12.4 * 9.81 / (2.0 * 1.225 * 4.0 * math.pi * (28.0 * 0.0254 / 2.0) ** 2)
)


def _fit_profile():
    profile = dict(multicopter_range.FIRFIR_SPEED_PRESET)
    profile["utip_ms"] = FIT_UTIP_MS
    return profile


def _synthetic_observations():
    # Synthetic bins generated from a Zeng-shaped ground-truth curve. The fits
    # recover it, letting transfer identity use realistic parameters.
    observations = []
    for speed in [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]:
        ratio = (
            0.82 * multicopter_range.zeng_profile_ratio(speed, FIT_UTIP_MS)
            + 0.18 * multicopter_range.zeng_induced_ratio(speed, FIT_V0_MS)
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
    theoretical = multicopter_range.build_theoretical_zeng_params(profile, FIT_HOVER_W)
    faessler_attitude = {
        "body_cda_fit_m2": 0.15,
        "body_cd_fit": 0.8,
        "lambda_fit_n_per_ms": 1.3,
        "rho": 1.225,
    }
    zeng = multicopter_range.fit_observation_weighted_zeng(
        FIT_V0_MS, FIT_UTIP_MS, FIT_HOVER_W, theoretical, None, observations
    )
    faessler = multicopter_range.fit_faessler_drag_constrained_zeng(
        FIT_V0_MS,
        FIT_UTIP_MS,
        FIT_HOVER_W,
        theoretical,
        faessler_attitude,
        None,
        observations=observations,
    )
    kirschstein = multicopter_range.fit_kirschstein_all_data(
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
                lambda v, p=zeng: multicopter_range.power_ratio_bauersfeld_anchored_zeng(v, p)
            ),
            "faessler_datalink_fit": (
                lambda v, p=faessler: (
                    multicopter_range.power_ratio_faessler_drag_constrained_zeng(v, p)
                )
            ),
            "kirschstein_datalink_fit": (
                lambda v, p=kirschstein: multicopter_range.power_ratio_kirschstein_all_data(v, p)
            ),
        },
    }


def _grid():
    return [0.25 * i for i in range(1, 101)]


# --- Phase 3 corrections ---------------------------------------------------


def test_fit_observation_weighted_zeng_empty_observations_has_no_keyerror():
    profile = _fit_profile()
    theoretical = multicopter_range.build_theoretical_zeng_params(profile, FIT_HOVER_W)

    params = multicopter_range.fit_observation_weighted_zeng(
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
    theoretical = multicopter_range.build_theoretical_zeng_params(profile, FIT_HOVER_W)
    attitude_fit = {"cda_m2": 0.30, "rho": 1.225, "speed_bins": []}

    params = multicopter_range.fit_observation_weighted_zeng(
        FIT_V0_MS, FIT_UTIP_MS, FIT_HOVER_W, theoretical, attitude_fit, []
    )

    assert params["k_par"] == pytest.approx(0.5 * 1.225 * 0.30 / FIT_HOVER_W)


def test_resolve_fit_power_reference_prefers_measured_then_fit_profile():
    fit_profile = {"theoretical_hover_power_w": 1124.0}

    assert (
        multicopter_range.resolve_fit_power_reference(757.9, fit_profile, 999.0) == 757.9
    )
    # Without measured hover, use the fit aircraft's theoretical hover rather
    # than the entered aircraft's power; avoid silent normalization to a wrong reference.
    assert multicopter_range.resolve_fit_power_reference(None, fit_profile, 999.0) == 1124.0
    assert multicopter_range.resolve_fit_power_reference(None, {}, 999.0) == 999.0


# --- Phase 4: physical parameter transfer ---------------------------------


def test_kirschstein_hover_profile_power_uses_same_disc_area_as_zeng():
    profile = _fit_profile()
    kirschstein = multicopter_range.build_kirschstein_params(profile, FIT_HOVER_W)
    zeng = multicopter_range.build_theoretical_zeng_params(profile, FIT_HOVER_W)

    # Both models share rho * total_disc_area * Utip^3 * solidity * drag / 8.
    # Using a radius instead of area in either path violates their common
    # dimensional power basis and this cross-model consistency check.
    assert kirschstein["p_profile_hover_w"] == pytest.approx(zeng["p0_mech"])
    assert multicopter_range.power_kirschstein_component(0.0, kirschstein) == pytest.approx(FIT_HOVER_W)


@pytest.mark.parametrize("diameter_factor", [0.5, 2.0])
def test_kirschstein_profile_power_scales_with_disc_area_in_build_and_transfer(diameter_factor):
    profile = _fit_profile()
    suite = _fitted_suite()
    fitted = suite["model_params"]["kirschstein_datalink_fit"]
    resized = dict(profile, prop_diameter_inch=profile["prop_diameter_inch"] * diameter_factor)

    rebuilt = multicopter_range.build_kirschstein_params(resized, FIT_HOVER_W)
    transferred = multicopter_range.transfer_kirschstein_params_to_vehicle(
        fitted, FIT_HOVER_W * 2, resized, FIT_UTIP_MS
    )

    # At fixed tip speed, doubling radius quadruples profile power. Both the
    # direct builder and the transfer must obey this law, independent of lift.
    expected_ratio = diameter_factor**2
    assert rebuilt["p_profile_hover_w"] / fitted["p_profile_hover_w"] == pytest.approx(expected_ratio)
    assert transferred["p_profile_hover_w"] / fitted["p_profile_hover_w"] == pytest.approx(expected_ratio)


def test_transfer_identity_reproduces_fit_vehicle_curves():
    suite = _fitted_suite()
    apply_profile = {
        "vehicle_name": "Firfir (identity)",
        "mass_kg": 12.4,
        "num_rotors": 4,
        "prop_diameter_inch": 28.0,
        "rho": 1.225,
    }

    transfer = multicopter_range.build_transferred_model_suite(suite, apply_profile)

    assert transfer["apply_utip_ms"] == pytest.approx(FIT_UTIP_MS)
    for name in ("zeng_datalink_fit", "faessler_datalink_fit"):
        original = suite["model_functions"][name]
        rebuilt = transfer["model_functions"][name]
        for speed in _grid():
            assert rebuilt(speed) == pytest.approx(original(speed), abs=1e-9), name
    # Kirschstein is rebased consistently at aircraft level; identity is reached
    # with a small refit residual.
    original = suite["model_functions"]["kirschstein_datalink_fit"]
    rebuilt = transfer["model_functions"]["kirschstein_datalink_fit"]
    max_residual = max(abs(rebuilt(v) - original(v)) for v in _grid())
    assert max_residual < 0.02


def test_transfer_mass_changes_curve_shape_not_just_scale():
    suite = _fitted_suite()
    heavy_profile = {
        "vehicle_name": "Heavy aircraft",
        "mass_kg": 24.8,
        "num_rotors": 4,
        "prop_diameter_inch": 28.0,
        "rho": 1.225,
    }

    transfer = multicopter_range.build_transferred_model_suite(suite, heavy_profile)

    zeng = transfer["model_params"]["zeng_datalink_fit"]
    # Mass 2x -> disc loading 2x -> v0 increases by sqrt(2).
    assert zeng["v0_ms"] == pytest.approx(FIT_V0_MS * math.sqrt(2.0), rel=1e-6)
    # Induced power grows with W^1.5, so predicted hover exceeds the fit aircraft.
    assert zeng["transfer"]["hover_power_pred_w"] > FIT_HOVER_W * 2

    frozen = suite["model_functions"]["zeng_datalink_fit"]
    rebuilt = transfer["model_functions"]["zeng_datalink_fit"]
    # Curve shape changes, not only scale. If the curves were proportional, the
    # rebuilt/frozen ratio would be equal at every speed.
    ratio_low = rebuilt(5.0) / frozen(5.0)
    ratio_high = rebuilt(15.0) / frozen(15.0)
    assert abs(ratio_low - ratio_high) > 0.005

    def optimum_range_speed(fn):
        return min(_grid(), key=lambda v: fn(v) / v)

    # A heavier aircraft shifts best-range speed upward, unlike a frozen shape.
    assert optimum_range_speed(rebuilt) > optimum_range_speed(frozen)


def test_mass_study_preserves_hover_change_on_shared_source_reference():
    suite = _fitted_suite()
    result = evaluate_mass_pair(suite, 13.0, [{"speed_ms": 0.0, "power_ratio": 1.0}])
    hover_ratio = result["bench_target_over_source_hover_power"]

    # Renormalizing target measurements by a hypothetical target hover would
    # hide this mass-driven difference. The source reference must stay fixed.
    assert hover_ratio > 1.0
    for values in result["models"].values():
        assert values["predicted_ratio_on_source_hover"][0] == pytest.approx(hover_ratio)
        assert values["bench_anchored_transfer"]["percent_residual"][0] < 0
        assert values["api_hover_prediction_on_source_reference"] > 1.0
        assert values["api_physical_predicted_ratio"][0] == pytest.approx(
            values["API_internal_target_over_source_hover_power"]
        )
        # The physical component model and manufacturer electrical table are
        # separate hover hypotheses and must not silently overwrite each other.
        assert values["API_internal_target_over_source_hover_power"] != pytest.approx(hover_ratio)


def test_mass_study_identity_diagnostic_preserves_original_and_source_parameters():
    suite = _fitted_suite()
    before = fingerprint(suite["model_params"])
    observations = [{"speed_ms": v, "power_ratio": 1.0} for v in (0.0, 8.0, 17.0)]
    result = evaluate_mass_pair(suite, 12.4, observations)

    for name, values in result["models"].items():
        expected = [suite["model_functions"][name](r["speed_ms"]) for r in observations]
        assert values["identity_anchored_predicted_ratio"] == pytest.approx(expected, abs=1e-12)
        assert values["api_identity_anchored_predicted_ratio"] == pytest.approx(expected, abs=1e-12)
        assert values["mass_effect_ratio_vs_same_mass_transfer"] == pytest.approx([1.0] * 3)
    evaluate_mass_pair(suite, 13.0, observations)
    assert fingerprint(suite["model_params"]) == before


def test_theoretical_utip_similarity_identity_and_scaling():
    identity = multicopter_range.estimate_theoretical_utip_similarity(
        12.4, 4, 28.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    assert identity["utip_ms"] == pytest.approx(FIT_UTIP_MS)
    assert identity["pct_diff_vs_fit"] == pytest.approx(0.0, abs=1e-9)

    # At equal mass, a 29-inch prop turns slower for equal thrust: Utip x 28/29.
    g29 = multicopter_range.estimate_theoretical_utip_similarity(
        12.4, 4, 29.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    assert g29["utip_ms"] == pytest.approx(FIT_UTIP_MS * 28.0 / 29.0)
    assert g29["rpm"] == pytest.approx(
        g29["utip_ms"] * 60.0 / (math.pi * 29.0 * 0.0254)
    )

    # Mass 2x -> per-rotor thrust 2x -> Utip increases by sqrt(2).
    heavy = multicopter_range.estimate_theoretical_utip_similarity(
        24.8, 4, 28.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    assert heavy["utip_ms"] == pytest.approx(FIT_UTIP_MS * math.sqrt(2.0))


def test_theoretical_utip_datasheet_identity_and_scale_discovery():
    # Identity at the fit point: the same aircraft returns the fitted Utip exactly.
    identity = multicopter_range.estimate_theoretical_utip_datasheet(
        12.4, 4, 28.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    assert identity["utip_ms"] == pytest.approx(FIT_UTIP_MS)
    assert identity["pct_diff_vs_fit"] == pytest.approx(0.0, abs=1e-9)

    # Absolute datasheet values: 3100 g @ G28x9.2 -> ~2216 RPM, ~82 m/s.
    assert identity["fit_rpm_datasheet"] == pytest.approx(2216.3, abs=1.0)
    assert identity["fit_utip_datasheet_ms"] == pytest.approx(82.5, abs=0.5)
    # Scale is ~1.0 after parser DATALINK_RPM_SCALE correction (80 / 82.5 = 0.97).
    assert 0.9 < identity["datalink_scale"] < 1.05

    # For a 29-inch prop at equal mass, the ratio comes from datasheet curves.
    g29 = multicopter_range.estimate_theoretical_utip_datasheet(
        12.4, 4, 29.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    rpm_g29, _ = multicopter_range.datasheet_rpm_from_thrust(29.0, 3100.0)
    expected_ratio = (rpm_g29 * 29.0) / (identity["fit_rpm_datasheet"] * 28.0)
    assert g29["utip_ms"] == pytest.approx(FIT_UTIP_MS * expected_ratio)


def test_datasheet_rpm_table_requires_supported_prop():
    with pytest.raises(ValueError):
        multicopter_range.datasheet_rpm_from_thrust(30.0, 3000.0)


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
            "battery_basis": multicopter_range.build_july3_firfir_battery_basis(),
            "sync_report": [],
            "source_result": {"graph_paths": {}},
        }
    )
    monkeypatch.setattr(
        multicopter_range,
        "build_datalink_fitted_model_suite",
        lambda *_args, **_kwargs: suite,
    )
    monkeypatch.setattr(
        multicopter_range,
        "write_datalink_fit_method_report",
        lambda *_args, **_kwargs: tmp_path / "report.md",
    )
    fit_profile = _fit_profile()
    fake_result = {
        "optimal_endurance_speed_ms": 6.6,
        "optimal_speed_ms": 10.7,
        "vi_h": FIT_V0_MS,
    }
    apply_profile = {
        "vehicle_name": "Simulation aircraft",
        "mass_kg": 18.6,
        "num_rotors": 4,
        "prop_diameter_inch": 29.0,
        "rho": 1.225,
    }

    result = multicopter_range.run_preset_fit_apply_to_vehicle(
        [6.0],
        fit_profile,
        fake_result,
        "1",
        1500.0,
        1198.8,
        0.72,
        make_graph=False,
        apply_result=fake_result,
        apply_profile=apply_profile,
        apply_utip_mode="theoretical_datasheet",
    )

    expected = multicopter_range.estimate_theoretical_utip_datasheet(
        18.6, 4, 29.0, 12.4, 4, 28.0, FIT_UTIP_MS
    )
    out = capsys.readouterr().out
    assert "THEORETICAL TIP SPEED" in out
    assert "Datasheet mechanical RPM" in out
    assert f"Applied fit-anchored tip speed = {expected['utip_ms']:.1f} m/s" in out
    assert f"%{expected['pct_diff_vs_fit']:+.1f}" in out
    # datalink_scale ~0.97 after parser correction, so no scale warning is expected.
    assert "WARNING: DataLink tip speed" not in out
    # Theoretical Utip is passed into the transfer.
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
        multicopter_range.build_transferred_model_suite(
            suite, {"mass_kg": 12.4, "num_rotors": 4, "prop_diameter_inch": 28.0}
        )
