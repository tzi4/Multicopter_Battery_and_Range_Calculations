"""Reports preserve the actual prediction and distinguish calibration from validation."""

import copy
import html
from pathlib import Path
import re
from urllib.parse import unquote

import pytest

from flight_workflow import FlightFit, MODEL_LABELS, fit_flight, from_calibration_suite
from test_workflow import aircraft, synthetic_samples


@pytest.fixture
def fitted():
    rows = synthetic_samples()
    # These steady low-speed samples count as stable but do not enter the fit.
    prefix = [dict(rows[0], vx_ms=1.0) for _ in range(100)]
    rows = prefix + rows
    for index, row in enumerate(rows):
        row["time_s"] = index * 0.05
    return fit_flight(rows, aircraft(), 1500.0)


def prediction_rows(report):
    result = {}
    for name, label in MODEL_LABELS.items():
        line = next(line for line in report.splitlines() if line.startswith(f"| {label} |"))
        result[name] = [float(value.strip()) for value in line.split("|")[2:-1]]
    return result


def test_restored_fit_report_uses_prediction_basis_and_after_reserve_energy(fitted, tmp_path):
    restored = FlightFit.load(fitted.save(tmp_path / "fit.json"))
    report = html.unescape(restored.write_report(tmp_path / "report.md", 1600.0, 1000.0, speed_ms=8.0).read_text())
    reported = prediction_rows(report)
    for name, prediction in restored.predict(8.0, 1600.0, 1000.0).items():
        values = [prediction[key] for key in ("power_ratio", "power_w", "endurance_min", "range_km")]
        assert reported[name] == pytest.approx(values, abs=0.00051)
    assert "Calibration normalization hover [W; log sensor basis] | 1500.0" in report
    assert "Prediction hover [W; supplied whole-aircraft basis] | 1600.0" in report
    assert "Usable prediction energy [Wh; after reserve] | 1000.0" in report
    assert "No additional CF, battery multiplier or reserve is applied" in report
    assert "inside the fitted speed-bin range" in report
    assert "Input samples | 1000" in report
    stable_count = restored.metadata["stable_sample_count"]
    retained_count = sum(row["sample_count"] for row in restored.observations)
    assert stable_count > retained_count
    assert f"Stable samples across the input flight | {stable_count}" in report
    assert f"Samples contributing to retained bin medians | {retained_count}" in report
    assert restored.metadata["samples_sha256"] in report

    second = restored.write_report(tmp_path / "less-energy.md", 1600.0, 500.0, speed_ms=8.0).read_text()
    for name, values in prediction_rows(second).items():
        assert values[:2] == reported[name][:2]
        assert values[2:] == pytest.approx([value / 2 for value in reported[name][2:]], abs=0.0008)


def test_bundled_metadata_gaps_are_not_reported_as_zero_and_extrapolation_is_explicit(fitted, tmp_path):
    observations = copy.deepcopy(fitted.observations)
    for row in observations:
        row["source_bins"] = ["reference.BIN"]
    bundled = from_calibration_suite({
        "model_params": {f"{name}_datalink_fit": parameters for name, parameters in fitted.parameters.items()},
        "model_profile": fitted.profile, "observations": observations, "power_reference_w": 1500.0,
    })
    restored = FlightFit.load(bundled.save(tmp_path / "bundled.json"))
    report = restored.write_report(tmp_path / "bundled.md", 1600.0, 1000.0, speed_ms=17.0).read_text()
    assert "Input samples | Not recorded in this saved fit" in report
    assert "Stable samples across the input flight | Not recorded in this saved fit" in report
    assert "Selection thresholds: Not recorded in this saved fit" in report
    assert "Source files: reference.BIN" in report
    assert "**Extrapolation:**" in report
    assert "calibration and model predictions, not independent validation" in report
    assert "Retained speed bins | 9" in report
    assert "Samples contributing to retained bin medians | 882" in report


def test_export_produces_reusable_fit_figures_and_portable_links(fitted, tmp_path):
    outputs = fitted.export(tmp_path / "an aircraft (trial)", 1600.0, 1000.0, speed_ms=8.0, max_speed_ms=18.0)
    assert set(outputs) == {"fit", "power_ratio", "range_endurance", "report"}
    for key in ("power_ratio", "range_endurance"):
        assert outputs[key].read_bytes().startswith(b"\x89PNG")
    assert FlightFit.load(outputs["fit"]).predict(8.0, 1600.0, 1000.0) == fitted.predict(8.0, 1600.0, 1000.0)
    links = re.findall(r"\]\(([^)]+)\)", outputs["report"].read_text())
    assert len(links) == 4
    assert all(not Path(target).is_absolute() for target in links)
    assert {(outputs["report"].parent / unquote(target)).resolve() for target in links} == {path.resolve() for path in outputs.values()}


def test_report_escapes_metadata_and_links_and_rejects_invalid_inputs_before_writing(fitted, tmp_path):
    fitted.profile["vehicle_name"] = "Aircraft [name](bad) | <script>"
    fitted.metadata["source_files"] = ["my|flight\n[name].csv"]
    fitted.metadata["parameter_warnings"] = ["Inspect [this](bad) | coefficient"]
    artifact = tmp_path / "data (trial)#1.json"
    artifact.write_text("{}")
    report_path = fitted.write_report(tmp_path / "subfolder" / "report.md", 1600.0, 1000.0, artifacts={"fit": artifact})
    report = report_path.read_text()
    assert "[name](bad)" not in report and "<script>" not in report
    assert "my|flight" not in report and "Recorded parameter warnings:" in report
    assert "(../data%20%28trial%29%231.json)" in report
    bad_dir = tmp_path / "invalid"
    with pytest.raises(ValueError, match="usable_energy_wh"):
        fitted.export(bad_dir, 1600.0, -1.0)
    assert not bad_dir.exists()
    with pytest.raises(ValueError, match="speed_ms"):
        fitted.write_report(bad_dir / "report.md", 1600.0, 1000.0, speed_ms=-1.0)
    assert not bad_dir.exists()
    fitted.parameters["kirschstein"]["extra_cubic_k"] = -1.0
    with pytest.raises(ValueError, match="nonphysical"):
        fitted.export(bad_dir, 1600.0, 1000.0, speed_ms=0.0)
    assert not bad_dir.exists()
