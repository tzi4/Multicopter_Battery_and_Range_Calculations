# Try a real flight CSV in a few minutes

This starter contains the Python calculator, a compact CSV derived from one real
July 3 flight, and an editable example. It fits the same three models through
the generic CSV interface you will use for your own logs. The full 126 MB
calibration archive is not required.

The CSV has **2,527 samples** and occupies about **175 KiB**. The unchanged
default filters retain three speed bins spanning **7.92–11.09 m/s**. Other
speeds remain in the file, but do not meet all of the fit's steady-flight bin
requirements; plotted speeds outside that interval are extrapolation.

The data describe the author's aircraft. This is a working example of the input
and output format, not a new validation experiment or a fit for another vehicle.

## Download and run

Download the [CSV starter ZIP](https://tzi4.github.io/Multicopter_Battery_and_Range_Calculations/downloads/csv-starter.zip),
extract it, and open a terminal inside `multicopter-csv-starter`.
Python 3.10 or newer is required. On Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python examples/csv_starter.py
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python examples/csv_starter.py
```

Installation downloads the Python dependencies. Once installed, the example
works locally without a network connection. If you already installed the full
repository, run `python examples/csv_starter.py` from that clone instead.

## Inputs you can edit

Open `examples/csv_starter.py`. No command-line flags are needed.

| Input | What to supply |
|---|---|
| `CSV_PATH` | Your synchronized CSV; the default is `data/starter/flight.csv`. |
| `OUTPUT_DIR` | Folder for the saved fit, figures and report. |
| `LOG_HOVER_POWER_W` | Measured hover power on the same sensor basis as the CSV's `power_w`. |
| `PREDICTION_HOVER_POWER_W` | Calibrated whole-aircraft hover power for the future-flight estimate. |
| `USABLE_ENERGY_WH` | Battery energy available for the modeled flight segment, after your reserve. |
| `PLANNED_SPEED_MS` | Constant speed to evaluate in the report and terminal output. |
| `MAX_PLOT_SPEED_MS` | Upper speed shown by the two figures. |
| `OPTIONS` | Explicit speed-bin, sample-count and stability thresholds. |

Aircraft geometry and battery defaults are in `examples/aircraft_inputs.py`:
12.4 kg, four rotors, G29, 450 cm² and two 6S 27 Ah Li-ion packs. Replace them
with your measured configuration before fitting your own flight. Mechanical RPM
comes from the CSV when available; otherwise the supplied aircraft RPM is used.

The CSV columns are:

```csv
time_s,vx_ms,vy_ms,vertical_speed_ms,pitch_deg,roll_deg,power_w,rpm
```

Times are seconds on one flight clock, velocities are m/s, angles are degrees,
power is watts and RPM is mechanical revolutions per minute. Keep the original
time gaps. Align external telemetry before exporting; do not concatenate flights
whose clocks restart. See the [complete input guide](https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations/blob/main/docs/USAGE.md)
for required fields and the alternative ArduPilot BIN workflow.

## What the example writes

The script fits the CSV, exports all four files, then reloads the saved JSON
and predicts at the requested speed. Look in `starter-output/`:

| File | Contents |
|---|---|
| `aircraft-fit.json` | Coefficients, calibration observations and metadata for later reuse. |
| `power_ratio.png` | Three fitted power-to-hover ratios versus ground speed. |
| `range_endurance.png` | Range and endurance versus speed, using the entered power and energy. |
| `fit-report.md` | Aircraft inputs, data coverage, power/energy references, predictions and links to the other files. |

The report identifies the fitted speed-bin range and labels predictions outside
it as extrapolation. It also retains any fit diagnostics. Sample counts and
calibration results do not establish accuracy on a future flight.

The included `data/starter/expected-results.json` records the default sample
counts, speed range and predictions. It is also available in the
[repository](https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations/blob/main/data/starter/expected-results.json).
It lets you check that your installation reproduces the example. Changing the
CSV, inputs or filtering options will change those outputs.

With the default inputs, the 10 m/s predictions are:

| Model | Power [W] | Endurance [min] | Range [km] |
|---|---:|---:|---:|
| Zeng-inspired | 1436.302 | 42.066 | 25.240 |
| Faessler-inspired | 1437.999 | 42.016 | 25.210 |
| Kirschstein-inspired | 1436.168 | 42.070 | 25.242 |

These are the starter's modeled operating-point outputs under the energy
scenario below, not measured flight ranges or the full archive's published fit.

## The example's two power references

The CSV retains the recorded four-ESC electrical sum. Its normalization reference
is **757.891 W**, inherited from the published July 3 analysis. The absolute
prediction uses the author's separate historical scenario: **1485.694254 W**
hover and **1006.992 Wh** after reserve. The CSV power is not silently doubled.
This distinction appears in every generated report.

That historical conversion has an unresolved sensor-boundary assumption; it
does not establish a new whole-aircraft measurement. For your own aircraft,
use calibrated power and energy. The preflight CF is not applied to these
fitted predictions, and reserve is not deducted again.
See [the recovered author inputs](https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations/blob/main/docs/AUTHOR_DEFAULTS.md).

## Reuse the result

After fitting once, load the JSON on a later day:

```python
from flight_workflow import FlightFit

fit = FlightFit.load("starter-output/aircraft-fit.json")
predictions = fit.predict(10.0, hover_power_w=1485.6942539603501,
                          usable_energy_wh=1006.992)
print(predictions)
fit.write_report("starter-output/next-estimate.md",
                 hover_power_w=1485.6942539603501,
                 usable_energy_wh=1006.992, speed_ms=10.0)
```

No raw logs are read by this step. The aircraft and fitted coefficients remain
those of the saved model; changed payload, propulsion or flight conditions need
a new check.

The CSV selection and source hashes are recorded in `data/starter/README.md`
and `data/starter/provenance.json`. The ZIP's `bundle-manifest.json` identifies
the included source files and their hashes. The complete research reproduction,
papers and live HTML explorer remain in the
[main repository](https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations).
