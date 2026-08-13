# Multicopter Battery and Range Calculator

An engineering toolkit for estimating multicopter endurance and forward-flight
range. It includes a general Bauersfeld-based calculator and a reproducible
power-versus-speed calibration pipeline built from real ArduPilot and T-MOTOR
DataLink flight logs.

> [!CAUTION]
> This is an experimental engineering model, not certified flight-planning
> software. Validate the estimates on your own aircraft and retain appropriate
> battery reserves.

## Features

- Estimates best-range speed, best-endurance speed, flight time, and range.
- Parses ArduPilot `.BIN` logs and T-MOTOR DataLink `.udat` telemetry.
- Fits Zeng, Faessler, and Kirschstein power-speed model families.
- Includes the complete 3 July 2026 calibration data set used by the tests.
- Transfers fitted physical parameters to another mass/rotor/propeller setup.
- Produces empirical and diagnostic plots for audit and comparison.

## Requirements

- Python 3.10 or newer
- About 300 MB of free space for the repository, virtual environment, and plots

## Installation

```bash
git clone https://github.com/tzi4/Multicopter-Battery-and-Range-Calculations.git
cd Multicopter-Battery-and-Range-Calculations
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows PowerShell, activate the environment with:

```powershell
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
  --mass 12.4 --drag-area 450 --prop-diameter 28 --rotors 4
```

Rebuild the fitted models from the included raw logs:

```bash
multicopter-range analyze-calibration
```

Add `--graphs` to write `empirical_datalink_power_curve.png` and
`diagnostic_datalink_surrogate_fits.png` in the current directory.

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

## Contributing and security

Bug reports and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md)
before submitting a change. For private vulnerability reports, follow
[SECURITY.md](SECURITY.md).

## License

Released under the [MIT License](LICENSE).
