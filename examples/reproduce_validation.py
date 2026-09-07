"""Replay July 21 derived telemetry against a frozen July 3 calibration.

Uses the installed package and public repository inputs. Mass and propeller
diameter are declared modeling assumptions, not measured aircraft metadata.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import gzip
from importlib.metadata import version
import io
import json
import math
from pathlib import Path
import statistics

import multicopter_range as model
from reproduce_calibration import build_calibration_suite, check_summary, sha256

DEFAULT_VALIDATION_ROOT = Path(__file__).resolve().parents[1] / "data/validation/2026-07-21"
CSV_FIELDS = [
    "elapsed_us", "speed_ms", "vx_ms", "vy_ms", "vertical_speed_ms",
    "roll_deg", "pitch_deg", "esc_sum_power_w", "mechanical_rpm",
    "voltage_v", "match_dt_s", "phase",
]
PHASES = {"first_10_laps", "post_intervention", "off_mission"}
VARIANTS = {
    "current_scalar_accel_gate": {"phase": "first_10_laps", "max_scalar_acceleration_ms2": 1.0},
    "historical_first10": {"phase": "first_10_laps", "max_scalar_acceleration_ms2": None},
    "historical_post_intervention": {"phase": "post_intervention", "max_scalar_acceleration_ms2": None},
}


def load_samples(validation_root, power_reference_w, prop_diameter_inch):
    """Validate the distributed derived samples, preserving their time intervals."""
    import hashlib

    path = validation_root / "joined-samples.csv.gz"
    provenance = json.loads((validation_root / "provenance.json").read_text(encoding="utf-8"))
    if sha256(path) != provenance["compressed_sha256"]:
        raise ValueError("Derived telemetry compressed checksum does not match provenance.json")
    data = gzip.decompress(path.read_bytes())
    if hashlib.sha256(data).hexdigest() != provenance["uncompressed_sha256"]:
        raise ValueError("Derived telemetry CSV checksum does not match provenance.json")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
    if reader.fieldnames != CSV_FIELDS:
        raise ValueError("Unexpected derived telemetry columns")
    # This is an artificial epoch, not a reconstruction of absolute flight UTC.
    epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
    samples = []
    previous_elapsed = -1
    bounds = provenance["extraction"]["phase_bounds_elapsed_us"]
    for raw in reader:
        elapsed = int(raw["elapsed_us"])
        if elapsed < 0 or elapsed < previous_elapsed:
            raise ValueError("Derived elapsed times must be nonnegative and ordered")
        previous_elapsed = elapsed
        numeric = {key: float(raw[key]) for key in CSV_FIELDS[1:-1]}
        if not all(math.isfinite(value) for value in numeric.values()):
            raise ValueError("Derived telemetry contains a nonfinite value")
        if numeric["esc_sum_power_w"] <= 0 or numeric["voltage_v"] <= 0 or numeric["mechanical_rpm"] <= 0:
            raise ValueError("Derived telemetry contains a nonpositive electrical/RPM value")
        if raw["phase"] not in PHASES:
            raise ValueError("Unknown derived telemetry phase")
        if bounds["clean_start_us"] <= elapsed <= bounds["clean_end_us"]:
            expected_phase = "first_10_laps"
        elif bounds["clean_end_us"] < elapsed <= bounds["flight_end_us"]:
            expected_phase = "post_intervention"
        else:
            expected_phase = "off_mission"
        if raw["phase"] != expected_phase:
            raise ValueError("Derived phase disagrees with the recorded interval bounds")
        samples.append({
            "timestamp_utc": epoch + timedelta(microseconds=elapsed),
            "speed_ms": numeric["speed_ms"], "vx_ms": numeric["vx_ms"], "vy_ms": numeric["vy_ms"],
            "vertical_speed_ms": numeric["vertical_speed_ms"],
            "roll_deg": numeric["roll_deg"], "pitch_deg": numeric["pitch_deg"],
            "power_w": numeric["esc_sum_power_w"],
            "power_ratio": numeric["esc_sum_power_w"] / power_reference_w,
            "rpm_median": numeric["mechanical_rpm"],
            "utip_ms": model.tip_speed_from_rpm(prop_diameter_inch, numeric["mechanical_rpm"]),
            "voltage_v": numeric["voltage_v"], "dt_s": numeric["match_dt_s"],
            "phase": raw["phase"], "source_session": "derived-2026-07-21",
        })
    if len(samples) != provenance["row_count"]:
        raise ValueError("Derived row count does not match provenance.json")
    return model.annotate_joined_sample_stability(samples), provenance


def reproduce(calibration_root, validation_root, output_dir, mass_kg=12.4, prop_diameter_inch=29.0):
    calibration_root = calibration_root.resolve()
    validation_root = validation_root.resolve()
    suite = build_calibration_suite(calibration_root, mass_kg=mass_kg, prop_diameter_inch=prop_diameter_inch)
    frozen_parameters = json.dumps(suite["model_params"], sort_keys=True, default=str)
    reference = suite["power_reference_w"]
    samples, provenance = load_samples(validation_root, reference, prop_diameter_inch)
    variants = {}
    csv_rows = []
    for label, selection in VARIANTS.items():
        selected = [row for row in samples if row["phase"] == selection["phase"] and 2.0 <= row["speed_ms"] <= 20.0]
        threshold = selection["max_scalar_acceleration_ms2"]
        if threshold is not None:
            selected = [row for row in selected if abs(row["accel_ms2"]) <= threshold]
        observations = model.build_datalink_speed_observations(
            selected, min_speed_ms=2.0, max_speed_ms=20.0, bin_width_ms=1.0,
            min_samples=80, power_reference_w=reference, stable_only=True,
            min_stable_fraction=0.5, extrapolation_start_ms=None,
        )
        bins = []
        for observation in observations:
            predicted = {name: function(observation["speed_ms"]) for name, function in suite["model_functions"].items()}
            residuals = {name: 100.0 * (observation["power_ratio"] / ratio - 1.0) for name, ratio in predicted.items()}
            row = {
                "speed_ms": observation["speed_ms"], "sample_count": observation["sample_count"],
                "raw_sample_count": observation["raw_sample_count"], "stable_fraction": observation["stable_fraction"],
                "measured_esc_sum_power_w": observation["power_w"], "measured_ratio": observation["power_ratio"],
                "predicted_ratio": predicted, "percent_residual": residuals,
            }
            bins.append(row)
            flat = {"variant": label, **{key: value for key, value in row.items() if not isinstance(value, dict)}}
            for name, ratio in predicted.items():
                flat[f"{name}_predicted_ratio"] = ratio
                flat[f"{name}_residual_percent"] = residuals[name]
            csv_rows.append(flat)
        variants[label] = {
            "selection": selection, "selected_before_stable_gate_count": len(selected),
            "bin_count": len(bins), "bins": bins,
            "residual_summary": {
                name: {
                    "median_percent": statistics.median(row["percent_residual"][name] for row in bins),
                    "unweighted_mean_absolute_percent": statistics.fmean(abs(row["percent_residual"][name]) for row in bins),
                    "max_absolute_percent": max(abs(row["percent_residual"][name]) for row in bins),
                } for name in suite["model_functions"]
            } if bins else {},
        }
    if json.dumps(suite["model_params"], sort_keys=True, default=str) != frozen_parameters:
        raise RuntimeError("Validation mutated the frozen calibration parameters")
    summary = {
        "schema_version": 1,
        "scope": "Public replay of derived July 21 telemetry against current July 3 fitted curves; raw extraction remains a separate provenance step.",
        "package_version": version("multicopter-range"), "module_sha256": sha256(Path(model.__file__)),
        "reproduction_script_sha256": sha256(Path(__file__)),
        "calibration_script_sha256": sha256(Path(__file__).with_name("reproduce_calibration.py")),
        "profile": {"mass_kg": mass_kg, "num_rotors": 4, "prop_diameter_inch": prop_diameter_inch},
        "calibration_input_sha256": {
            path.relative_to(calibration_root).as_posix(): sha256(path)
            for path in sorted(calibration_root.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".bin", ".udat", ".csv"}
        },
        "validation_input_sha256": {name: sha256(validation_root / name) for name in ("joined-samples.csv.gz", "provenance.json")},
        "configuration_assumptions": {
            "calibration_mass_kg": mass_kg, "prop_diameter_inch": prop_diameter_inch,
            "rotor_count": 4, "motor": "U8 Lite KV190",
            "comparison": "Untransferred frozen July 3 ratio curves. July 21 mass/propeller identity is not measured by this file; treating the configuration as shared is an assumption.",
        },
        "calibration": {"joined_samples": suite["source_result"]["joined_sample_count"], "bin_count": len(suite["observations"]),
                        "hover_esc_sum_reference_w": reference, "tip_speed_ms": suite["utip_ms"], "parameters_unchanged_by_validation": True},
        "normalization": "Every July 21 measurement and model prediction uses the July 3 ESC-sum hover reference. This is not normalization by a newly measured July 21 hover. A common multiplicative scale cancels only if it applies consistently to both dates; changes in sensor gain or offset do not cancel.",
        "derived_telemetry": {"row_count": len(samples), "phase_counts": {phase: sum(row["phase"] == phase for row in samples) for phase in sorted(PHASES)},
                              "source_date": provenance["source_date"]},
        "common_selection": {"speed_range_ms": [2.0, 20.0], "bin_width_ms": 1.0, "minimum_samples": 80, "minimum_stable_fraction": 0.5,
                             "stable_gate": "Package defaults: scalar speed acceleration <=8 m/s^2, |vertical speed|<=1.5 m/s, |roll|/|pitch|<=28 degrees."},
        "residual_definition": "100 * (measured_power_ratio / predicted_power_ratio - 1); aggregate mean absolute residual weights each retained bin equally.",
        "variants": variants,
        "limitations": [
            "Historical variant names describe earlier sample selections; all predictions use the current installed package and declared configuration, not historical model coefficients.",
            "The current scalar acceleration gate does not exclude constant-speed turns; wind, mission geometry and attitude estimation remain potential confounders.",
            "Selection and clock alignment were developed after examining the later flight; this is not a prospectively blinded validation.",
            "ESC-slot power is not promoted to independently calibrated vehicle power; cross-flight electrical calibration remains an assumption.",
            "Public replay verifies fitting, selection and residual computation from derived telemetry, not the private raw decoder or physical hardware metadata.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "validation-summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (output_dir / "validation-bins.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]) if csv_rows else ["variant"])
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"Derived telemetry: {len(samples)} samples; assumed {mass_kg:g} kg / {prop_diameter_inch:g}-inch propeller")
    for label, result in variants.items():
        print(f"{label}: {result['bin_count']} bins")
        for name, metrics in result["residual_summary"].items():
            print(f"  {name}: mean absolute residual {metrics['unweighted_mean_absolute_percent']:.6f}%")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", "--calibration-root", dest="calibration_root", type=Path, required=True,
                        help="Public July 3 calibration directory")
    parser.add_argument("--validation-root", type=Path, default=DEFAULT_VALIDATION_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mass", type=float, default=12.4, help="Assumed calibration mass in kg; not an inferred takeoff weight")
    parser.add_argument("--prop-diameter", type=float, choices=(28.0, 29.0), default=29.0, help="Assumed propeller diameter in inches")
    parser.add_argument("--check-summary", type=Path)
    args = parser.parse_args()
    try:
        expected = json.loads(args.check_summary.read_text(encoding="utf-8")) if args.check_summary else None
        summary = reproduce(args.calibration_root, args.validation_root, args.output_dir, mass_kg=args.mass, prop_diameter_inch=args.prop_diameter)
        if expected is not None:
            check_summary(summary, expected)
            print("Saved validation summary matches (exact provenance; numeric tolerance 1e-9).")
    except (ValueError, FileNotFoundError, gzip.BadGzipFile) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
