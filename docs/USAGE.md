# Using the calculator and fitted models

The main implementation is [`multicopter_range.py`](../multicopter_range.py).
It contains the calculator, log parsers, model fitting, physical transfer and
command-line entry point. The installed command `multicopter-range` calls its
`main()` function. The files in `examples/` assemble those functions into
reproducible experiments.

Install the repository first with `python -m pip install -e .` in a Python
3.10+ environment. Run the commands below from the repository root.

## 1. Estimate range and endurance from aircraft inputs

```bash
python multicopter_range.py calculate --hover-power 1500 --battery-energy 1200 --mass 12.4 --drag-area 450 --prop-diameter 29 --rotors 4 --correction-factor 0.93
```

The installed equivalent starts with `multicopter-range calculate`. The
example prints:

```text
Induced hover velocity: 5.397 m/s
Best-range speed: 10.723 m/s
Best-range flight time: 40.879 min
Maximum range: 26.302 km
Best-endurance speed: 6.589 m/s
Maximum endurance: 48.840 min
```

These are **illustrative inputs**, not a reconstruction of a particular flight:
1500 W is measured hover power for the whole aircraft, 1200 Wh is the whole
pack's energy basis, 12.4 kg is total takeoff mass, 450 cm² is the projected
reference area, and 29 inches is one propeller's diameter. The example treats
93% of the energy input as available. If the energy you enter is already usable
under your reserve policy, use a correction factor of 1.0.

This command runs the **Bauersfeld calculator**. It does not load the July 3
Zeng/Faessler/Kirschstein fits. It also does not infer hover power from mass or
select a motor from propeller diameter. Different aircraft need consistent
hover-power, energy and geometry inputs; changing only mass is insufficient.

## 2. Reproduce the flight-data results

```bash
python examples/reproduce_showcase.py --prop-diameter 29 --mass 12.4 --output-dir showcase-output --check-results docs/results
```

This rebuilds the G29 July 3 calibration, evaluates the frozen fits on the
published July 21 derived observations, and writes:

| Output | Contents |
|---|---|
| `calibration-summary.json` | Source/data hashes, configuration, measured bins and model curves |
| `calibration-bins.csv` | Measured and predicted normalized power in each calibration bin |
| `calibration-audit.md` | Fit parameters, diagnostics and interpretation |
| `validation-summary.json` | Every comparison bin, model prediction and residual |
| `validation-bins.csv` | The same comparison results in spreadsheet form |
| `figures/` | Calibration and comparison plots in PNG and SVG |

The comparison's `P/Ph` uses the **July 3 ESC-sum hover reference**. It does not
establish independently calibrated whole-aircraft watts. The two highlighted
approximately 17 m/s results are beyond the fitted bin range; all retained
comparison bins remain visible and downloadable.

The separate command `multicopter-range analyze-calibration --graphs` keeps
the historical fixed **G28 / 12.4 kg preset**. It has no mass or propeller
options. Use the examples above for the explicit G29 experiment. A wheel
installation also needs `--data-root` pointing to the public July 3 data in a
repository clone; wheels omit telemetry.

## 3. Evaluate or transfer a fitted curve from Python

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
