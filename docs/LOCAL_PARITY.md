# Comparing the original local calculator with the public package

The public workflow separates the original program's two stages into callable
Python functions: a Bauersfeld preflight estimate and a flight-calibrated power
model. Saving a fit to JSON makes the second stage reusable without parsing the
logs again. This is a change in how the calculation is used, not a new set of
Zeng or Faessler equations.

The comparison in [current-local-comparison.json](results/current-local-comparison.json)
executes the author's original `menzil2.py` and the current package with the
same aircraft inputs. Each implementation independently parses the July 3
files. The archive source is identified by SHA-256, and the source file is left
unchanged. This is a software comparison, not a measurement of flight accuracy.

## Results from the current comparison

All 32 required input files match the original archive: 31 are byte-identical,
and the attitude CSV differs only in line endings. Both implementations recover
46,175 joined samples, the same 757.891 W ESC-sum hover reference, and the same
11 calibration-bin observations.

The same-input comparisons evaluate 251 speeds per model, from 0 to 25 m/s:

| Quantity | Result |
|---|---|
| Bauersfeld outputs, both G28 and G29 scenarios | Identical |
| Zeng fitted curves, matched geometry | Identical |
| Faessler fitted curves, matched geometry | Identical |
| Kirschstein fitted curve, G28 geometry | Maximum relative difference 0.0818% |
| Kirschstein fitted curve, G29 geometry | Maximum relative difference 0.1273% |
| Current fitted curves after JSON save/load and Python API prediction | Maximum absolute `P/Ph` difference `4.44e-16` |
| LiPo, Li-ion and LiHV energy examples | Identical |

The small Kirschstein differences are caused by the intentional disk-area
correction described below. The JSON/API discrepancy is floating-point
rounding. Separating the workflow and saving coefficients has therefore not
changed the substantive curve calculations.

Comparing the actual **historical G28 fit** with the **current G29 fit** also
includes the requested geometry change:

| Model | Historical `P/Ph` at 17 m/s | Current `P/Ph` at 17 m/s | Maximum relative curve difference over 0–25 m/s |
|---|---:|---:|---:|
| Zeng-inspired | 1.232941 | 1.227333 | 1.40% |
| Faessler-inspired | 1.220295 | 1.213738 | 1.66% |
| Kirschstein-inspired | 1.247823 | 1.242123 | 1.49% |

These percentages describe differences between two software/scenario outputs.
They are not prediction errors against a flight. With the recovered electrical
basis, the current Faessler example at 17 m/s gives 1803.24 W, 33.51 minutes and
34.18 km. This is a constant-speed scenario beyond the fitted bin range, not a
measured mission range.

## The recovered correction factor

The author's saved July 28 console output prints **CF = 0.6159**, and the July 29
fit report records **CF = 0.616**. The exact value recovered by executing the
original reference calculation is **0.6159319356120826**, approximately 0.62:

```text
Reference aircraft: 19.5 kg, four P80 motors
Battery energy basis: four 6S, 17 Ah packs = 1761.2 Wh under the archive's LiHV rule
Hover power from the reference thrust table: 1859.6217 W
Theoretical hover duration: 56.8244605879 min
Reference hover duration recorded in the original code: 35 min
CF = 35 / 56.8244605879 = 0.6159319356120826
```

The author used this empirical adjustment in the team's own aircraft work,
including aircraft with cylindrical arms. It is an aircraft/project correction
to the duration and energy basis, not a universal coefficient from Bauersfeld's
paper or a validated constant for every cylindrical-arm design. Its reference
duration and battery assumptions are part of the calibration. Use your own
measurements to replace it when applying the preflight estimate to another
aircraft. The `0.72` found in older comparison scripts is a test input, not the
standard CF printed by the latest saved run.

The original program already used a different basis for the fitted graphs.
Its latest saved report explicitly labels `1198.8 Wh * CF 0.616` as a legacy
menu audit that is **not used for those graphs**. The graph calculation uses
the adopted usable-energy fraction `25.2 / 27`, a stated reserve, and its
calibrated hover-power basis. Applying CF again would change that basis twice.

## Author inputs and version differences

The current editable example uses the requested G29 propeller, 12.4 kg, four
rotors, 450 cm² reference area, and two 6S 27 Ah Li-ion packs. The nominal energy
is 1198.8 Wh. The archived July 29 report has that same nominal energy and
1118.88 Wh before the separate flight reserve.

For the postflight example, the archive's entered-aircraft convention gives
1485.6942539603501 W: the G29 thrust-table estimate multiplied by the historical
electrical scale derived from the G28 fit preset. This reproduces the saved
report's rounded 1485.7 W. A 10% reserve leaves 1006.992 Wh. This is a retained
scenario assumption, not an independently established whole-aircraft hover
measurement: the original conversion doubled the ESC power sum, and its sensor
topology has not been independently verified. Change the example's hover power
and usable energy together when you have measured whole-aircraft inputs.

Three differences must be separated when comparing old screenshots:

1. The historical fitted source preset used **28 inches**, even when the entered
   target aircraft used G29. The current showcase declares **29 inches** as
   requested by the owner. This changes rotor area, induced speed and tip speed.
2. The current Kirschstein component corrects the rotor term from `N * r` to
   total disk area `N * pi * r²`. The correction and supporting sources are
   recorded in [References](REFERENCES.md). Identical Kirschstein results are
   therefore neither expected nor claimed.
3. Fitted graph range and duration depend on the supplied electrical basis.
   Earlier public examples used illustrative 1500 W / 1100 Wh inputs. The author
   example now uses the recovered scenario above so these inputs are visible
   and editable in [aircraft_inputs.py](../examples/aircraft_inputs.py).

The newest local archive already uses the same empirical LiHV adjustment
(`3.7 * 7 / 6` V per cell-equivalent) as the current package. The earlier
LiHV version boundary in [Numerical validation](VALIDATION.md) does not cause a
difference against this particular archived source.

## Repeating the optional archive comparison

Normal users do not need the author's private working directory. The public
calibration examples and saved JSON are sufficient for their documented use.
An owner with a trusted copy of the original source and data can repeat this
additional audit:

```bash
python examples/compare_local_archive.py /path/to/original/archive
```

That directory must contain `menzil2.py`, its original July 3 data directory,
`flight_attitude_00000075.csv`, and `datalink_fit_method_report.md`. The script
imports the supplied Python file, so use your own trusted archive. It writes
the comparison JSON in the public repository, without editing the original
source, logs or report. Both 28-inch and 29-inch scenarios are evaluated on
251 speed points from 0 to 25 m/s for each of the three models. A separate
comparison records the actual historical G28 to current G29 profile change.
