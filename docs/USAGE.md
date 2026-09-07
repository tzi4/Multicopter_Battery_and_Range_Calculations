# Two stages, one aircraft workflow

Use a first estimate before flight, then a model fitted to your own telemetry
once flight data are available. You can edit and run the Python files in
`examples/`; command-line flags are optional. For the author's default setup,
edit [`examples/aircraft_inputs.py`](../examples/aircraft_inputs.py) and run
`python examples/analyze_aircraft.py` to execute both stages together.
The defaults and the recovered CF are explained in [Author defaults](AUTHOR_DEFAULTS.md).

Install with `python -m pip install -e .` from a repository clone in a Python
3.10+ environment. The calculator lives in
[`multicopter_range.py`](../multicopter_range.py); the custom-log and saved-fit
interface lives in [`flight_workflow.py`](../flight_workflow.py).

For an interactive view without Python, [open the browser
explorer](https://tzi4.github.io/Multicopter_Battery_and_Range_Calculations/aircraft-demo.html).
You can also download the [standalone HTML](https://raw.githubusercontent.com/tzi4/Multicopter_Battery_and_Range_Calculations/main/docs/aircraft-demo.html) for offline use. It keeps the author's Zeng-only
interface, with the current G29 source fit and explicit power/energy settings.
It explores a supplied model; it does not fit uploaded logs. See [Browser demo](AIRCRAFT_DEMO.md).

## Start with a small real-flight CSV

The [CSV starter](CSV_STARTER.md) includes a compact real-flight CSV and an
editable Python example. A small downloadable ZIP contains the necessary
source files, so the full calibration archive is optional for this workflow.
After installation, run:

```bash
python examples/csv_starter.py
```

The script calls `load_flight_csv`, `fit_flight` and `export`, then reloads the
JSON for a prediction. It writes both figures and a short `fit-report.md` along
with the reusable fit. Edit `CSV_PATH`, the electrical references and the
requested speed in the example, and the shared geometry in `aircraft_inputs.py`.
The CSV's source and sampling rule are recorded in
[its provenance](../data/starter/README.md).

## Before flight: geometry, hover power and energy

Edit the inputs in [`examples/aircraft_inputs.py`](../examples/aircraft_inputs.py).
To run just the Bauersfeld stage:

```bash
python examples/preflight_estimate.py
```

| Python input | Meaning |
|---|---|
| `hover_power_w` | Electrical hover power for the whole aircraft, in W. Before flight, use a suitable bench or manufacturer estimate; a previous hover measurement can improve this input. |
| `battery_wh` | Whole-pack energy basis, in Wh. |
| `correction_factor` | Empirical time/energy multiplier. The author's standard value is 0.6159319356, recovered from a hover benchmark. Use `1.0` when calibrated power and usable energy already supply the intended basis. |
| `total_mass_kg` | Takeoff mass including battery and payload, in kg. |
| `drag_area_cm2` | Projected reference area in cm², as used by the Bauersfeld regression. This is not aerodynamic `CdA`. |
| `prop_diameter_inch` | Diameter of one propeller, in inches. |
| `num_rotors` | Number of load-bearing rotors. |

The author's G29 table gives 1101.6581197 W hover power for the declared 12.4 kg
quadrotor. Two 6S 27 Ah Li-ion packs give 1198.8 Wh nominal energy. With the
recovered standard CF, the example prints:

```text
Empirical correction factor: 0.615932
Bench hover-power estimate: 1101.66 W
Nominal energy: 1198.80 Wh
Best-range speed: 10.72 m/s
Best-range power: 1203.0 W
Best-range flight time: 36.83 min
Maximum range: 23.69 km
Best-endurance speed: 6.59 m/s
Maximum endurance: 44.00 min
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
0.0,0.1,0.0,0.0,0.2,0.1,1485.7,2149.8
0.1,0.1,0.0,0.0,0.2,0.1,1487.0,2150.0
```

These two invented rows illustrate the format only; they are not enough to fit a model.
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
    hover_rpm=2149.761904761904,  # Author's representative RPM; replace for your aircraft.
)
fit = fit_flight(
    samples,
    aircraft,
    hover_power_w=1485.6942539603501,  # Author scenario; replace with your measured log reference.
    options=FitOptions(min_speed_ms=2.0, max_speed_ms=20.0, min_bin_samples=80),
)
outputs = fit.export(
    "my-flight-output",
    hover_power_w=1485.6942539603501,
    usable_energy_wh=1006.992,  # Already excludes reserve; no extra deduction.
    speed_ms=10.0,
    max_speed_ms=20.0,
)
```

The starting numbers follow the author's archived scenario. Replace the power
reference with your own calibrated measurement on the same sensor basis as
the log. The archived 1485.69 W value is not inferred from an arbitrary BIN file.
Aircraft geometry and measured tip speed inform the three existing model
families. The Faessler-inspired fit also uses a drag prior estimated from sufficiently steady attitude/velocity records.
Rotor solidity, blade drag, induced correction and hotel-power
assumptions are configurable in `Aircraft`; the defaults are modeling
assumptions, not measurements inferred for every new aircraft. See the
[workflow methodology](WORKFLOW_METHOD.md) for filtering and fit requirements.

### Read the automatic fit report

`export()` writes `aircraft-fit.json`, `power_ratio.png`, `range_endurance.png`
and `fit-report.md`. The CSV starter, own-log example and bundled demonstration
all call it automatically. It returns a dictionary of paths with keys `fit`,
`power_ratio`, `range_endurance` and `report`.

The English report records the aircraft configuration, input and retained
sample counts, fitted speed-bin range, selection thresholds and predictions at
the requested speed. Log-normalization hover power is separate from the supplied
whole-aircraft prediction hover and energy after reserve. Any existing fit
warnings and extrapolation status remain visible. Its output links are relative,
so the folder can be moved or shared.

For a saved fit, you can regenerate just the report without loading logs or
redrawing the figures:

```python
from flight_workflow import FlightFit

fit = FlightFit.load("my-flight-output/aircraft-fit.json")
fit.write_report(
    "my-flight-output/next-estimate.md",
    hover_power_w=1485.6942539603501, usable_energy_wh=1006.992,
    speed_ms=10.0,
)
```

Legacy saved fits may lack overall sample counts or selection metadata; the
report marks those fields as not recorded. A report describes the calibration
and entered prediction scenario, not independent flight accuracy. The separate
`save()` and `plot()` methods remain available.

### Reuse the fit on a later day

```python
from flight_workflow import FlightFit

fit = FlightFit.load("my-flight-output/aircraft-fit.json")
predictions = fit.predict(
    speed_ms=10.0,
    hover_power_w=1485.6942539603501,
    usable_energy_wh=1006.992,
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
| `fit-report.md` | Aircraft and electrical inputs, retained data, a 17 m/s prediction and output links. |

Edit the shared aircraft and battery settings in `examples/aircraft_inputs.py`,
and the log/output paths in the demonstration file. The postflight defaults are
**1485.694254 W** hover and **1006.992 Wh** after a 10% reserve. They reproduce
the saved report's electrical scenario; the normalized curves use the current
G29 fit. Absolute range and endurance are estimates, not newly measured flight
results. CF is not applied again to these plots.
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
