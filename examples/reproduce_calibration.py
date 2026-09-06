"""Rebuild a compact audit from the public July 3 inputs; no raw data is exported.

Install the project first. Works with an editable install or an installed wheel.
"""

import argparse
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


def reproduce(data_root, output_dir):
    data_root = data_root.resolve()
    # The fixed calibration profile is 12.4 kg, four rotors, 28 inches.
    profile = model.build_speed_model_profile("1", 12.4, 4, 28.0, 450.0)
    profile["attitude_log_csv"] = data_root / "flight_attitude.csv"
    required = [data_root / name for name in ("00000076.BIN", "00000077.BIN", "flight_attitude.csv")]
    if any(not path.is_file() for path in required) or not (data_root / "Datalink").is_dir():
        raise ValueError("--data-root must contain the complete public July 3 calibration data")
    # Retain the CLI's legacy calculation inputs; the fit uses measured branch
    # power, and endurance below uses the explicit 6S1P usable-energy basis.
    hover_w = model.get_power_from_thrust(12400.0 / 4.0, model.u8lite_kv190_g29_data) * 4.0
    legacy_wh = model.calculate_real_energy_wh(12, 27000, "liion")
    reference = model.BauersfeldRangeCalculator(
        hover_w, 0.72, legacy_wh, 12.4, 450.0, 28.0, 4
    ).solve()
    suite = model.build_datalink_fitted_model_suite(
        profile, reference, hover_w, legacy_wh, 0.72,
        log_root=data_root, date_hint="260703",
    )
    result = suite["source_result"]
    arms = suite["battery_parallel_arms"]
    branch_wh = suite["battery_basis"]["usable_energy_wh"]
    branch_w = suite["measured_hover_power_w"]
    integrated_wh = suite["battery_qc_report"]["datalink_energy_wh"]
    summary = {
        "schema_version": 1,
        "scope": "July 3 calibration reproduction; not independent flight validation",
        "package_version": version("multicopter-range"),
        "module_sha256": sha256(Path(model.__file__)),
        "input_sha256": {
            path.relative_to(data_root).as_posix(): sha256(path)
            for path in sorted(data_root.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".bin", ".udat", ".csv"}
        },
        "profile": {key: profile[key] for key in ("mass_kg", "num_rotors", "prop_diameter_inch")},
        "joined_samples": result["joined_sample_count"],
        "stable_samples": suite["empirical_curve"]["sample_count_total"],
        "rpm_scale": model.DATALINK_RPM_SCALE,
        "tip_speed_ms": suite["utip_ms"],
        "tip_speed_before_rpm_conversion_ms": suite["utip_ms"] / model.DATALINK_RPM_SCALE,
        "parallel_branches": arms,
        "hover_power_branch_w": branch_w,
        "hover_power_vehicle_w": suite["vehicle_measured_hover_power_w"],
        "usable_energy_branch_wh": branch_wh,
        "usable_energy_vehicle_wh": suite["full_pack_usable_energy_wh"],
        "integrated_energy_branch_wh": integrated_wh,
        "integrated_energy_vehicle_wh": integrated_wh * arms,
        "hover_10_percent_reserve_min": suite["battery_reserve_report"]["hover_10_reserve_min"],
        "battery_direct_current_fit_enabled": suite["battery_qc_report"]["direct_current_fit_enabled"],
        "battery_warnings": suite["battery_qc_report"]["warnings"],
        "calibration_bin_mae": {
            name: sum(abs(row["error"]) for row in rows) / len(rows)
            for name, rows in result["model_fit_residuals"].items()
        },
        "bins": [
            {key: obs[key] for key in ("speed_ms", "power_ratio", "sample_count", "raw_sample_count")}
            for obs in suite["observations"]
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "calibration-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    model.write_scientific_fit_audit(result, output_dir / "calibration-audit.md")
    print(f"Calibration: {summary['joined_samples']} joined samples; {len(summary['bins'])} stable bins")
    print(f"Utip: {suite['utip_ms']:.6f} m/s; RPM scale: 10/21")
    print(f"Hover power: branch {branch_w:.3f} W; vehicle {branch_w * arms:.3f} W")
    print(f"Usable energy: branch {branch_wh:.2f} Wh; vehicle {branch_wh * arms:.2f} Wh")
    print(f"Hover at 10% reserve: {summary['hover_10_percent_reserve_min']:.6f} min")
    print(f"Summary: {summary_path.resolve()}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--check-summary", type=Path, help="compare with a saved summary from the same source version")
    args = parser.parse_args()
    try:
        expected = json.loads(args.check_summary.read_text(encoding="utf-8")) if args.check_summary else None
        summary = reproduce(args.data_root, args.output_dir)
        if expected is not None:
            check_summary(summary, expected)
            print("Saved summary matches (exact provenance; numeric tolerance 1e-9).")
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
