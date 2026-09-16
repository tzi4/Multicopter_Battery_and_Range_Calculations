"""Check the downloadable example against real source data and the public API."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from flight_workflow import Aircraft, FitOptions, FlightFit, fit_flight, load_flight_csv


ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "data/starter"


def load_json(name):
    return json.loads((STARTER / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def starter_fit():
    expected = load_json("expected-results.json")
    samples = load_flight_csv(STARTER / "flight.csv")
    fit = fit_flight(
        samples, Aircraft(**expected["aircraft"]), expected["log_hover_reference_w"],
        options=FitOptions(**expected["fit_options"]),
    )
    return samples, fit, expected


def test_starter_regenerates_from_unmodified_flight_sources(tmp_path):
    path = ROOT / "examples/prepare_starter_csv.py"
    spec = importlib.util.spec_from_file_location("prepare_starter_csv", path)
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    actual, _ = exporter.rebuild(output_dir=tmp_path)
    assert (tmp_path / "flight.csv").read_bytes() == (STARTER / "flight.csv").read_bytes()
    assert actual == load_json("provenance.json")
    assert actual["source_bin"] == "00000076.BIN"
    assert actual["gaps_over_1_second"] == 23
    assert actual["sample_count"] == 2527
    assert actual["csv_bytes"] < 300_000
    assert actual["csv_sha256"] == hashlib.sha256((STARTER / "flight.csv").read_bytes()).hexdigest()


def test_starter_fits_all_models_and_saved_fit_reproduces_example(starter_fit, tmp_path):
    samples, fit, expected = starter_fit
    assert expected["fit_options"] == {
        field: getattr(FitOptions(), field) for field in expected["fit_options"]
    }
    assert expected["csv_sha256"] == hashlib.sha256((STARTER / "flight.csv").read_bytes()).hexdigest()
    assert len(samples) == expected["sample_count"]
    assert fit.metadata["stable_sample_count"] == expected["stable_sample_count"]
    assert fit.fitted_speed_range == pytest.approx(expected["fitted_speed_range_ms"], rel=1e-9)
    assert fit.metadata["parameter_warnings"] == expected["parameter_warnings"]
    assert len(fit.observations) == len(expected["retained_bins"]) == 3
    for actual, reference in zip(fit.observations, expected["retained_bins"]):
        assert {key: actual[key] for key in reference} == pytest.approx(reference, rel=1e-9)
    saved = FlightFit.load(fit.save(tmp_path / "starter-fit.json"))
    predictions = saved.predict(**expected["prediction_inputs"])
    assert set(predictions) == {"zeng", "faessler", "kirschstein"}
    for name, actual in predictions.items():
        assert actual == pytest.approx(expected["predictions"][name], rel=1e-9)
    # Exercise the complete intended plot domain, including extrapolation.
    for index in range(201):
        rows = saved.predict(index / 10.0, 1485.6942539603501, 1006.992)
        assert all(row["power_w"] > 0 for row in rows.values())
