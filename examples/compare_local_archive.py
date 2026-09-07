"""Compare an optional, trusted local menzil2.py archive with this package.

This audit reads the archive and its July 3 logs without changing them. It is
not needed for normal use; the public result records the author's comparison.
Run from a clone: python examples/compare_local_archive.py /path/to/archive
"""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile

import multicopter_range as current
from flight_workflow import FlightFit, from_calibration_suite


ROOT = Path(__file__).resolve().parents[1]
SPEEDS = [index / 10 for index in range(251)]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_archive(root):
    # Imports execute Python: use only your own trusted source archive.
    spec = importlib.util.spec_from_file_location("local_menzil2_archive", root / "menzil2.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def reference_cf(module):
    energy_wh = module.calculate_real_energy_wh(24, 17000, "lihv")
    hover_w = 4 * module.get_power_from_thrust(19500 / 4, module.p80_thrust_power)
    minutes = 60 * energy_wh / hover_w
    return {"reference_mass_kg": 19.5, "num_rotors": 4,
            "total_cell_equivalents": 24, "capacity_mah": 17000,
            "energy_wh": energy_wh, "hover_power_w": hover_w,
            "theoretical_hover_min": minutes, "recorded_hover_min": 35.0,
            "correction_factor": 35.0 / minutes}


def build_suite(module, root, *, archive, diameter, correction_factor):
    data_root = root / "3 Temmuz Tüm Test Logları" if archive else root / "data/calibration/2026-07-03"
    profile = module.build_speed_model_profile("1", 12.4, 4, 28.0, 450.0)
    original_diameter = profile["prop_diameter_inch"]
    profile["prop_diameter_inch"] = diameter
    profile["utip_ms"] *= diameter / original_diameter
    profile["utip_from_rpm_ms"] = module.tip_speed_from_rpm(diameter, profile["hover_rpm_estimate"])
    table = module.u8lite_kv190_g29_data if diameter == 29 else module.u8lite_kv190_data
    hover_w = 4 * module.get_power_from_thrust(3100, table)
    profile["theoretical_hover_power_w"] = hover_w
    profile["attitude_log_csv"] = root / "flight_attitude_00000075.csv" if archive else data_root / "flight_attitude.csv"
    energy_wh = module.calculate_real_energy_wh(12, 27000, "liion")
    calculator = module.BauersfeldMenzilHesaplayici if archive else module.BauersfeldRangeCalculator
    solved = calculator(hover_w, correction_factor, energy_wh, 12.4, 450.0, diameter, 4).solve()
    with contextlib.redirect_stdout(io.StringIO()):
        suite = module.build_datalink_fitted_model_suite(
            profile, solved, hover_w, energy_wh, correction_factor,
            log_root=data_root, date_hint="260703",
        )
    return solved, suite


def compare_curves(old, new):
    rows = [{"speed_ms": speed, "archive_ratio": old(speed), "current_ratio": new(speed)} for speed in SPEEDS]
    return {"points": len(rows),
            "max_absolute_ratio_difference": max(abs(row["current_ratio"] - row["archive_ratio"]) for row in rows),
            "max_absolute_relative_difference_percent": max(100 * abs(row["current_ratio"] / row["archive_ratio"] - 1) for row in rows),
            "selected_points": [row for row in rows if row["speed_ms"] in (0.0, 6.0, 10.0, 15.0, 17.0, 20.0, 25.0)]}


def input_comparison(archive_root):
    public = ROOT / "data/calibration/2026-07-03"
    rows = []
    for path in sorted(public.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".bin", ".udat", ".csv"}:
            continue
        relative = path.relative_to(public)
        original = archive_root / "flight_attitude_00000075.csv" if relative.as_posix() == "flight_attitude.csv" else archive_root / "3 Temmuz Tüm Test Logları" / relative
        before, after = original.read_bytes(), path.read_bytes()
        rows.append({"public_path": relative.as_posix(), "archive_sha256": sha256(original),
                     "current_sha256": sha256(path), "byte_identical": before == after,
                     "equivalent": before == after or (path.suffix.lower() == ".csv" and before.replace(b"\r\n", b"\n") == after.replace(b"\r\n", b"\n"))})
    return rows


def compare(archive_root):
    original_hash = sha256(archive_root / "menzil2.py")
    archive = load_archive(archive_root)
    cf_old, cf_new = reference_cf(archive), reference_cf(current)
    comparisons = []
    historical_suite = None
    for diameter in (28.0, 29.0):
        print(f"Comparing separate raw-log parses at {diameter:g} inches...", flush=True)
        old_solved, old_suite = build_suite(archive, archive_root, archive=True, diameter=diameter, correction_factor=cf_old["correction_factor"])
        new_solved, new_suite = build_suite(current, ROOT, archive=False, diameter=diameter, correction_factor=cf_old["correction_factor"])
        if diameter == 28:
            historical_suite = old_suite
        curves = {name: compare_curves(old_fn, new_suite["model_functions"][name]) for name, old_fn in old_suite["model_functions"].items()}
        fit = from_calibration_suite(new_suite)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fit.json"
            fit.save(path)
            restored = FlightFit.load(path)
        wrapper_differences = []
        for speed in SPEEDS:
            predicted = restored.predict(speed, hover_power_w=757.891, usable_energy_wh=503.496)
            for name, fn in new_suite["model_functions"].items():
                key = name.removesuffix("_datalink_fit")
                wrapper_differences.append(abs(predicted[key]["power_ratio"] - fn(speed)))
        observations_old = [{key: row[key] for key in ("speed_ms", "power_ratio", "sample_count")} for row in old_suite["observations"]]
        observations_new = [{key: row[key] for key in ("speed_ms", "power_ratio", "sample_count")} for row in new_suite["observations"]]
        comparisons.append({"profile": {"mass_kg": 12.4, "num_rotors": 4, "prop_diameter_inch": diameter, "reference_area_cm2": 450.0},
                            "bauersfeld": {"archive": old_solved, "current": new_solved, "max_absolute_difference": max(abs(new_solved[key] - value) for key, value in old_solved.items())},
                            "joined_samples": {"archive": old_suite["source_result"]["joined_sample_count"], "current": new_suite["source_result"]["joined_sample_count"]},
                            "hover_reference_w": {"archive": old_suite["measured_hover_power_w"], "current": new_suite["measured_hover_power_w"]},
                            "observations_equal": observations_old == observations_new,
                            "bin_count": len(observations_new), "curve_comparison": curves,
                            "saved_json_api_max_absolute_ratio_difference": max(wrapper_differences)})
    batteries = [{"chemistry": chemistry, "archive_wh": archive.calculate_real_energy_wh(6, 5000, chemistry),
                  "current_wh": current.calculate_real_energy_wh(6, 5000, chemistry)} for chemistry in ("lipo", "liion", "lihv")]
    g29_hover = 4 * archive.get_power_from_thrust(3100, archive.u8lite_kv190_g29_data)
    g28_hover = 4 * archive.get_power_from_thrust(3100, archive.u8lite_kv190_data)
    entered_hover_w = g29_hover * 1515.782 / g28_hover
    prediction_energy_wh = 1198.8 * (25.2 / 27.0) * 0.9
    actual_profile_comparison = {
        name: compare_curves(old_fn, new_suite["model_functions"][name])
        for name, old_fn in historical_suite["model_functions"].items()
    }
    current_predictions = from_calibration_suite(new_suite).predict(
        17.0, hover_power_w=entered_hover_w, usable_energy_wh=prediction_energy_wh,
    )
    inputs = input_comparison(archive_root)
    result = {"schema_version": 1, "scope": "Same-input code comparison, not independent flight validation.",
              "archive_module_name": "menzil2.py", "archive_module_sha256": original_hash,
              "current_model_sha256": sha256(Path(current.__file__)),
              "comparison_script_sha256": sha256(Path(__file__)),
              "reference_cf": {"archive": cf_old, "current": cf_new},
              "latest_saved_report": {"filename": "datalink_fit_method_report.md", "sha256": sha256(archive_root / "datalink_fit_method_report.md"),
                                      "nominal_energy_wh": 1198.8, "usable_energy_wh": 1118.88,
                                      "entered_g29_table_hover_w": g29_hover,
                                      "historical_g28_table_hover_w": g28_hover,
                                      "conditional_scaled_entered_hover_w": entered_hover_w,
                                      "note": "The saved report prints CF 0.616 only as a legacy-menu audit. Fitted range/time uses a separate usable-energy and conditional electrical-power basis. The fitted source preset was G28, while the entered aircraft could use G29."},
              "comparisons": comparisons,
              "historical_g28_to_current_g29": {
                  "scope": "Actual historical fitted geometry versus the owner's current G29 selection; includes geometry changes and the Kirschstein correction.",
                  "curve_comparison": actual_profile_comparison,
              },
              "current_g29_prediction_at_17_ms": {
                  "conditional_hover_power_w": entered_hover_w,
                  "usable_energy_after_10_percent_reserve_wh": prediction_energy_wh,
                  "models": current_predictions,
              },
              "battery_checks": batteries,
              "input_hash_checks": inputs,
              "archive_module_unchanged": sha256(archive_root / "menzil2.py") == original_hash}
    assert all(row["equivalent"] for row in inputs)
    assert cf_old == cf_new
    assert all(row["archive_wh"] == row["current_wh"] for row in batteries)
    assert result["archive_module_unchanged"]
    for comparison in comparisons:
        assert comparison["bauersfeld"]["max_absolute_difference"] == 0.0
        assert comparison["observations_equal"]
        assert comparison["saved_json_api_max_absolute_ratio_difference"] <= 1e-12
        for name in ("zeng_datalink_fit", "faessler_datalink_fit"):
            assert comparison["curve_comparison"][name]["max_absolute_ratio_difference"] == 0.0
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_root", type=Path, help="Trusted local directory containing menzil2.py and its July 3 inputs")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/results/current-local-comparison.json")
    args = parser.parse_args()
    result = compare(args.archive_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Comparison written to {args.output}")


if __name__ == "__main__":
    main()
