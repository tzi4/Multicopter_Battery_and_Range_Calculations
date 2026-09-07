# Which example should I run?

These are the editable entry points for normal use. Install the project first,
then run the chosen file from the repository root with
`python examples/<filename>.py`. The [main README](../README.md#install) and
[small CSV starter guide](../docs/CSV_STARTER.md) explain installation.

| Your task | File | What to edit |
|---|---|---|
| Learn the workflow using the included small CSV | [`csv_starter.py`](csv_starter.py) | Run the defaults first; outputs go to `starter-output/`. |
| Fit your own synchronized CSV | [`csv_starter.py`](csv_starter.py) | `CSV_PATH`, hover-power references, usable energy, requested speed and aircraft inputs. |
| Fit your own ArduPilot BIN | [`postflight_fit.py`](postflight_fit.py) | `LOG_PATH`, monitor or ESC selection, calibrated power references, usable energy and aircraft inputs. |
| Estimate range and endurance before flight | [`preflight_estimate.py`](preflight_estimate.py) | Geometry, propulsion, battery and empirical correction in `aircraft_inputs.py`. |
| Run the author's complete two-stage example | [`analyze_aircraft.py`](analyze_aircraft.py) | Shared inputs; requires the full bundled July 3 archive. |
| Rebuild only the author's bundled fit and figures | [`bundled_flight_demo.py`](bundled_flight_demo.py) | Shared inputs and the output folder; requires the full archive. |

**Recommended path:** try `csv_starter.py`, then use that script for your own
CSV or `postflight_fit.py` for your own BIN. The fitting examples write
`aircraft-fit.json`, `power_ratio.png`, `range_endurance.png` and `fit-report.md`.

[`aircraft_inputs.py`](aircraft_inputs.py) holds the shared geometry and battery
defaults. In the own-log example, also replace the log path, normalization hover
reference and prediction power/energy with your measurements. The supplied
numbers describe the author's aircraft. The full bundled demonstration retains
its four-rotor, 450 cm² source-airframe assumptions.

## Where is the HTML?

The complete browser application is
**[`docs/aircraft-demo.html`](../docs/aircraft-demo.html)**, one directory up from
here and inside `docs`. It contains its JavaScript, styles and plotting library.
You can [open the live demo](https://tzi4.github.io/Multicopter_Battery_and_Range_Calculations/aircraft-demo.html)
or download the HTML and open it locally.

The HTML explores the author's existing Zeng model. Use the Python fitting
examples above to fit your own logs and compare all three models.

## Where are the calculation functions?

The repository root contains two importable modules:

- [`multicopter_range.py`](../multicopter_range.py): model equations, the
  Bauersfeld calculator, original parsers and fitting/transfer routines.
- [`flight_workflow.py`](../flight_workflow.py): `Aircraft`, log loaders,
  `fit_flight` and `FlightFit`. Load a saved JSON with `FlightFit.load`, then
  call `predict` for later estimates or `write_report` for a new report.

Normal input changes belong in the example scripts and shared settings.
The [usage guide](../docs/USAGE.md) documents the Python API and every input.

## Research and maintenance scripts

The `reproduce_*.py` scripts and `compare_local_archive.py` reproduce or audit
the published research. The rendering, sensitivity and starter-build scripts
maintain the repository's figures and downloads. The
[reproduction guide](../docs/REPRODUCIBILITY.md) covers the research workflow;
new users can begin with the runnable examples listed above.
