"""Fit flight-specific power curves and reuse them from Python.

The bundled calibration belongs to one aircraft. Fit your own logs before using
these models for another configuration. Speed from XKF1 is horizontal ground
speed, used as an airspeed proxy under approximately calm, steady conditions.
"""

from bisect import bisect_left
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from statistics import median

import multicopter_range as model


MODEL_FUNCTIONS = {
    "zeng": model.power_ratio_bauersfeld_anchored_zeng,
    "faessler": model.power_ratio_faessler_drag_constrained_zeng,
    "kirschstein": model.power_ratio_kirschstein_all_data,
}
MODEL_LABELS = {"zeng": "Zeng-inspired", "faessler": "Faessler-inspired", "kirschstein": "Kirschstein-inspired"}
CSV_COLUMNS = ("time_s", "vx_ms", "vy_ms", "vertical_speed_ms", "pitch_deg", "roll_deg", "power_w")


def _implementation_provenance():
    return {"model_sha256": hashlib.sha256(Path(model.__file__).read_bytes()).hexdigest(),
            "workflow_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _positive(value, name, *, zero=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(f"{name} must be finite and {'nonnegative' if zero else 'positive'}")
    return value


@dataclass(frozen=True)
class Aircraft:
    """Measured configuration; aerodynamic defaults are assumptions, not fits."""

    name: str
    mass_kg: float
    num_rotors: int
    prop_diameter_inch: float
    reference_area_m2: float
    hover_rpm: float | None = None
    rho: float = 1.225
    rotor_solidity: float = 0.05
    blade_drag_coefficient: float = 0.012
    induced_correction: float = 0.1
    hotel_power_w: float = 0.0

    def __post_init__(self):
        for field in ("mass_kg", "prop_diameter_inch", "reference_area_m2", "rho", "rotor_solidity", "blade_drag_coefficient"):
            _positive(getattr(self, field), field)
        if not isinstance(self.num_rotors, int) or isinstance(self.num_rotors, bool) or self.num_rotors < 1:
            raise ValueError("num_rotors must be a positive integer")
        _positive(self.hotel_power_w, "hotel_power_w", zero=True)
        _positive(self.induced_correction, "induced_correction", zero=True)
        if self.hover_rpm is not None:
            _positive(self.hover_rpm, "hover_rpm")


@dataclass(frozen=True)
class FitOptions:
    """Explicit selection thresholds; freeze these before comparing later flights."""

    min_speed_ms: float = 2.0
    max_speed_ms: float = 25.0
    bin_width_ms: float = 1.0
    min_bin_samples: int = 80
    min_bins: int = 3
    max_accel_ms2: float = 0.8
    max_vertical_speed_ms: float = 1.0
    max_tilt_deg: float = 25.0
    min_stable_fraction: float = 0.5
    attitude_min_speed_ms: float = 3.0
    attitude_max_speed_ms: float = 7.2
    min_attitude_samples: int = 20
    max_sample_gap_s: float = 1.0

    def __post_init__(self):
        for field, value in asdict(self).items():
            _positive(value, field)
        for field in ("min_bin_samples", "min_bins", "min_attitude_samples"):
            if not isinstance(getattr(self, field), int) or isinstance(getattr(self, field), bool):
                raise ValueError(f"{field} must be an integer")
        if self.min_bins < 3:
            raise ValueError("at least three independent speed bins are required")
        if self.max_speed_ms <= self.min_speed_ms or self.attitude_max_speed_ms <= self.attitude_min_speed_ms:
            raise ValueError("maximum speeds must exceed their minimum speeds")
        if self.min_stable_fraction > 1 or self.max_tilt_deg >= 90:
            raise ValueError("stable fraction must be <= 1 and maximum tilt < 90 degrees")


def load_flight_csv(path):
    """Read one synchronized flight. Required columns are CSV_COLUMNS; rpm is optional.

    time_s is monotonic seconds within this flight; velocities are m/s, angles
    degrees, power_w the selected measured electrical sum, rpm mechanical RPM.
    Convert and synchronize external telemetry before exporting this CSV.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(CSV_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")
        rows = []
        for number, raw in enumerate(reader, 2):
            try:
                row = {name: float(raw[name]) for name in CSV_COLUMNS}
                if raw.get("rpm"):
                    row["rpm"] = float(raw["rpm"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid numeric value in {path.name}, line {number}") from exc
            row["source"] = path.name
            rows.append(row)
    return _validate_samples(rows)


def _validate_samples(samples):
    rows = []
    for index, raw in enumerate(samples):
        row = dict(raw)
        for field in CSV_COLUMNS:
            if field not in row or not isinstance(row[field], (int, float)) or not math.isfinite(row[field]):
                raise ValueError(f"Sample {index}: {field} must be a finite number")
        _positive(row["power_w"], f"sample {index} power_w")
        if abs(row["pitch_deg"]) >= 90 or abs(row["roll_deg"]) >= 90:
            raise ValueError(f"Sample {index}: pitch and roll must lie between -90 and 90 degrees")
        if row.get("rpm") is not None:
            _positive(row["rpm"], f"sample {index} rpm")
        row["speed_ms"] = math.hypot(row["vx_ms"], row["vy_ms"])
        rows.append(row)
    rows.sort(key=lambda row: row["time_s"])
    if not rows:
        raise ValueError("No usable flight samples were supplied")
    if any(right["time_s"] <= left["time_s"] for left, right in zip(rows, rows[1:])):
        raise ValueError("Sample times must be unique within a single flight; fit flights separately")
    return rows


def _nearest(rows, times, time_s, max_dt_s):
    index = bisect_left(times, time_s)
    candidates = rows[max(0, index - 1): min(len(rows), index + 1)]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda row: abs(row["time_s"] - time_s))
    return nearest if abs(nearest["time_s"] - time_s) <= max_dt_s else None


def load_ardupilot_log(path, *, power_source="battery", battery_instance=0,
                       esc_ids=None, current_scale=1.0, rpm_scale=1.0,
                       time_shift_s=0.0, max_dt_s=0.35, ekf_core=0):
    """Join one DataFlash BIN's XKF1 and BAT or ESC messages by TimeUS.

    BAT uses one explicitly selected monitor, not a sum of parallel batteries.
    ESC sums exactly the supplied zero-based ESC instances and requires fresh
    telemetry from every selected ESC. Scale factors multiply decoded Curr/RPM;
    they must come from sensor calibration. time_shift_s is added to electrical
    telemetry timestamps before alignment, never inferred from fit quality.
    """
    from pymavlink import mavutil

    if power_source not in {"battery", "esc"}:
        raise ValueError("power_source must be 'battery' or 'esc'")
    for value, name in ((current_scale, "current_scale"), (rpm_scale, "rpm_scale"), (max_dt_s, "max_dt_s")):
        _positive(value, name)
    if not math.isfinite(time_shift_s):
        raise ValueError("time_shift_s must be finite")
    selected = tuple(esc_ids or ())
    if power_source == "esc" and (not selected or len(set(selected)) != len(selected) or any(not isinstance(i, int) or i < 0 for i in selected)):
        raise ValueError("ESC power requires distinct nonnegative esc_ids")
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    flight, battery = [], []
    esc = {instance: [] for instance in selected}
    log = mavutil.mavlink_connection(str(path), robust_parsing=True)
    try:
        while True:
            message = log.recv_match(type=["XKF1", "BAT", "ESC"], blocking=False)
            if message is None:
                break
            data = message.to_dict()
            time_s = data.get("TimeUS", float("nan")) / 1e6
            if not math.isfinite(time_s):
                continue
            kind = message.get_type()
            if kind == "XKF1" and data.get("C", 0) == ekf_core:
                fields = {"vx_ms": "VN", "vy_ms": "VE", "vertical_speed_ms": "VD", "pitch_deg": "Pitch", "roll_deg": "Roll"}
                if all(field in data for field in fields.values()):
                    flight.append({"time_s": time_s, **{key: data[value] for key, value in fields.items()}})
            elif kind == "BAT" and power_source == "battery" and data.get("Inst", 0) == battery_instance:
                voltage, current = data.get("Volt", 0), data.get("Curr", 0) * current_scale
                if voltage > 0 and current > 0:
                    battery.append({"time_s": time_s + time_shift_s, "power_w": voltage * current})
            elif kind == "ESC" and power_source == "esc" and data.get("Instance", data.get("I")) in esc:
                instance = data.get("Instance", data.get("I"))
                voltage, current = data.get("Volt", 0), data.get("Curr", 0) * current_scale
                rpm = data.get("RPM", 0) * rpm_scale
                if voltage > 0 and current > 0 and rpm > 0:
                    esc[instance].append({"time_s": time_s + time_shift_s, "power_w": voltage * current, "rpm": rpm})
    finally:
        log.close()
    streams = [battery] if power_source == "battery" else [esc[i] for i in selected]
    for stream in streams:
        stream.sort(key=lambda row: row["time_s"])
    times = [[row["time_s"] for row in stream] for stream in streams]
    joined = []
    for row in flight:
        readings = [_nearest(stream, stamps, row["time_s"], max_dt_s) for stream, stamps in zip(streams, times)]
        if not all(readings):
            continue
        sample = dict(row, power_w=sum(item["power_w"] for item in readings), source=path.name,
                      log_configuration={"power_source": power_source, "battery_instance": battery_instance,
                                         "esc_ids": list(selected), "current_scale": current_scale,
                                         "rpm_scale": rpm_scale, "time_shift_s": time_shift_s,
                                         "max_dt_s": max_dt_s, "ekf_core": ekf_core})
        if power_source == "esc":
            sample["rpm"] = median(item["rpm"] for item in readings)
        joined.append(sample)
    if not joined:
        raise ValueError("No synchronized XKF1/electrical samples found. Check message types, instances and clock alignment; a synchronized CSV is also supported.")
    return _validate_samples(joined)


def _stable_samples(samples, options):
    result = []
    for index, row in enumerate(samples):
        row = dict(row)
        acceleration = float("inf")
        if 0 < index < len(samples) - 1:
            previous, following = samples[index - 1], samples[index + 1]
            dt = following["time_s"] - previous["time_s"]
            if 0 < dt <= 2 * options.max_sample_gap_s and row["time_s"] - previous["time_s"] <= options.max_sample_gap_s and following["time_s"] - row["time_s"] <= options.max_sample_gap_s:
                acceleration = math.hypot(following["vx_ms"] - previous["vx_ms"], following["vy_ms"] - previous["vy_ms"]) / dt
        tilt = math.acos(max(-1.0, min(1.0, math.cos(math.radians(row["pitch_deg"])) * math.cos(math.radians(row["roll_deg"])))))
        row.update(accel_ms2=acceleration, tilt_rad=tilt)
        row["stable"] = acceleration <= options.max_accel_ms2 and abs(row["vertical_speed_ms"]) <= options.max_vertical_speed_ms and math.degrees(tilt) <= options.max_tilt_deg
        result.append(row)
    return result


def _attitude_prior(rows, aircraft, options):
    selected = [row for row in rows if row["stable"] and options.attitude_min_speed_ms <= row["speed_ms"] <= options.attitude_max_speed_ms]
    if len(selected) < options.min_attitude_samples:
        raise ValueError("Insufficient steady attitude samples for the Faessler drag prior; collect level segments across several speeds or adjust the documented selection thresholds")
    points = [(0.5 * aircraft.rho * row["speed_ms"]**2, row["speed_ms"], aircraft.mass_kg * 9.81 * math.tan(row["tilt_rad"])) for row in selected]
    s11 = sum(x*x for x, y, z in points)
    s12 = sum(x*y for x, y, z in points)
    s22 = sum(y*y for x, y, z in points)
    b1 = sum(x*z for x, y, z in points)
    b2 = sum(y*z for x, y, z in points)
    determinant = s11*s22 - s12*s12
    if determinant <= 1e-8 * s11*s22:
        raise ValueError("Attitude samples do not span enough distinct speeds to identify body and rotor drag")
    unconstrained = ((b1*s22-b2*s12)/determinant, (s11*b2-s12*b1)/determinant)
    candidates = [(max(0.0, b1/s11), 0.0), (0.0, max(0.0, b2/s22)), (0.0, 0.0)]
    if min(unconstrained) >= 0:
        candidates.append(unconstrained)
    cda, rotor_drag = min(candidates, key=lambda pair: sum((pair[0]*x + pair[1]*y-z)**2 for x,y,z in points))
    if cda == 0 and rotor_drag == 0:
        raise ValueError("Attitude data implies no drag across the selected speeds; verify the angle fields before fitting")
    return {"body_cda_fit_m2": cda, "body_cd_fit": cda/aircraft.reference_area_m2, "lambda_fit_n_per_ms": rotor_drag, "sample_count": len(points), "rho": aircraft.rho, "source": "own_flight_quasi_steady_tilt", "assumption": "Tilt-implied drag; approximately calm, steady, level flight and ground speed as an airspeed proxy"}


def fit_flight(samples, aircraft, hover_power_w, *, options=None):
    """Fit three normalized models to one flight; hover must use the log's power basis.

    Supply measured hover on the same sensor basis as power_w. A BAT or ESC sum
    is not automatically whole-aircraft power. Later absolute predictions take
    independently supplied whole-aircraft hover power and usable battery energy.
    """
    _positive(hover_power_w, "hover_power_w")
    options = options or FitOptions()
    rows = _stable_samples(_validate_samples(samples), options)
    for row in rows:
        config = row.get("log_configuration", {})
        if config.get("power_source") == "esc" and len(config["esc_ids"]) != aircraft.num_rotors:
            raise ValueError("The selected ESC count must match Aircraft.num_rotors")
    stable_rpms = [row["rpm"] for row in rows if row["stable"] and options.min_speed_ms <= row["speed_ms"] <= options.max_speed_ms and row.get("rpm")]
    rpm = median(stable_rpms) if stable_rpms else aircraft.hover_rpm
    if rpm is None:
        raise ValueError("Supply mechanical rpm in the samples or measured Aircraft.hover_rpm")
    utip = model.tip_speed_from_rpm(aircraft.prop_diameter_inch, rpm)
    for row in rows:
        row.update(power_ratio=row["power_w"]/hover_power_w, rpm_median=row.get("rpm") or rpm, utip_ms=model.tip_speed_from_rpm(aircraft.prop_diameter_inch, row.get("rpm") or rpm), source_bin=row.get("source", "own flight"))
    observations = model.build_datalink_speed_observations(rows, min_speed_ms=options.min_speed_ms, max_speed_ms=options.max_speed_ms, bin_width_ms=options.bin_width_ms, min_samples=options.min_bin_samples, power_reference_w=hover_power_w, stable_only=True, min_stable_fraction=options.min_stable_fraction)
    if len(observations) < options.min_bins:
        raise ValueError(f"Only {len(observations)} eligible speed bins; need at least {options.min_bins}. Collect steady flight across more speeds.")
    for observation in observations:
        observation.update(label=f"Flight bin at {observation['speed_ms']:.2f} m/s", source="own_flight")
    prior = _attitude_prior(rows, aircraft, options)
    profile = {"vehicle_name": aircraft.name, "mass_kg": aircraft.mass_kg, "num_rotors": aircraft.num_rotors, "prop_diameter_inch": aircraft.prop_diameter_inch, "rho": aircraft.rho, "utip_ms": utip, "rotor_solidity_s": aircraft.rotor_solidity, "blade_profile_drag_delta": aircraft.blade_drag_coefficient, "induced_correction_k": aircraft.induced_correction, "eta_propulsion": 1.0, "p_hotel_w": aircraft.hotel_power_w, "body_area_m2": aircraft.reference_area_m2, "cda_body_m2": prior["body_cda_fit_m2"], "blade_count": 2}
    theoretical = model.build_theoretical_zeng_params(profile, hover_power_w)
    if theoretical["p0_mech"] + aircraft.hotel_power_w >= hover_power_w:
        raise ValueError("Hover reference must exceed assumed rotor profile power plus hotel power; check the sensor basis, RPM and aerodynamic inputs")
    v0 = theoretical["v0_ms"]
    parameters = {
        "zeng": model.fit_observation_weighted_zeng(v0, utip, hover_power_w, theoretical, None, observations),
        "faessler": model.fit_faessler_drag_constrained_zeng(v0, utip, hover_power_w, theoretical, prior, None, observations=observations),
        "kirschstein": model.fit_kirschstein_all_data(profile, hover_power_w, v0, observations, faessler_fit=prior),
    }
    if parameters["faessler"]["f0_source"] != "all_data_weighted_fit":
        raise ValueError("Faessler fit is rank deficient; collect a wider range of steady speeds and check the attitude inputs")
    fingerprint = hashlib.sha256(json.dumps([{key: row.get(key) for key in (*CSV_COLUMNS, "rpm")} for row in rows], sort_keys=True, allow_nan=False).encode()).hexdigest()
    metadata = {"scope": "Calibration on one flight; evaluate frozen coefficients on later flights", "sample_count": len(rows), "stable_sample_count": sum(row["stable"] for row in rows), "source_files": sorted({row.get("source", "in-memory samples") for row in rows}), "samples_sha256": fingerprint, "selection": asdict(options), "hover_reference_w": hover_power_w, "rpm_source": "stable flight mechanical RPM" if stable_rpms else "supplied mechanical hover RPM", "attitude_prior": prior, "speed_basis": "horizontal ground speed; an airspeed proxy in calm conditions", "limitations": "Same aircraft configuration and comparable operating conditions; extrapolation and calibration residuals are not independent validation"}
    metadata["log_configurations"] = [json.loads(config) for config in sorted({json.dumps(row["log_configuration"], sort_keys=True) for row in rows if row.get("log_configuration")})]
    metadata["implementation"] = _implementation_provenance()
    metadata["parameter_warnings"] = []
    if not 0 <= parameters["zeng"]["f0"] <= 1:
        metadata["parameter_warnings"].append("Zeng hover split lies outside [0, 1]; treat this as a diagnostic fit")
    if parameters["zeng"]["k_par"] < 0:
        metadata["parameter_warnings"].append("Zeng parasite coefficient is negative; treat this as a diagnostic fit")
    for field in ("f0", "drag_scale"):
        if parameters["faessler"].get(f"{field}_raw") != parameters["faessler"][field]:
            metadata["parameter_warnings"].append(f"Faessler {field} reached its constraint; inspect the residuals before relying on this fit")
    fit = FlightFit(profile, parameters, observations, metadata)
    for observation in observations:
        fit.predict(observation["speed_ms"], hover_power_w, 1.0)
    return fit


@dataclass
class FlightFit:
    """Portable fitted coefficients. JSON is data only; loading executes no code."""

    profile: dict
    parameters: dict
    observations: list
    metadata: dict

    @property
    def fitted_speed_range(self):
        speeds = [row["speed_ms"] for row in self.observations]
        return min(speeds), max(speeds)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "profile": self.profile, "parameters": self.parameters, "observations": self.observations, "metadata": self.metadata}
        path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, path):
        def reject_constant(value):
            raise ValueError(f"Nonfinite value in fit JSON: {value}")
        payload = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant)
        def check_finite(value):
            if isinstance(value, dict):
                for item in value.values():
                    check_finite(item)
            elif isinstance(value, list):
                for item in value:
                    check_finite(item)
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Fit JSON contains a nonfinite number")
        check_finite(payload)
        if payload.get("schema_version") != 1:
            raise ValueError("Unsupported fit schema version")
        if set(payload.get("parameters", {})) != set(MODEL_FUNCTIONS) or not payload.get("observations"):
            raise ValueError("Fit JSON must contain three supported models and calibration observations")
        fit = cls(payload["profile"], payload["parameters"], payload["observations"], payload["metadata"])
        for speed in fit.fitted_speed_range:
            fit.predict(speed, 1.0, 1.0)
        return fit

    def predict(self, speed_ms, hover_power_w, usable_energy_wh):
        """Return power, time and still-air distance at constant speed for each model.

        usable_energy_wh is energy available after your reserve policy. No extra
        multiplier is applied. Mass, geometry and fitted coefficients stay fixed.
        """
        _positive(speed_ms, "speed_ms", zero=True)
        _positive(hover_power_w, "hover_power_w")
        _positive(usable_energy_wh, "usable_energy_wh")
        low, high = self.fitted_speed_range
        predictions = {}
        for name, function in MODEL_FUNCTIONS.items():
            ratio = function(speed_ms, self.parameters[name])
            if name == "kirschstein":
                params = self.parameters[name]
                ratio = model.power_kirschstein_component(speed_ms, params) / params["hover_power_reference_w"] + params.get("induced_relief_scale", 0.0) * (model.zeng_induced_ratio(speed_ms, params["v0_ms"]) - 1.0) + params.get("extra_cubic_k", 0.0) * speed_ms**3
            if not math.isfinite(ratio) or ratio <= 0:
                raise ValueError(f"{name} predicts nonphysical power at {speed_ms:g} m/s; restrict the prediction range and inspect the fit")
            power = hover_power_w * ratio
            minutes = 60.0 * usable_energy_wh / power
            if not math.isfinite(power) or not math.isfinite(minutes):
                raise ValueError("Prediction exceeds the numeric range; check power and energy inputs")
            predictions[name] = {"speed_ms": speed_ms, "power_ratio": ratio, "power_w": power, "endurance_min": minutes, "range_km": speed_ms * minutes * 60.0 / 1000.0, "within_fitted_speed_range": low <= speed_ms <= high}
        return predictions

    def plot(self, output_dir, hover_power_w, usable_energy_wh, *, max_speed_ms=25.0):
        """Write P/Ph and range/endurance figures; shaded span is the fitted range."""
        import matplotlib.pyplot as plt

        _positive(max_speed_ms, "max_speed_ms")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        speeds = [index * max_speed_ms / 250.0 for index in range(251)]
        predictions = [self.predict(speed, hover_power_w, usable_energy_wh) for speed in speeds]
        low, high = self.fitted_speed_range
        paths = {}
        for key, fields, labels in (("power_ratio", ["power_ratio"], ["Normalized power P(V) / P_hover"]), ("range_endurance", ["range_km", "endurance_min"], ["Range [km]", "Endurance [min]"])):
            figure, axes = plt.subplots(len(fields), 1, figsize=(10, 4.8 * len(fields)), sharex=True, squeeze=False)
            for axis, field, label in zip(axes[:, 0], fields, labels):
                axis.axvspan(low, high, color="gray", alpha=0.12, label="Fitted speed-bin range")
                for name in MODEL_FUNCTIONS:
                    values = [prediction[name][field] for prediction in predictions]
                    line, = axis.plot(speeds, [value if low <= speed <= high else float("nan") for speed, value in zip(speeds, values)], label=MODEL_LABELS[name])
                    axis.plot(speeds, [value if speed <= low or speed >= high else float("nan") for speed, value in zip(speeds, values)], color=line.get_color(), linestyle="--", alpha=0.85)
                if field == "power_ratio":
                    axis.scatter([row["speed_ms"] for row in self.observations], [row["power_ratio"] for row in self.observations], c="black", s=25, zorder=4, label="Calibration bin medians")
                axis.set_ylabel(label)
                axis.grid(alpha=0.25)
                axis.legend(fontsize=8)
            axes[-1, 0].set_xlabel("Horizontal ground speed [m/s]")
            title = f"{self.profile.get('vehicle_name', 'Aircraft')}: fitted power models"
            if key == "range_endurance":
                title = f"P_hover = {hover_power_w:g} W; usable energy = {usable_energy_wh:g} Wh (after reserve)"
            axes[0, 0].set_title(title)
            figure.text(0.5, 0.005, "Outside the shaded span: extrapolation. Constant speed and comparable conditions assumed.", ha="center", fontsize=8)
            figure.tight_layout(rect=(0, 0.025, 1, 1))
            path = output_dir / f"{key}.png"
            figure.savefig(path, dpi=180)
            plt.close(figure)
            paths[key] = path
        return paths


def from_calibration_suite(suite):
    """Copy the bundled fit's coefficients, without its historical battery scenario.

    This is a vehicle-specific demonstration. Use fit_flight for your own logs.
    Absolute predictions always require explicit hover power and usable energy.
    """
    def json_safe(value):
        if isinstance(value, dict):
            return {key: json_safe(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [json_safe(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        return value

    parameters = {name: json_safe(suite["model_params"][f"{name}_datalink_fit"]) for name in MODEL_FUNCTIONS}
    return FlightFit(json_safe(suite["model_profile"]), parameters, json_safe(suite["observations"]), {"scope": "Bundled vehicle-specific demonstration; fit your own logs before using another aircraft", "hover_reference_w": suite["power_reference_w"], "speed_basis": "horizontal ground speed; an airspeed proxy in calm conditions", "implementation": _implementation_provenance(), "limitations": "Calibration residuals are not independent validation. Historical battery and branch multipliers are not used by this workflow."})
