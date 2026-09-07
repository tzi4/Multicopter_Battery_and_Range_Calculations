# Small real-flight CSV example

`flight.csv` is a 175 KiB, 2,527-row excerpt from the public July 3, 2026
flight `00000076.BIN` and its matching T-MOTOR DataLink session. It lets you
try the complete CSV-to-fit workflow without downloading the raw log archive.
The values come from recorded telemetry; no synthetic power or attitude is
inserted.

Run `python examples/csv_starter.py` after installing the project. Edit that
example to point at your own synchronized CSV and aircraft inputs. The
[usage guide](https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations/blob/main/docs/USAGE.md)
explains installation and the custom-flight workflow.

This is a teaching example from one specific aircraft, **not the published
aircraft calibration or a new accuracy evaluation**. Fit your own logs before
using the models for your aircraft. The declared example configuration is
12.4 kg, four U8 Lite KV190 motors, G29×9.5 propellers and a 0.045 m² reference
area; those are supplied inputs, not measurements inferred from this CSV.

## Columns

| Column | Meaning |
| --- | --- |
| `time_s` | Seconds from the selected BIN's first GPS anchor in the legacy join coordinate; not time since takeoff |
| `vx_ms`, `vy_ms` | North and east velocity from XKF1, in m/s |
| `vertical_speed_ms` | Vertical velocity in m/s, positive upward |
| `pitch_deg`, `roll_deg` | Recorded XKF1 attitude, in degrees |
| `power_w` | Sum of four valid DataLink ESC voltage × current readings, in watts |
| `rpm` | Median mechanical RPM across the four ESC slots, using the retained 10/21 conversion |

Horizontal ground speed is an airspeed proxy under approximately calm
conditions. The recorded ESC sum is a sensor basis; it is not automatically
calibrated whole-aircraft power. BAT current and the archive's conditional
power-doubling convention are not used to create this CSV.

## Selection and expected output

The exporter retains the **first real joined record in each fixed
0.75-second time bucket**, over all available data in this one flight. It
does not select by speed, power, attitude or fitted error. Values are rounded
to six decimal places. Missing time buckets stay missing, so the 23 gaps
longer than one second remain visible in `time_s`; samples from opposite
sides of a gap are not made consecutive in time.

The unmodified `FitOptions()` filters retain 1,665 steady samples and three
speed bins with median speeds of approximately **7.92, 10.92 and 11.09 m/s**.
Other speeds remain in the CSV but do not satisfy all of the generic fit's
steady-flight bin requirements. The 7.92–11.09 m/s interval is narrow: use
this example to learn the workflow, then collect steady segments across the
speeds you want to model. Plotting beyond this interval is extrapolation.

The log normalization reference is **757.891 W**, the published July 3
two-flight hover median on the same ESC-sum basis. It is deliberately carried
over as an external reference, not estimated from the thinned CSV. The
unthinned `00000076.BIN` join alone has a different hover median
(785.8225 W). Absolute example predictions separately use the author's
conditional historical scenario of 1485.6942539603501 W hover and
1006.992 Wh available after reserve. These quantities are not inferred from
this excerpt; see the
[author's input conventions](https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations/blob/main/docs/AUTHOR_DEFAULTS.md).

[expected-results.json](expected-results.json) records the exact supplied
inputs, selected bins and example predictions at 10 m/s. It is a reproducible
workflow result, not a claim of predictive accuracy.

## Provenance and regeneration

[provenance.json](provenance.json) records every source file's SHA-256,
the export script and model hashes, the CSV hash, column derivations and the
time-selection rule. The CSV contains no latitude or longitude fields.

Synchronization follows the retained archive parser: DataLink filename
times are interpreted as Europe/Istanbul local time and matched to the
nearest flight sample within 0.35 s. The legacy GPS helper omits the
18-second GPS-to-UTC correction applicable to July 2026. Reproducing that
alignment does not independently validate UTC synchronization. This
limitation applies to the source data and this example.

With the complete public archive in a repository clone, rebuild all three
generated files with:

```bash
python examples/prepare_starter_csv.py
```

The small starter download already includes the generated CSV; it does not
need the raw archive or this maintenance step. Original raw files remain
unchanged. Their
[data notes](https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations/blob/main/data/calibration/2026-07-03/README.md)
describe the source limitations in more detail.
