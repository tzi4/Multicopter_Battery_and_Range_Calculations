# Multicopter Battery and Range Calculator

**From real flight telemetry to reproducible multicopter power and range estimates.**

Fit and compare three power–speed models, estimate endurance and range, and
trace the results back to ArduPilot and T-MOTOR DataLink measurements. The
repository includes the calibration logs, later-flight comparison data,
publication-ready figures, and the scripts that connect them.

**46,175 calibration samples · 30,782 later-flight samples · 3 model families · 4 research papers**

## Features

- Estimates best-range speed, best-endurance speed, flight time, and range.
- Parses ArduPilot `.BIN` logs and T-MOTOR DataLink `.udat` telemetry.
- Fits Zeng, Faessler, and Kirschstein power-speed model families.
- Includes the complete 3 July 2026 calibration data set used by the tests.
- Transfers fitted physical parameters to another mass/rotor/propeller setup.
- Produces empirical and diagnostic plots for audit and comparison.

## Flight results

**Aircraft scenario:** T-MOTOR U8 Lite KV190 · G29×9.5 CF · four rotors ·
6S · 12.4 kg assumed. Every plotted observation has downloadable data and a
reproducible calculation. Flight-specific mass is an explicit analysis input;
see the [configuration audit](docs/FLIGHT_CONFIGURATION.md).

![July 3 measured speed bins, fitted curves and calibration residuals](docs/assets/calibration.png)

**Calibration:** 46,175 joined telemetry samples; 28,095 retained samples in
11 speed bins spanning 2.46–12.34 m/s. All retained bins are shown. Errors here
are measured on the data used to fit the curves. [Bin data](docs/results/calibration-bins.csv)
and [source hashes and full results](docs/results/calibration-summary.json).

![July 21 observations compared with fixed July 3 models, with residuals for every retained bin](docs/assets/validation.png)

**Later-flight comparison:** the July 3 coefficients remain fixed. All nine
bins retained by the documented July 21 selection are shown. This is a
retrospective comparison using ground speed; its timing and filters were
developed after inspecting the flight. Both dates use July 3's hover reference;
flight-specific mass changes have not been compensated.
[All bin results](docs/results/validation-bins.csv)
and [30,782 derived telemetry rows](data/validation/2026-07-21/).

| Fixed July 3 model | July 21 mean absolute percent residual, all nine bins |
|---|---:|
| Zeng | 11.76% |
| Faessler-inspired | 11.70% |
| Kirschstein-inspired | 12.01% |

The residual is `100 × (observation / prediction − 1)`; the table averages
its absolute value equally over the nine bins.

**Mass sensitivity:** a separate sweep tests all 49 combinations of July 3 and
July 21 masses from 12.4 to 13.0 kg. The lowest mean absolute residuals using
the models' transferred hover power are **10.96% / 10.80% / 11.27%** for
Zeng / Faessler / Kirschstein, at 12.4 kg → 13.0 kg. These masses were selected
against the comparison data; they are exploratory scenarios, not measured
flight weights. [All combinations, assumptions and reproduction](docs/MASS_SENSITIVITY.md).
Some bins worsen: the largest absolute residuals at those choices are
28.2–28.9%, so the lower mean is not an improvement at every speed.

An earlier G28 analysis recorded **absolute residuals of 0.27% and 0.61% in two
approximately 17 m/s bins**. Those are individual-bin results under an older selection,
rather than an overall accuracy score. Both selections are available in the
public replay; see [reproduction and error definitions](docs/REPRODUCIBILITY.md).

Reproduce the data tables and figures after installation:

```bash
python examples/reproduce_showcase.py --prop-diameter 29 --mass 12.4 \
  --output-dir showcase-output --check-results docs/results
```

To compare mass scenarios, change `--mass` and omit `--check-results`. The plots report
normalized electrical power; absolute endurance additionally depends on the
battery-energy and current-sensor interpretation described in
[Methodology](docs/METHODOLOGY.md).

## Requirements

- Python 3.10 or newer
- Space for the repository history, the 126 MB calibration inputs, and a Python
  environment (allow at least 1 GB for a fresh clone and installation)

## Installation

```bash
git clone https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations.git
cd Multicopter_Battery_and_Range_Calculations
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows PowerShell, create and activate the environment with:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Quick start

Run a calculation from measured hover power and battery energy:

```bash
multicopter-range calculate \
  --hover-power 1500 \
  --battery-energy 1200 \
  --mass 12.4 \
  --drag-area 450 \
  --prop-diameter 28 \
  --rotors 4 \
  --correction-factor 0.93
```

Input definitions:

- `--hover-power`: measured electrical power for the **whole aircraft** during
  steady hover, in watts. Do not enter per-motor power.
- `--battery-energy`: energy basis for the whole battery pack, in watt-hours.
  Use nominal energy only when the correction factor accounts for unusable
  capacity; otherwise enter an independently measured usable-energy value.
- `--mass`: takeoff mass including the battery and payload, in kilograms.
- `--drag-area`: the projected reference area used by the Bauersfeld regression,
  in square centimetres. This is not the aerodynamic `CdA` used by the fitted
  forward-flight models.
- `--prop-diameter`: one propeller's diameter, in inches.
- `--rotors`: total load-bearing rotor count.
- `--correction-factor`: a dimensionless multiplier applied to available energy
  in the range/endurance calculation. Use `1.0` when `--battery-energy` is
  already usable energy. A value such as `0.93` means 93% of the entered energy
  is treated as usable. The tool does not infer this value for a new aircraft.

The example above produces:

```text
Induced hover velocity: 5.590 m/s
Best-range speed: 10.934 m/s
Best-range flight time: 40.879 min
Maximum range: 26.819 km
Best-endurance speed: 6.711 m/s
Maximum endurance: 48.840 min
```

The same command works without installation:

```bash
python multicopter_range.py calculate --hover-power 1500 --battery-energy 1200 \
  --mass 12.4 --drag-area 450 --prop-diameter 28 --rotors 4 --correction-factor 0.93
```

Rebuild the fitted models from the included raw logs:

```bash
multicopter-range analyze-calibration
```

Add `--graphs` to write `empirical_datalink_power_curve.png` and
`diagnostic_datalink_surrogate_fits.png`, plus `scientific_model_fit_audit.md`,
in the current directory. These are calibration diagnostics.

For a compact audit with input hashes, electrical measurements, and
per-model residuals:

```bash
python examples/reproduce_calibration.py \
  --data-root data/calibration/2026-07-03 --output-dir calibration-output
```

The example defaults to the G29 / 12.4 kg scenario shown above: 46,175 joined
samples, 11 stable speed bins and a tip-speed statistic of 82.912632 m/s.
The legacy `analyze-calibration` command retains its fixed G28 / 12.4 kg preset.
See the [reproduction and research audit](docs/REPRODUCIBILITY.md) for measured
results, the old 168.1 m/s report discrepancy, and the separate July 21 check.

Wheels and source distributions contain the calculator code but omit the large
flight logs. After installing a wheel, point to the data in a repository clone:

```bash
multicopter-range analyze-calibration --data-root /path/to/repository/data/calibration/2026-07-03
```

The directory must include both BIN logs, the DataLink sessions, and
`flight_attitude.csv`. This command uses the fixed July 3 aircraft profile;
the option relocates that data set and does not configure a new aircraft.

## Calibration data

The required raw logs are committed under
`data/calibration/2026-07-03/`:

```text
data/calibration/2026-07-03/
├── 00000076.BIN
├── 00000077.BIN
├── flight_attitude.csv
└── Datalink/
    └── UART-260703-*/
        └── *.udat
```

The `.BIN` files provide vehicle state and speed. The `.udat` files provide
per-motor voltage, current, and RPM. Both sources are needed because the
pipeline time-aligns them before creating stable speed bins. See
[the data notes](data/calibration/2026-07-03/README.md) and
[the methodology](docs/METHODOLOGY.md) for assumptions and known limitations.
The directly parsed power is the sum of four ESC `voltage × current` records.
The archive's additional factor of two assumes a particular sensor layout;
the physical wiring has not been established from these logs. Parallel battery
count alone does not justify doubling ESC power.

> [!IMPORTANT]
> The raw ArduPilot logs contain the original flight's GPS positions and
> non-secret autopilot parameters. Review this before redistributing the data.

The largest file is approximately 83 MB. Git LFS is not required; every file is
below GitHub's 100 MB per-file limit.

## Testing

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

The full suite parses the real flight logs and may take around one minute.
For a fast unit and numerical-regression check:

```bash
python -m pytest -q tests/test_numerical_regression.py tests/test_transfer.py
```

The old and public implementations were also executed side by side over broad
input grids and the complete bundled telemetry set. See
[Numerical validation](docs/VALIDATION.md) for the exact comparison and scope.

## Project layout

- `multicopter_range.py` — calculator, telemetry parsers, model fitting, plots,
  and command-line interface.
- `data/calibration/2026-07-03/` — raw logs and the derived attitude input needed
  to reproduce the calibration.
- `tests/test_transfer.py` — model and physical-transfer unit tests.
- `tests/test_numerical_regression.py` — representative outputs captured from
  the pre-cleanup implementation.
- `tests/test_calibration.py` — end-to-end tests against the included logs.
- `docs/METHODOLOGY.md` — model basis, calibration decisions, and limitations.
- `docs/VALIDATION.md` — old-versus-public numerical equivalence evidence.
- `examples/reproduce_calibration.py` — compact calibration audit and input hashes.
- `examples/analyze_mass_sensitivity.py` — separate flight-mass sweep with all 49 combinations.
- `docs/REPRODUCIBILITY.md` — current calibration and local July 21 audit scope.
- `CHANGELOG.md` — release candidate notes.

## Contributing and security

Bug reports and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md)
before submitting a change. For private vulnerability reports, follow
[SECURITY.md](SECURITY.md).

## Engineering scope

This is an experimental engineering model. Validate estimates on the target
aircraft and retain flight reserves. The G29 selection comes from the aircraft
owner; masses of approximately 12.4–13 kg varied between flights and have not
been established individually from telemetry. Timing, wind and electrical
calibration limits are documented in [Methodology](docs/METHODOLOGY.md).

## License

Released under the [MIT License](LICENSE).

## Research references

The general range/endurance calculator follows Bauersfeld and Scaramuzza.
Flight calibration uses Zeng-type power curves, a Faessler-inspired drag prior,
and a Kirschstein-inspired component model. These locally fitted adaptations
do not inherit the original papers' accuracy claims.

- Bauersfeld & Scaramuzza (2022), *Range, Endurance, and Optimal Speed Estimates
  for Multicopters*. [Paper](https://doi.org/10.1109/LRA.2022.3145063).
- Zeng, Xu & Zhang (2019), *Energy Minimization for Wireless Communication With
  Rotary-Wing UAV*. [Paper](https://doi.org/10.1109/TWC.2019.2902559).
- Faessler, Franchi & Scaramuzza (2018), *Differential Flatness of Quadrotor
  Dynamics Subject to Rotor Drag for Accurate Tracking of High-Speed
  Trajectories*. [Paper](https://doi.org/10.1109/LRA.2017.2776353).
- Kirschstein (2020), *Comparison of energy demands of drone-based and
  ground-based parcel delivery services*.
  [Paper](https://doi.org/10.1016/j.trd.2019.102209) and
  [2022 corrigendum](https://doi.org/10.1016/j.trd.2022.103457).

See the [equation-to-code mapping and technical sources](docs/REFERENCES.md)
and [downloadable BibTeX](docs/references.bib).
