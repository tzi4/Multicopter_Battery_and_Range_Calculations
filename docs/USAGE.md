# Two stages, one aircraft workflow

Use a first estimate before flight, then a model fitted to your own telemetry
once flight data are available. You can edit and run the Python files in
`examples/`; command-line flags are optional.

Install with `python -m pip install -e .` from a repository clone in a Python
3.10+ environment. The calculator lives in
[`multicopter_range.py`](../multicopter_range.py); the custom-log and saved-fit
interface lives in [`flight_workflow.py`](../flight_workflow.py).

## Before flight: geometry, hover power and energy

Open [`examples/preflight_estimate.py`](../examples/preflight_estimate.py).
Edit the values passed to `BauersfeldRangeCalculator`, then run:

```bash
python examples/preflight_estimate.py
```

| Python input | Meaning |
|---|---|
| `hover_power_w` | Electrical hover power for the whole aircraft, in W. Before flight, use a suitable bench or manufacturer estimate; a previous hover measurement can improve this input. |
| `battery_wh` | Whole-pack energy basis, in Wh. |
| `correction_factor` | Fraction of that energy available for flight. Use `1.0` if the input already excludes reserves and unusable capacity. |
| `total_mass_kg` | Takeoff mass including battery and payload, in kg. |
| `drag_area_cm2` | Projected reference area in cm², as used by the Bauersfeld regression. This is not aerodynamic `CdA`. |
| `prop_diameter_inch` | Diameter of one propeller, in inches. |
| `num_rotors` | Number of load-bearing rotors. |

The example's 1500 W / 1200 Wh values are illustrative. It prints:

```text
Best-range speed: 10.72 m/s
Best-range power: 1638.0 W
Best-range flight time: 40.88 min
Maximum range: 26.30 km
Best-endurance speed: 6.59 m/s
Maximum endurance: 48.84 min
```

`solve()` returns a dictionary, so your own program can use these values
without parsing terminal output. This stage uses the Bauersfeld relationships;
it does not automatically use the log-fitted curves.

## After flight: introduce your logs

Choose a representative calibration flight with steady hover and several
steady forward-flight speeds. Include enough settled samples for multiple
speed bins. Record the actual mass, rotor geometry and power-sensor setup.
Use a separate later flight to assess how well the fitted curve carries over.

The [editable postflight example](../examples/postflight_fit.py) keeps log paths,
aircraft inputs and output settings in Python. Replace its example values,
then run `python examples/postflight_fit.py`.

### ArduPilot BIN input

```python
from flight_workflow import load_ardupilot_log

samples = load_ardupilot_log(
    "my-logs/flight.BIN",       # An absolute path also works.
    power_source="battery",
    battery_instance=0,
    current_scale=1.0,          # Keep 1 unless an independent calibration says otherwise.
)
```

The battery route needs `XKF1` vehicle velocity/attitude and `BAT` voltage/current
from a **calibrated whole-aircraft monitor**. Select the monitor instance that
covers the aircraft's electrical supply. The loader joins records on log time.
It cannot repair an uncalibrated current sensor or infer battery wiring.

If your BIN log records all motor ESCs instead:

```python
samples = load_ardupilot_log(
    "my-logs/flight.BIN",
    power_source="esc",
    esc_ids=(0, 1, 2, 3),       # Use the actual complete set of motor IDs.
    rpm_scale=1.0,             # Convert to mechanical RPM if your logger requires it.
)
```

ESC power is the sum of the selected `voltage × current` measurements. It may
exclude avionics or other loads. Match the electrical boundary of the fitted
power and hover reference, and check any whole-aircraft scaling independently.
Do not double ESC power merely because the battery has two parallel branches.

For battery-only logs without rotor RPM, supply `hover_rpm` in the aircraft
configuration below. For another logger, use a synchronized CSV with the
schema described below. The legacy T-MOTOR `.udat` reproduction path remains
available for the included July 3 data; it is not a universal DataLink importer.

### CSV input from another logger

Export one already synchronized flight, with this header:

```csv
time_s,vx_ms,vy_ms,vertical_speed_ms,pitch_deg,roll_deg,power_w,rpm
0.0,0.1,0.0,0.0,0.2,0.1,1500.0,2200.0
0.1,0.1,0.0,0.0,0.2,0.1,1502.0,2202.0
```

These two rows illustrate the format only; they are not enough to fit a model.
`time_s` is seconds on one common flight clock. `vx_ms` and `vy_ms` are horizontal
velocity components in a consistent earth-fixed frame; vertical speed is in
m/s, pitch and roll in degrees, and power in W. `rpm` is optional and must be
mechanical RPM. Without it, supply the aircraft's measured `hover_rpm`.
All required fields must be finite numbers, power must be positive, and times
must be unique within the flight. Use complete in-flight rows, not empty cells
or zero-power records from a disarmed aircraft.

```python
from flight_workflow import load_flight_csv

samples = load_flight_csv("my-logs/synchronized-flight.csv")
```

Convert units, correct independently established sensor gains and align any
external logger clocks before exporting. Do not concatenate flights whose
clocks restart into one CSV. There is no automatic search for the clock shift
that produces the smallest model error.

### Fit the aircraft

```python
from flight_workflow import Aircraft, FitOptions, fit_flight

aircraft = Aircraft(
    name="My multicopter",
    mass_kg=12.4,
    num_rotors=4,
    prop_diameter_inch=29.0,
    reference_area_m2=0.045,   # Projected body reference area [m²].
    hover_rpm=2200.0,          # Measured mechanical RPM; replace for your aircraft.
)
fit = fit_flight(
    samples,
    aircraft,
    hover_power_w=1500.0,     # Measured hover reference on the same electrical basis.
    options=FitOptions(min_speed_ms=2.0, max_speed_ms=20.0, min_bin_samples=80),
)
fit.save("my-flight-output/aircraft-fit.json")
fit.plot(
    "my-flight-output",
    hover_power_w=1500.0,
    usable_energy_wh=1100.0,  # Already excludes reserve; no extra deduction.
    max_speed_ms=20.0,
)
```

All numbers above are example inputs. Aircraft geometry and measured tip speed
inform the three existing model families. The Faessler-inspired fit also uses
a drag prior estimated from sufficiently steady attitude/velocity records.
Rotor solidity, blade drag, induced correction and hotel-power
assumptions are configurable in `Aircraft`; the defaults are modeling
assumptions, not measurements inferred for every new aircraft. See the
[workflow methodology](WORKFLOW_METHOD.md) for filtering and fit requirements.

### Reuse the fit on a later day

```python
from flight_workflow import FlightFit

fit = FlightFit.load("my-flight-output/aircraft-fit.json")
predictions = fit.predict(
    speed_ms=10.0,
    hover_power_w=1500.0,
    usable_energy_wh=1100.0,
)
for model_name, row in predictions.items():
    print(model_name, row)
```

The log is not parsed again. Each of `zeng`, `faessler` and `kirschstein` returns:

| Output field | Meaning |
|---|---|
| `speed_ms` | Requested steady-flight speed in m/s. |
| `power_ratio` | Predicted electrical power relative to the hover reference, `P/P_hover`. |
| `power_w` | Power ratio multiplied by the supplied hover power, in W. |
| `endurance_min` | `60 × usable_energy_wh / power_w`. |
| `range_km` | Requested speed multiplied by flight time, in km. |
| `within_fitted_speed_range` | Whether the speed lies between the retained calibration-bin medians. A false value means extrapolation. |

These are steady-flight estimates for the calibrated configuration, not a
complete mission simulation. The energy input is the usable budget for the
modeled segment. Hover, takeoff, climb, manoeuvres and return-flight wind may
consume additional energy. A new payload or propulsion setup is a reason to
recheck the fit, not just change the energy number.

## Rebuild the included example and its two plots

The supplied fit belongs to one specific aircraft. **Refit your own logs before
using these curves for your aircraft.** To inspect the workflow immediately:

```bash
python examples/bundled_flight_demo.py
```

This fits the current G29 / 12.4 kg July 3 scenario, saves and reloads its
coefficients, predicts at 17 m/s and writes:

| File in `flight-output/` | Contents |
|---|---|
| `aircraft-fit.json` | Reusable model parameters, calibration observations and fit metadata. |
| `power_ratio.png` | Three fitted `P/P_hover` curves and measured bins versus speed. |
| `range_endurance.png` | Range and endurance versus speed using the explicit power/energy inputs. |

Edit `DATA_ROOT`, `OUTPUT_DIR`, `HOVER_POWER_W` and `USABLE_ENERGY_WH` in the
example file. The latter two default to illustrative **1500 W / 1100 Wh**;
absolute range and endurance in these plots are not measured flight results.
The 17 m/s prediction is beyond the retained calibration-bin range.

Both plots use ground speed from the logs; neither is a thrust-to-weight plot
or a normalized-airspeed plot. Dashed curve segments indicate extrapolation.

For the published calibration and July 21 comparison, the separate
`examples/reproduce_showcase.py` script writes JSON summaries, CSV bin tables,
a Markdown audit and calibration/comparison PNG/SVG figures. Its options and
source hashes are documented in [Reproducibility](REPRODUCIBILITY.md).

The older `multicopter-range analyze-calibration --graphs` retains a fixed
G28 / 12.4 kg preset. Its `--data-root` relocates that historical data set and
does not configure a new aircraft. Wheels omit the large raw logs; use a
repository clone for the bundled demonstration.

## Advanced: transfer physical parameters to another configuration

Run this Python example from the repository root after installation. The first
call parses the bundled calibration data, so allow time for it to complete.

```python
from pathlib import Path
import multicopter_range as model
from examples.reproduce_calibration import build_calibration_suite

suite = build_calibration_suite(
    Path("data/calibration/2026-07-03"),
    mass_kg=12.4,
    prop_diameter_inch=29.0,
)

# Frozen July 3 Faessler-inspired curve, evaluated at any requested speed.
ratio_at_17 = suite["model_functions"]["faessler_datalink_fit"](17.0)
print(f"At 17 m/s: P/Ph = {ratio_at_17:.4f}")

# Illustrative target inputs: replace these with your aircraft's measurements.
target = {"mass_kg": 13.0, "num_rotors": 4, "prop_diameter_inch": 29.0,
          "rho": 1.225}
target_rpm = 2200.0
target_hover_w = 1600.0
target_usable_wh = 1100.0
speed_ms = 10.0

transferred = model.build_transferred_model_suite(
    suite, target,
    apply_utip_ms=model.tip_speed_from_rpm(target["prop_diameter_inch"], target_rpm),
)
ratio = transferred["model_functions"]["faessler_datalink_fit"](speed_ms)
power_w = target_hover_w * ratio
minutes = 60.0 * target_usable_wh / power_w
distance_km = speed_ms * minutes * 60.0 / 1000.0
print(f"{power_w:.1f} W; {minutes:.2f} min; {distance_km:.2f} km")
```

The target example prints approximately **1586.2 W, 41.61 min and 24.97 km**.
It scales the transferred curve shape using a supplied target hover-power
measurement; it does not infer that measurement from the API's internal hover
estimate. Time and distance assume constant modeled power/speed and the stated
usable-energy basis. Target RPM, mass, hover power and energy above are example
values, not recommendations or measurements recovered from the logs.

Transfer retains assumptions about the fitted aerodynamic coefficients and
electrical reference. A different airframe or propulsion system can change
those coefficients. See [Methodology](METHODOLOGY.md) for the physical transfer
and its same-configuration checks. There is no `transfer` CLI subcommand.

## What “1–25 kg” means here

The general calculator accepts positive, finite user-supplied mass and can be
used for aircraft-specific 1–25 kg design scenarios. That input flexibility is
not a validated accuracy interval derived from the repository's fit. Its
flight comparison concerns one nominal 12.4 kg configuration.

The U8 Lite G29 lookup helpers are also **not generic 1–25 kg motor models**.
Their measured per-motor thrust ranges correspond to approximately 7.52–29.34 kg
total thrust for the four-rotor RPM table and 8.14–29.34 kg for the power table.
The interpolation function clamps outside its table range. In particular, it
cannot supply a meaningful extrapolated G29 hover estimate for a 1 kg aircraft.
Use propulsion data and measured hover/RPM appropriate to the target vehicle,
then validate the resulting estimates on that vehicle.
