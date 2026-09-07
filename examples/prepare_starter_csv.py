"""Rebuild the compact teaching CSV from the unmodified public July 3 archive.

Run after installing the project. This maintenance step needs the full source
archive; running examples/csv_starter.py needs only the already exported CSV.
Selection depends on elapsed time and input validity, never on a model's error.
"""

import csv
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path

import multicopter_range as model
from flight_workflow import Aircraft, CSV_COLUMNS, FitOptions, fit_flight, load_flight_csv


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data/calibration/2026-07-03"
OUTPUT_DIR = ROOT / "data/starter"
SOURCE_BIN = "00000076.BIN"
SOURCE_SESSION = "UART-260703-103606"
SAMPLE_PERIOD_S = 0.75
HOVER_REFERENCE_W = 757.891
PREDICTION_INPUTS = {
    "speed_ms": 10.0,
    "hover_power_w": 1485.6942539603501,
    "usable_energy_wh": 1006.992,
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _first_record_per_bucket(joined, origin):
    """Keep original observations, with gaps and their one-flight clock intact."""
    selected = []
    seen = set()
    for row in sorted(joined, key=lambda item: item["timestamp_utc"]):
        elapsed = (row["timestamp_utc"] - origin).total_seconds()
        bucket = int(elapsed // SAMPLE_PERIOD_S)
        if bucket in seen:
            continue
        seen.add(bucket)
        selected.append({
            "time_s": elapsed,
            **{key: row[key] for key in CSV_COLUMNS if key != "time_s"},
            "rpm": row["rpm_median"],
        })
    return selected


def rebuild(data_root=DATA_ROOT, output_dir=OUTPUT_DIR):
    data_root, output_dir = Path(data_root), Path(output_dir)
    bin_path = data_root / SOURCE_BIN
    session = model.summarize_datalink_session(data_root / "Datalink" / SOURCE_SESSION)
    span = model.read_ardupilot_bin_time_span(bin_path)
    if not session or span.get("error"):
        raise ValueError("The complete public July 3 source archive is required to rebuild this CSV")
    telemetry = [
        row for row in model._parse_datalink_session_samples(session, "filename_trt", 29.0)
        if span["first_utc"] <= row["timestamp_utc"] <= span["last_utc"]
    ]
    flight = model.read_ardupilot_flight_samples(bin_path, span["first_utc"], span["last_utc"])
    joined = model.join_datalink_and_flight_samples(telemetry, flight, HOVER_REFERENCE_W)
    selected = _first_record_per_bucket(joined, span["first_utc"])
    if not selected:
        raise ValueError("No synchronized source samples are available")
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=(*CSV_COLUMNS, "rpm"), lineterminator="\n")
    writer.writeheader()
    for row in selected:
        writer.writerow({key: f"{value:.6f}".rstrip("0").rstrip(".") or "0" for key, value in row.items()})
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "flight.csv"
    csv_path.write_bytes(text.getvalue().encode("utf-8"))

    # Fit the exact rounded CSV a new user receives, not the in-memory source.
    samples = load_flight_csv(csv_path)
    aircraft = Aircraft("July 3 starter aircraft", 12.4, 4, 29.0, 0.045)
    options = FitOptions()
    fit = fit_flight(samples, aircraft, HOVER_REFERENCE_W, options=options)
    for index in range(201):
        fit.predict(index / 10.0, PREDICTION_INPUTS["hover_power_w"], PREDICTION_INPUTS["usable_energy_wh"])
    gaps = [right["time_s"] - left["time_s"] for left, right in zip(samples, samples[1:])]
    provenance = {
        "schema_version": 1,
        "scope": "Real-flight CSV for teaching the custom-log workflow; not the published calibration or independent validation",
        "csv_sha256": sha256(csv_path),
        "csv_bytes": csv_path.stat().st_size,
        "source_date": "2026-07-03",
        "source_bin": SOURCE_BIN,
        "source_session": SOURCE_SESSION,
        "input_sha256": {
            path.relative_to(data_root).as_posix(): sha256(path)
            for path in sorted([bin_path, *session["files"]])
        },
        "export_script_sha256": sha256(Path(__file__)),
        "model_sha256": sha256(Path(model.__file__)),
        "source_joined_samples": len(joined),
        "selection": {
            "rule": "First actual joined record in each fixed elapsed-time bucket; no speed, power, attitude, or model-error selection",
            "bucket_width_s": SAMPLE_PERIOD_S,
            "numeric_decimal_places": 6,
            "missing_buckets": "Omitted; original elapsed times and gaps are preserved",
        },
        "clock": {
            "time_origin": "First GPS anchor in the selected BIN, expressed in the legacy join coordinate; not takeoff time",
            "legacy_origin": span["first_utc"].isoformat(),
            "source_timeus_s_at_origin": span["first_timeus_s"],
            "timestamp_mode": "filename_trt",
            "nearest_flight_sample_max_dt_s": 0.35,
            "limitation": "The retained GPS helper omits the 18-second GPS-to-UTC correction applicable to July 2026. This reproduces the existing alignment; it does not establish independently verified UTC synchronization.",
        },
        "measurements": {
            "vx_ms": "XKF1.VN, EKF core 0",
            "vy_ms": "XKF1.VE, EKF core 0",
            "vertical_speed_ms": "-XKF1.VD; positive upward",
            "pitch_deg": "XKF1.Pitch",
            "roll_deg": "XKF1.Roll",
            "power_w": "Sum of voltage times current from four valid DataLink ESC slots; no historical x2 multiplier and no BAT current",
            "rpm": "Median of the four ESC mechanical RPM readings after the retained 10/21 conversion",
            "rpm_scale": model.DATALINK_RPM_SCALE,
        },
        "hover_reference": {
            "power_w": HOVER_REFERENCE_W,
            "basis": "Published July 3 two-flight hover median on the same recorded ESC-sum basis; not re-estimated from this thinned single-flight CSV",
            "source": "docs/results/calibration-summary.json#hover_esc_sum_power_w",
        },
        "sample_count": len(samples),
        "first_time_s": samples[0]["time_s"],
        "last_time_s": samples[-1]["time_s"],
        "gaps_over_1_second": sum(gap > 1.0 for gap in gaps),
        "max_gap_s": max(gaps),
    }
    expected = {
        "schema_version": 1,
        "scope": "Reproducible starter workflow output, not accuracy evidence or the published aircraft fit",
        "csv_sha256": sha256(csv_path),
        "aircraft": asdict(aircraft),
        "fit_options": asdict(options),
        "log_hover_reference_w": HOVER_REFERENCE_W,
        "sample_count": len(samples),
        "stable_sample_count": fit.metadata["stable_sample_count"],
        "fitted_speed_range_ms": list(fit.fitted_speed_range),
        "retained_bins": [
            {key: row[key] for key in ("speed_ms", "power_ratio", "sample_count", "raw_sample_count")}
            for row in fit.observations
        ],
        "parameter_warnings": fit.metadata["parameter_warnings"],
        "prediction_basis": "The author's conditional historical whole-aircraft power/energy scenario; separate from the recorded ESC normalization and not measured from this excerpt",
        "prediction_inputs": PREDICTION_INPUTS,
        "predictions": fit.predict(**PREDICTION_INPUTS),
    }
    for name, payload in (("provenance.json", provenance), ("expected-results.json", expected)):
        (output_dir / name).write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Starter CSV: {csv_path} ({len(samples)} rows, {csv_path.stat().st_size} bytes)")
    print(f"Retained bins: {len(fit.observations)}; fitted speed range: {fit.fitted_speed_range}")
    return provenance, expected


if __name__ == "__main__":
    rebuild()
