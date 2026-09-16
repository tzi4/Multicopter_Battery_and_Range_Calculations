"""Explore separate July 3 and July 21 masses on a fixed 12.4--13 kg grid.

This retrospective comparison is not an independent validation or a mass
measurement. It preserves the calibration observations and all nine comparison
bins, and reports every source/target pair rather than only the best score.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import statistics

import multicopter_range as model

from reproduce_calibration import build_calibration_suite, check_summary, sha256
from reproduce_validation import load_samples, VARIANTS


MASS_GRID_KG = tuple(i / 10 for i in range(124, 131))
COMPARISON_VARIANT = "current_scalar_accel_gate"
IDENTITY_SPEED_GRID_MS = tuple(i / 4 for i in range(101))
METHODS = (
    "bench_anchored_transfer", "bench_identity_anchored_diagnostic",
    "api_physical_transfer", "api_identity_anchored_diagnostic",
)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def metrics(observed, predicted):
    if not observed or len(observed) != len(predicted):
        raise ValueError("Metrics require matching, nonempty observations and predictions")
    if not all(math.isfinite(p) and p > 0 for p in predicted):
        raise ValueError("A transferred prediction is nonpositive or nonfinite")
    residuals = [100.0 * (y / p - 1.0) for y, p in zip(observed, predicted)]
    return {
        "percent_residual": residuals,
        "unweighted_mean_absolute_percent": statistics.fmean(abs(r) for r in residuals),
        "median_percent": statistics.median(residuals),
        "max_absolute_percent": max(abs(r) for r in residuals),
    }


def bench_hover_w(mass_kg, diameter):
    table = model.u8lite_kv190_g29_data if diameter == 29 else model.u8lite_kv190_data
    return 4 * model.get_power_from_thrust(mass_kg * 1000 / 4, table)


def refit_source_mass(base, source_mass):
    """Reuse measured observations; rebuild each mass-dependent July 3 prior."""
    profile = copy.deepcopy(base["model_profile"])
    profile["mass_kg"] = source_mass
    profile["cda_pitch_m2"] = model.estimate_cda_from_pitch(
        profile["pitch_measurement_speed_ms"], profile["pitch_measurement_deg"],
        source_mass, profile["rho"],
    )
    profile["cda_body_m2"] = profile["cda_pitch_m2"]
    hover_w = bench_hover_w(source_mass, profile["prop_diameter_inch"])
    profile["theoretical_hover_power_w"] = hover_w
    reference = model.BauersfeldRangeCalculator(
        hover_w, 1.0, base["battery_basis"]["usable_energy_wh"], source_mass,
        450.0, profile["prop_diameter_inch"], profile["num_rotors"],
    ).solve()
    fitted = model.build_measured_curve_model_fit(
        profile, reference, base["power_reference_w"], copy.deepcopy(base["observations"])
    )
    suite = {
        "model_profile": fitted["profile"], "utip_ms": fitted["profile"]["utip_ms"],
        "power_reference_w": base["power_reference_w"],
        "battery_parallel_arms": base["battery_parallel_arms"],
        "model_params": {}, "model_functions": {}, "calibration_bin_mae": {},
    }
    for family in ("zeng", "faessler", "kirschstein"):
        measured, public = f"{family}_measured_fit", f"{family}_datalink_fit"
        suite["model_params"][public] = dict(
            fitted[f"{family}_params"], public_model_name=public, source_model_name=measured
        )
        suite["model_functions"][public] = fitted["model_functions"][measured]
        suite["calibration_bin_mae"][public] = statistics.fmean(
            abs(row["error"]) for row in fitted["model_fit_residuals"][measured]
        )
    return suite


def evaluate_mass_pair(suite, target_mass, observations, identity=None):
    """Keep the observed July 3 hover reference while changing target geometry.

    The API provides the target curve shape and its own internal hover estimate.
    This experiment explicitly anchors target electrical hover to the bench
    target/source power ratio, assuming unchanged electrical gain. These are
    different assumptions; both hover ratios are retained in the output.
    """
    source = suite["model_profile"]
    target = dict(source, mass_kg=target_mass)
    diameter = source["prop_diameter_inch"]
    source_rpm, _ = model.datasheet_rpm_from_thrust(diameter, source["mass_kg"] * 1000 / 4)
    target_rpm, _ = model.datasheet_rpm_from_thrust(diameter, target_mass * 1000 / 4)
    rpm_ratio = target_rpm / source_rpm
    hover_ratio = bench_hover_w(target_mass, diameter) / bench_hover_w(source["mass_kg"], diameter)
    target_utip = suite["utip_ms"] * rpm_ratio
    transfer = model.build_transferred_model_suite(suite, target, apply_utip_ms=target_utip)
    if identity is None:
        identity = model.build_transferred_model_suite(suite, source, apply_utip_ms=suite["utip_ms"])
    speeds = [row["speed_ms"] for row in observations]
    observed = [row["power_ratio"] for row in observations]
    result = {
        "source_mass_kg": source["mass_kg"], "target_mass_kg": target_mass,
        "bench_target_over_source_rpm": rpm_ratio,
        "bench_target_over_source_hover_power": hover_ratio,
        "source_tip_speed_ms": suite["utip_ms"], "target_tip_speed_ms": target_utip,
        "assumed_target_hover_on_ESC_sum_basis_w": suite["power_reference_w"] * hover_ratio,
        "models": {},
    }
    for name, fn in transfer["model_functions"].items():
        original = suite["model_functions"][name]
        same_mass = identity["model_functions"][name]
        predicted = [hover_ratio * fn(v) for v in speeds]
        internal_hover_ratio = (
            transfer["model_params"][name]["transfer"]["hover_power_pred_w"]
            / transfer["fit_hover_power_vehicle_w"]
        )
        api_predicted = [internal_hover_ratio * fn(v) for v in speeds]
        # Remove the API's same-mass reconstruction discrepancy as a separately
        # labeled diagnostic. This leaves the original source curve unchanged
        # for identity, without fitting any further coefficients to July 21.
        anchored = [original(v) * hover_ratio * fn(v) / same_mass(v) for v in speeds]
        api_anchored = [original(v) * internal_hover_ratio * fn(v) / same_mass(v) for v in speeds]
        result["models"][name] = {
            "predicted_ratio_on_source_hover": predicted,
            "bench_anchored_transfer": metrics(observed, predicted),
            "identity_anchored_predicted_ratio": anchored,
            "bench_identity_anchored_diagnostic": metrics(observed, anchored),
            "api_physical_predicted_ratio": api_predicted,
            "api_physical_transfer": metrics(observed, api_predicted),
            "api_identity_anchored_predicted_ratio": api_anchored,
            "api_identity_anchored_diagnostic": metrics(observed, api_anchored),
            "mass_effect_ratio_vs_same_mass_transfer": [hover_ratio * fn(v) / same_mass(v) for v in speeds],
            "hover_prediction_on_source_reference": hover_ratio * fn(0.0),
            "api_hover_prediction_on_source_reference": internal_hover_ratio * fn(0.0),
            "API_internal_target_over_source_hover_power": internal_hover_ratio,
        }
    return result


def fixed_observations(validation_root, reference):
    samples, provenance = load_samples(validation_root, reference, 29.0)
    selection = VARIANTS[COMPARISON_VARIANT]
    selected = [row for row in samples if row["phase"] == selection["phase"]
                and 2.0 <= row["speed_ms"] <= 20.0
                and abs(row["accel_ms2"]) <= selection["max_scalar_acceleration_ms2"]]
    bins = model.build_datalink_speed_observations(
        selected, min_speed_ms=2.0, max_speed_ms=20.0, bin_width_ms=1.0,
        min_samples=80, power_reference_w=reference, stable_only=True,
        min_stable_fraction=0.5, extrapolation_start_ms=None,
    )
    if len(bins) != 9:
        raise ValueError(f"This fixed study requires the established nine bins; got {len(bins)}")
    return bins, provenance, len(selected)


def reproduce(calibration_root, validation_root, output_dir):
    calibration_root, validation_root = calibration_root.resolve(), validation_root.resolve()
    base = build_calibration_suite(calibration_root, mass_kg=12.4, prop_diameter_inch=29.0)
    bins, provenance, selected_count = fixed_observations(validation_root, base["power_reference_w"])
    frozen_observations = fingerprint(base["observations"])
    frozen_bins = fingerprint(bins)
    source_fits, scenarios = [], []
    for source_mass in MASS_GRID_KG:
        print(f"Refitting July 3 source mass {source_mass:.1f} kg; all measured observations fixed.", flush=True)
        suite = refit_source_mass(base, source_mass)
        frozen_parameters = fingerprint(suite["model_params"])
        if source_mass == 12.4:
            for name, fn in suite["model_functions"].items():
                if max(abs(fn(v) - base["model_functions"][name](v)) for v in IDENTITY_SPEED_GRID_MS) > 1e-9:
                    raise RuntimeError("Reusing observations changed the nominal calibration")
        identity = model.build_transferred_model_suite(
            suite, suite["model_profile"], apply_utip_ms=suite["utip_ms"]
        )
        source_entry = {
            "source_mass_kg": source_mass, "source_hover_ESC_sum_reference_w": suite["power_reference_w"],
            "source_tip_speed_ms": suite["utip_ms"],
            # Nested diagnostic structures include local paths and duplicate
            # observations. All scalar fitted coefficients are kept as numbers
            # so golden checks tolerate normal cross-Python float variation.
            "model_scalar_parameters": {
                name: {key: value for key, value in params.items()
                       if value is None or isinstance(value, (str, int, float, bool))}
                for name, params in suite["model_params"].items()
            },
            "calibration_bin_mae": suite["calibration_bin_mae"], "models": {},
        }
        for name, fn in suite["model_functions"].items():
            transferred = identity["model_functions"][name]
            maximum = max(abs(transferred(v) - fn(v)) for v in IDENTITY_SPEED_GRID_MS)
            if name != "kirschstein_datalink_fit" and maximum > 1e-9:
                raise RuntimeError(f"Same-mass transfer identity failed for {name}")
            predicted = [fn(row["speed_ms"]) for row in bins]
            source_entry["models"][name] = {
                "untransferred_predicted_ratio": predicted,
                "untransferred": metrics([row["power_ratio"] for row in bins], predicted),
                "same_mass_transfer_max_absolute_ratio_difference_0_to_25_ms": maximum,
                "same_mass_transfer_difference_at_comparison_bins": [transferred(row["speed_ms"]) - fn(row["speed_ms"]) for row in bins],
            }
        source_fits.append(source_entry)
        scenarios.extend(evaluate_mass_pair(suite, target, bins, identity) for target in MASS_GRID_KG)
        if fingerprint(suite["model_params"]) != frozen_parameters:
            raise RuntimeError("Target evaluation changed source calibration coefficients")
    if fingerprint(base["observations"]) != frozen_observations or fingerprint(bins) != frozen_bins:
        raise RuntimeError("The mass study changed its fixed observations")
    names = sorted(base["model_functions"])
    best = {}
    for method in METHODS:
        best[method] = {}
        for name in names:
            row = min(scenarios, key=lambda s: s["models"][name][method]["unweighted_mean_absolute_percent"])
            best[method][name] = {
                "source_mass_kg": row["source_mass_kg"], "target_mass_kg": row["target_mass_kg"],
                **row["models"][name][method],
            }
    summary = {
        "schema_version": 1, "package_version": version("multicopter-range"),
        "scope": "Retrospective bounded configuration comparison; neither inferred mass nor independent validation.",
        "module_sha256": sha256(Path(model.__file__)), "analysis_script_sha256": sha256(Path(__file__)),
        "calibration_script_sha256": sha256(Path(__file__).with_name("reproduce_calibration.py")),
        "validation_script_sha256": sha256(Path(__file__).with_name("reproduce_validation.py")),
        "calibration_input_sha256": {p.relative_to(calibration_root).as_posix(): sha256(p) for p in sorted(calibration_root.rglob("*")) if p.is_file() and p.suffix.lower() in {".bin", ".udat", ".csv"}},
        "validation_input_sha256": {name: sha256(validation_root / name) for name in ("joined-samples.csv.gz", "provenance.json")},
        "method": {
            "source_mass_grid_kg": list(MASS_GRID_KG), "target_mass_grid_kg": list(MASS_GRID_KG),
            "scenario_count": len(scenarios), "propeller": "G29x9.5", "motor": "U8 Lite KV190", "rotor_count": 4,
            "air_density_kg_m3": base["model_profile"]["rho"],
            "manufacturer_source": "https://store.tmotor.com/product/u8-lite-u-efficiency-kv190.html",
            "source_fit": "Parse July 3 once; reuse identical observed speed/power/RPM bins, weights and measured hover. Recompute mass-dependent physics and attitude priors for each source mass; refit July 3 only.",
            "target_tip_speed": "Measured source Utip * manufacturer target/source RPM at equal per-rotor static thrust; no target RPM fit.",
            "target_hover": "July3 ESC-sum hover * manufacturer target/source hover power ratio; assumes the same electrical gain. This external hover anchor replaces the transfer API's internal absolute-hover estimate, which is reported separately.",
            "prediction": "(bench target hover / bench source hover) * transferred P(v)/P_hover_target; measurements remain divided by the same measured July3 hover.",
            "api_physical_alternative": "Use each model transfer's own target/source hover ratio instead of the bench ratio, preserving its rebuilt absolute components and the same July3 electrical reference. Reported separately; neither electrical/hover interpretation is selected by its error.",
            "transfer_electrical_multiplier": base["battery_parallel_arms"],
            "transfer_electrical_status": "Historical API x2 convention held fixed, not inferred from parallel pack count or optimized. Its physical basis is unverified and affects Kirschstein rebasing.",
            "identity_anchored_diagnostic": "Original source ratio * target transferred ratio / same-mass transferred ratio * the corresponding bench or API hover ratio. Separates mass response from the transfer API's same-mass reconstruction discrepancy; not another calibration.",
            "identity_audit_speed_grid_ms": list(IDENTITY_SPEED_GRID_MS),
            "comparison_variant": COMPARISON_VARIANT, "selected_before_stable_gate_count": selected_count,
            "comparison_bin_count": len(bins), "derived_sample_count": provenance["row_count"],
            "residual": "100*(observed/predicted-1); mean absolute residual gives every retained bin equal weight.",
            "selection_status": "All nine established bins retained; no clock, filter, sensor gain, propeller or aerodynamic coefficient retuning against July 21.",
            "best_score_status": "Minimum on the reported discrete 0.1kg grid, selected after inspecting July21 errors; not a continuous optimum, weighed mass, or independent validation score.",
        },
        "fixed_calibration_observations": [
            {key: row[key] for key in ("speed_ms", "power_ratio", "utip_ms", "weight", "sample_count", "raw_sample_count", "power_w")}
            for row in base["observations"]
        ],
        "fixed_comparison_bins": [{key: row[key] for key in ("speed_ms", "power_ratio", "sample_count", "raw_sample_count", "power_w")} for row in bins],
        "source_fits": source_fits, "scenarios": scenarios, "best_grid_scores": best,
        "invariants": {"nominal_refit_matches_original_within_1e_9": True, "zeng_faessler_same_mass_transfer_within_1e_9": True, "calibration_observations_unchanged": True, "comparison_bins_unchanged": True, "source_parameters_unchanged_by_target_evaluation": True},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "mass-transfer-sensitivity.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for method, results in best.items():
        for name, result in results.items():
            print(f"{method} {name}: source {result['source_mass_kg']:.1f} / target {result['target_mass_kg']:.1f} kg, mean absolute residual {result['unweighted_mean_absolute_percent']:.6f}%")
    return summary


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--validation-root", type=Path, default=root / "data/validation/2026-07-21")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--check-summary", type=Path)
    args = parser.parse_args()
    try:
        expected = json.loads(args.check_summary.read_text(encoding="utf-8")) if args.check_summary else None
        summary = reproduce(args.data_root, args.validation_root, args.output_dir)
        if expected is not None:
            check_summary(summary, expected)
            print("Mass study matches (exact provenance; numeric tolerance 1e-9).")
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
