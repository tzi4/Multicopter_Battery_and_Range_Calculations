"""Rebuild a compact audit from the public July 3 inputs; no raw data is exported.

Install the project first. Works with an editable install or an installed wheel.
"""

import argparse
import csv
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path

import multicopter_range as model


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_summary(actual, expected, path="summary"):
    """Compare provenance exactly and floating-point results within 1e-9."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if actual.keys() != expected.keys():
            raise ValueError(f"{path}: summary fields differ")
        for key in expected:
            check_summary(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(actual) != len(expected):
            raise ValueError(f"{path}: lengths differ")
        for index, (value, reference) in enumerate(zip(actual, expected)):
            check_summary(value, reference, f"{path}[{index}]")
    elif isinstance(expected, float) and isinstance(actual, (int, float)):
        if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError(f"{path}: {actual!r} != {expected!r}")
    elif actual != expected:
        raise ValueError(f"{path}: {actual!r} != {expected!r}")


def build_calibration_suite(data_root, mass_kg=12.4, prop_diameter_inch=29.0):
    """Fit July 3 with explicitly declared geometry; preserve the legacy CLI preset."""
    data_root = data_root.resolve()
    if not math.isfinite(mass_kg) or mass_kg <= 0:
        raise ValueError("mass must be finite and positive")
    if prop_diameter_inch not in (28.0, 29.0):
        raise ValueError("this experiment supports the G28 and G29 manufacturer tables")
    profile = model.build_speed_model_profile("1", 12.4, 4, 28.0, 450.0)
    original_diameter = profile["prop_diameter_inch"]
    profile.update(mass_kg=mass_kg, prop_diameter_inch=prop_diameter_inch)
    profile["cda_pitch_m2"] = model.estimate_cda_from_pitch(
        profile["pitch_measurement_speed_ms"], profile["pitch_measurement_deg"],
        mass_kg, profile["rho"],
    )
    profile["cda_body_m2"] = profile["cda_pitch_m2"]
    profile["utip_ms"] *= prop_diameter_inch / original_diameter
    profile["utip_from_rpm_ms"] = model.tip_speed_from_rpm(
        prop_diameter_inch, profile["hover_rpm_estimate"]
    )
    table = model.u8lite_kv190_g29_data if prop_diameter_inch == 29 else model.u8lite_kv190_data
    hover_w = model.get_power_from_thrust(mass_kg * 1000 / 4, table) * 4
    profile["theoretical_hover_power_w"] = hover_w
    profile["attitude_log_csv"] = data_root / "flight_attitude.csv"
    required = [data_root / name for name in ("00000076.BIN", "00000077.BIN", "flight_attitude.csv")]
    if any(not path.is_file() for path in required) or not (data_root / "Datalink").is_dir():
        raise ValueError("--data-root must contain the complete public July 3 calibration data")
    # This energy basis is inherited from the archive, not measured by this run.
    basis_wh = model.build_july3_firfir_battery_basis()["usable_energy_wh"]
    reference = model.BauersfeldRangeCalculator(
        hover_w, 1.0, basis_wh, mass_kg, 450.0, prop_diameter_inch, 4
    ).solve()
    return model.build_datalink_fitted_model_suite(
        profile, reference, hover_w, basis_wh, 1.0,
        log_root=data_root, date_hint="260703",
    )


def reproduce(data_root, output_dir, mass_kg=12.4, prop_diameter_inch=29.0):
    data_root = data_root.resolve()
    suite = build_calibration_suite(data_root, mass_kg, prop_diameter_inch)
    profile = suite["model_profile"]
    result = suite["source_result"]
    arms = suite["battery_parallel_arms"]
    branch_wh = suite["battery_basis"]["usable_energy_wh"]
    branch_w = suite["measured_hover_power_w"]
    integrated_wh = suite["battery_qc_report"]["datalink_energy_wh"]
    summary = {
        "schema_version": 2,
        "scope": "July 3 calibration reproduction; not independent flight validation",
        "package_version": version("multicopter-range"),
        "module_sha256": sha256(Path(model.__file__)),
        "reproduction_script_sha256": sha256(Path(__file__)),
        "input_sha256": {
            path.relative_to(data_root).as_posix(): sha256(path)
            for path in sorted(data_root.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".bin", ".udat", ".csv"}
        },
        "profile": {key: profile[key] for key in ("mass_kg", "num_rotors", "prop_diameter_inch")},
        "configuration_status": f"Declared {prop_diameter_inch:g}-inch propeller and {mass_kg:g} kg mass. Owner selected G29 for the showcase; actual mass may differ between flights (12.4, 12.8 or 13 kg). These inputs are not inferred measurements.",
        "electrical_status": "Power is the sum of four ESC V*I slots. The historical x2 vehicle conversion is conditional on unverified sensor wiring; parallel pack count alone does not establish it.",
        "joined_samples": result["joined_sample_count"],
        "stable_samples": suite["empirical_curve"]["sample_count_total"],
        "rpm_scale": model.DATALINK_RPM_SCALE,
        "tip_speed_ms": suite["utip_ms"],
        "tip_speed_before_rpm_conversion_ms": suite["utip_ms"] / model.DATALINK_RPM_SCALE,
        "hover_esc_sum_power_w": branch_w,
        "integrated_esc_sum_energy_wh": integrated_wh,
        "historical_energy_power_scenario": {
            "assumed_multiplier": arms,
            "usable_energy_basis_wh": branch_wh,
            "conditional_vehicle_hover_w": branch_w * arms,
            "conditional_vehicle_energy_wh": branch_wh * arms,
            "hover_10_percent_reserve_min": suite["battery_reserve_report"]["hover_10_reserve_min"],
        },
        "battery_direct_current_fit_enabled": suite["battery_qc_report"]["direct_current_fit_enabled"],
        "battery_warnings": suite["battery_qc_report"]["warnings"],
        "calibration_bin_mae": {
            name: sum(abs(row["error"]) for row in rows) / len(rows)
            for name, rows in result["model_fit_residuals"].items()
        },
        "bins": [
            {**{key: obs[key] for key in ("speed_ms", "power_ratio", "sample_count", "raw_sample_count")},
             "predicted_ratio": {name: fn(obs["speed_ms"]) for name, fn in suite["model_functions"].items()}}
            for obs in suite["observations"]
        ],
        "model_curves": [
            {"speed_ms": i / 10, **{name: fn(i / 10) for name, fn in suite["model_functions"].items()}}
            for i in range(201)
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "calibration-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (output_dir / "calibration-bins.csv").open("w", newline="", encoding="utf-8") as target:
        fields = ["speed_ms", "power_ratio", "sample_count", "raw_sample_count", *suite["model_functions"]]
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for row in summary["bins"]:
            writer.writerow({**{key: row[key] for key in fields[:4]}, **row["predicted_ratio"]})
    model.write_scientific_fit_audit(result, output_dir / "calibration-audit.md")
    audit_path = output_dir / "calibration-audit.md"
    audit_path.write_text(
        "> Interpretation: legacy branch/vehicle labels below assume an unverified sensor layout. "
        "The directly parsed quantity is the four-ESC electrical sum. Geometry and mass are declared experiment inputs.\n\n"
        + audit_path.read_text(encoding="utf-8"), encoding="utf-8",
    )
    print(f"Calibration: {summary['joined_samples']} joined samples; {len(summary['bins'])} stable bins")
    print(f"Utip: {suite['utip_ms']:.6f} m/s; RPM scale: 10/21")
    print(f"Declared geometry: {prop_diameter_inch:g} in, {mass_kg:g} kg, four rotors")
    print(f"Hover ESC electrical sum: {branch_w:.3f} W")
    print("Absolute endurance retains the archive's conditional energy/power scenario.")
    print(f"Summary: {summary_path.resolve()}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prop-diameter", type=float, choices=(28.0, 29.0), default=29.0)
    parser.add_argument("--mass", type=float, default=12.4)
    parser.add_argument("--check-summary", type=Path, help="compare with a saved summary from the same source version")
    args = parser.parse_args()
    try:
        expected = json.loads(args.check_summary.read_text(encoding="utf-8")) if args.check_summary else None
        summary = reproduce(args.data_root, args.output_dir, args.mass, args.prop_diameter)
        if expected is not None:
            check_summary(summary, expected)
            print("Saved summary matches (exact provenance; numeric tolerance 1e-9).")
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
