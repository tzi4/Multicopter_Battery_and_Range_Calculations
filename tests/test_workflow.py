"""Check the custom-flight workflow's scientific and input/output contracts."""

import copy
import csv
import json
import math
from pathlib import Path

import pytest

import multicopter_range as model
from flight_workflow import Aircraft, CSV_COLUMNS, FitOptions, FlightFit, fit_flight, load_ardupilot_log, load_flight_csv


def aircraft():
    return Aircraft("Synthetic aircraft", 12.4, 4, 29.0, 0.045, hover_rpm=2200.0)


def synthetic_samples():
    vehicle = aircraft()
    utip = model.tip_speed_from_rpm(vehicle.prop_diameter_inch, vehicle.hover_rpm)
    area = vehicle.num_rotors * math.pi * (vehicle.prop_diameter_inch * 0.0254 / 2)**2
    v0 = math.sqrt(vehicle.mass_kg * 9.81 / (2 * vehicle.rho * area))
    rows = []
    for speed in (2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5):
        ratio = 0.78 * model.zeng_profile_ratio(speed, utip) + 0.22 * model.zeng_induced_ratio(speed, v0) + 8e-5 * speed**3
        drag = 0.5 * vehicle.rho * 0.10 * speed**2 + 0.8 * speed
        pitch = math.degrees(math.atan(drag / (vehicle.mass_kg * 9.81)))
        for _ in range(100):
            rows.append(dict(time_s=len(rows)*0.05, vx_ms=speed, vy_ms=0.0,
                             vertical_speed_ms=0.0, pitch_deg=pitch, roll_deg=0.0,
                             power_w=1500*ratio, rpm=2200.0))
    return rows


def test_own_flight_recovers_known_curve_and_attitude_coefficients():
    fit = fit_flight(synthetic_samples(), aircraft(), 1500.0)
    assert len(fit.observations) == 9
    assert fit.parameters["zeng"]["f0"] == pytest.approx(0.78, abs=1e-10)
    assert fit.parameters["zeng"]["k_par"] == pytest.approx(8e-5, abs=1e-12)
    assert fit.metadata["attitude_prior"]["body_cda_fit_m2"] == pytest.approx(0.1, abs=1e-10)
    assert fit.metadata["attitude_prior"]["lambda_fit_n_per_ms"] == pytest.approx(0.8, abs=1e-10)
    assert all(row["source"] == "own_flight" for row in fit.observations)
    assert fit.fitted_speed_range == (2.5, 10.5)


def test_saved_fit_predicts_without_raw_logs_and_conserves_energy(tmp_path):
    fit = fit_flight(synthetic_samples(), aircraft(), 1500.0)
    path = fit.save(tmp_path / "nested" / "fit.json")
    restored = FlightFit.load(path)
    before = fit.predict(8.0, 1600.0, 1000.0)
    assert restored.predict(8.0, 1600.0, 1000.0) == before
    for name, prediction in before.items():
        assert prediction["power_w"] * prediction["endurance_min"] / 60 == pytest.approx(1000.0)
        assert prediction["range_km"] == pytest.approx(8.0 * prediction["endurance_min"] * 0.06)
        assert prediction["within_fitted_speed_range"] is True
        assert restored.predict(17.0, 1600.0, 1000.0)[name]["within_fitted_speed_range"] is False
    for prediction in restored.predict(0.0, 1600.0, 1000.0).values():
        assert prediction["power_ratio"] == pytest.approx(1.0)
        assert prediction["range_km"] == 0.0
    figures = restored.plot(tmp_path, 1600.0, 1000.0, max_speed_ms=18.0)
    assert set(figures) == {"power_ratio", "range_endurance"}
    assert all(path.read_bytes().startswith(b"\x89PNG") for path in figures.values())


def test_csv_contract_and_missing_rpm_fallback(tmp_path):
    path = tmp_path / "flight.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows({key: row[key] for key in CSV_COLUMNS} for row in synthetic_samples())
    rows = load_flight_csv(path)
    rows[0]["rpm"] = None
    fit = fit_flight(rows, aircraft(), 1500.0)
    assert fit.metadata["rpm_source"] == "supplied mechanical hover RPM"
    assert fit.metadata["source_files"] == ["flight.csv"]
    path.write_text("time_s,power_w\n0,1000\n")
    with pytest.raises(ValueError, match="missing columns"):
        load_flight_csv(path)


def test_rejects_sparse_rank_deficient_and_duplicate_time_data():
    rows = synthetic_samples()
    with pytest.raises(ValueError, match="eligible speed bins"):
        fit_flight(rows[:100], aircraft(), 1500.0)
    with pytest.raises(ValueError, match="distinct speeds"):
        fit_flight(rows, aircraft(), 1500.0, options=FitOptions(attitude_min_speed_ms=3.1, attitude_max_speed_ms=3.9))
    rows[1]["time_s"] = rows[0]["time_s"]
    with pytest.raises(ValueError, match="unique"):
        fit_flight(rows, aircraft(), 1500.0)


def test_vector_acceleration_rejects_turns_at_constant_speed():
    rows = synthetic_samples()
    # Heading alternates while scalar speed stays constant. Vector acceleration
    # must remove the corresponding bins rather than certify steady flight.
    for index, row in enumerate(rows):
        if index % 4 < 2:
            row["vx_ms"] = -row["vx_ms"]
    with pytest.raises(ValueError, match="eligible speed bins"):
        fit_flight(rows, aircraft(), 1500.0)


def test_zero_attitude_cannot_silently_return_an_unfitted_faessler_prior():
    rows = synthetic_samples()
    for row in rows:
        row["pitch_deg"] = 0.0
    with pytest.raises(ValueError, match="no drag"):
        fit_flight(rows, aircraft(), 1500.0)


def test_nonphysical_predictions_and_invalid_saved_models_fail(tmp_path):
    fit = fit_flight(synthetic_samples(), aircraft(), 1500.0)
    bad = copy.deepcopy(fit)
    bad.parameters["kirschstein"]["extra_cubic_k"] = -1.0
    with pytest.raises(ValueError, match="kirschstein predicts nonphysical"):
        bad.predict(10.0, 1500.0, 1000.0)
    with pytest.raises(ValueError, match="speed_ms"):
        fit.predict(-1.0, 1500.0, 1000.0)
    with pytest.raises(ValueError, match="Hover reference"):
        fit_flight(synthetic_samples(), aircraft(), 1.0)
    path = fit.save(tmp_path / "fit.json")
    payload = json.loads(path.read_text())
    payload["schema_version"] = 99
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="schema"):
        FlightFit.load(path)
    payload["schema_version"] = 1
    payload["parameters"]["zeng"]["f0"] = float("nan")
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Nonfinite"):
        FlightFit.load(path)


class FakeMessage:
    def __init__(self, kind, **data):
        self.kind, self.data = kind, data

    def get_type(self):
        return self.kind

    def to_dict(self):
        return self.data


class FakeLog:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.closed = False

    def recv_match(self, **_kwargs):
        return next(self.messages, None)

    def close(self):
        self.closed = True


def xkf(time_s):
    return FakeMessage("XKF1", TimeUS=time_s*1e6, C=0, VN=5.0, VE=0.0, VD=0.0, Pitch=3.0, Roll=0.0)


def test_battery_instance_clock_shift_and_sensor_gain(monkeypatch, tmp_path):
    from pymavlink import mavutil
    path = tmp_path / "flight.BIN"
    path.touch()
    messages = [xkf(1.5), FakeMessage("BAT", TimeUS=1e6, Inst=1, Volt=24.0, Curr=20.0), FakeMessage("BAT", TimeUS=1e6, Inst=0, Volt=24.0, Curr=99.0)]
    monkeypatch.setattr(mavutil, "mavlink_connection", lambda *_args, **_kwargs: FakeLog(messages))
    with pytest.raises(ValueError, match="No synchronized"):
        load_ardupilot_log(path, battery_instance=1, max_dt_s=0.1)
    rows = load_ardupilot_log(path, battery_instance=1, current_scale=2.0, time_shift_s=0.5, max_dt_s=0.1)
    assert len(rows) == 1
    assert rows[0]["power_w"] == 960.0
    assert rows[0]["log_configuration"]["time_shift_s"] == 0.5


def test_esc_requires_all_selected_fresh_instances(monkeypatch, tmp_path):
    from pymavlink import mavutil
    path = tmp_path / "flight.BIN"
    path.touch()
    ids = (1, 3, 6, 7)
    messages = [xkf(1.0), xkf(2.0)]
    for time_s in (1.0, 2.0):
        for instance in ids:
            if time_s == 2.0 and instance == 7:
                continue
            messages.append(FakeMessage("ESC", TimeUS=time_s*1e6, Instance=instance, Volt=24.0, Curr=5.0, RPM=4000.0))
    monkeypatch.setattr(mavutil, "mavlink_connection", lambda *_args, **_kwargs: FakeLog(messages))
    rows = load_ardupilot_log(path, power_source="esc", esc_ids=ids, rpm_scale=0.5)
    assert len(rows) == 1  # At t=2, ESC 7 is stale: no partial electrical sum.
    assert rows[0]["power_w"] == 480.0
    assert rows[0]["rpm"] == 2000.0
    with pytest.raises(ValueError, match="esc_ids"):
        load_ardupilot_log(path, power_source="esc", esc_ids=(0, 0))


def test_public_bin_battery_reader_parses_without_fitting_uncalibrated_current():
    path = Path(__file__).resolve().parents[1] / "data/calibration/2026-07-03/00000076.BIN"
    rows = load_ardupilot_log(path, power_source="battery", battery_instance=0)
    assert len(rows) > 1000
    assert rows[0]["source"] == path.name
    assert all(row["power_w"] > 0 for row in rows)
    # This archive's BAT current is suspect: parsing is not permission to use it
    # as a valid power fit. The showcase continues using its audited ESC sum.
