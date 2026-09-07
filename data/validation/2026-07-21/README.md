# July 21 derived telemetry

`joined-samples.csv.gz` contains **30,782 joined telemetry samples** from the
author's July 21 research logs. It supports public replay of sample selection
and comparison against a separately fitted July 3 power curve. It contains
elapsed times, velocities, attitude, decoded ESC power/RPM/voltage, matching
distance and phase labels. Raw BIN files, absolute positions, device identifiers
and absolute sample timestamps are not included.

The dataset is provided under this repository's MIT license. Source filenames,
SHA-256 hashes, extraction settings and column units are recorded in
[`provenance.json`](provenance.json). The listed raw inputs are one ArduPilot BIN
and twelve DataLink files; some DataLink files contain no accepted flight
records. No July 21 samples are used to fit the replay's July 3 model.

## Replay

After installing the package as described in the project README, run from the
repository root:

```bash
python examples/reproduce_validation.py \
  --data-root data/calibration/2026-07-03 \
  --validation-root data/validation/2026-07-21 \
  --prop-diameter 29 --mass 12.4 \
  --output-dir validation-output
```

The script uses the installed `multicopter_range` module and the sibling public
calibration helper. It writes `validation-summary.json` and
`validation-bins.csv`. `--check-summary <saved-summary.json>` additionally
requires exact matching provenance and compares floating-point results within
`1e-9` absolute/relative tolerance.

The selected showcase configuration is **G29 × 9.5 CF, four U8 Lite KV190
motors, assumed 12.4 kg**. These are modeling inputs, not hardware or takeoff-mass
measurements recovered from this file. `--prop-diameter 28` and other positive
`--mass` values are available for explicitly declared sensitivity experiments.
The comparison uses frozen July 3 curves without a transfer to an independently
identified July 21 aircraft.

Every measured ratio uses the **July 3 ESC-sum hover-power reference**. The
replay does not estimate a new July 21 hover reference. A constant sensor factor
cancels only when it applies consistently to both dates; changed electrical
gain, offset or wiring would affect the comparison. Decoded ESC power is not
promoted to independently calibrated whole-aircraft power.

## Selections and metrics

The export retains all samples admitted by the historical timestamp join,
before the following stability and speed-bin selections. Each replay variant
uses the same current package and declared calibration configuration:

| Variant | Selection | Retained bins |
| --- | --- | ---: |
| `current_scalar_accel_gate` | First ten uninterrupted laps, with an additional scalar speed-acceleration limit of 1 m/s² | 9 |
| `historical_first10` | First ten uninterrupted laps, without that additional acceleration limit | 16 |
| `historical_post_intervention` | Separate post-intervention phase, without that additional acceleration limit | 16 |

The common package stability gate limits scalar speed acceleration to 8 m/s²,
vertical speed magnitude to 1.5 m/s, and roll/pitch magnitudes to 28°. Samples
are reduced into 1 m/s bins between 2 and 20 m/s, requiring 80 stable samples and
a stable fraction of at least 0.5. All retained bins are exported; small errors
at particular speeds do not establish accuracy across the full interval.

Percent residual is `100 × (measured_ratio / predicted_ratio − 1)`. The reported
mean absolute residual weights each retained bin equally. This differs from
the calibration-bin MAE in dimensionless `P/P_hover` units.

The word *historical* describes the earlier **selection policy**. These variants
recompute predictions using the current package; they do not reconstruct old
28-inch coefficients or an earlier Kirschstein implementation. The old report's
approximately 0.27% and 0.61% Zeng results belong to two individual high-speed
bins under its named historical configuration. Their exact reproduced values,
configuration and source-code hashes are retained separately in
[`historical-high-speed-bins.json`](historical-high-speed-bins.json). That record
contains two of the sixteen bins and is not an overall validation score.

## Time and extraction provenance

`elapsed_us` is an integer number of microseconds from the first exported joined
sample. The replay attaches an artificial epoch solely to reproduce time
intervals for the stability calculation. Phase bounds in `provenance.json` use
that same relative time coordinate; they are not absolute UTC timestamps.

The audited archive module has SHA-256
`51a13396a005b8731ef1bd4b05dc94cc8606eed314465898d03a41678eff05cc`.
Its `build_july21_joined_samples` selects the longest armed flight, finds the ten
uninterrupted `[2, 3, 4, 5]` mission laps, parses mechanical RPM as raw × `10/21`,
and joins DataLink to flight state with a maximum 0.35-second difference.

That historical loader converts GPS week/milliseconds into a UTC-labeled clock
without subtracting the 18-second GPS-to-UTC difference used by the installed
pymavlink reader. Its DataLink correction of **−56.18 seconds** therefore refers
to that legacy GPS clock coordinate. Relabeling both clocks into UTC while
preserving the same pairing would make the DataLink correction **−74.18 seconds**.
This export preserves the original pairing and does not claim a newly estimated
physical clock offset. Source and extraction-script hashes allow a local archive
owner to trace its origin; public replay starts from the derived CSV and does
not independently verify the unavailable raw decoder or phase identification.

The timing/filter policy was developed after examining this flight, so the
experiment is not prospectively blinded. Ground speed is not airspeed, and a
scalar acceleration threshold does not exclude constant-speed turns. Wind,
mission geometry, sensor calibration and uncertain aircraft configuration
remain limitations.
