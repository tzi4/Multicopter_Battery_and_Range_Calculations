# Reproducing the 0.1.2rc1 experiments

The current experiment declares a G29*9.5 CF propeller configuration and fits
the corrected model implementation. Calibration can be rebuilt from public
July 3 raw logs. The July 21 comparison can be replayed from public derived
rows; its raw-log extraction and clock alignment remain a separate local
step. Neither calculation establishes flight-wide model accuracy.

To rebuild both experiments and the README figures together:

```bash
python examples/reproduce_showcase.py --prop-diameter 29 --mass 12.4 \
  --output-dir showcase-output --check-results docs/results
```

The output directory contains both JSON summaries, the bin CSV tables, and
standalone PNG/SVG figures under `figures/`. The individual commands below
allow either experiment to be inspected separately.

## July 3 calibration from raw inputs

Install this source version as described in the README, then run from the
repository root:

```bash
python examples/reproduce_calibration.py \
  --data-root data/calibration/2026-07-03 \
  --prop-diameter 29 --mass 12.4 \
  --output-dir calibration-output \
  --check-summary docs/results/calibration-summary.json
```

The helper defaults to 29 inches and 12.4 kg, but the explicit arguments record
the intended scenario. The aircraft owner selected G29; 12.4 kg is an input
assumption for this run. Reported masses of 12.4, 12.8 and 13 kg need not refer
to the same flight. Telemetry does not establish a shared measured mass.
To examine another mass, change `--mass`, use a separate output directory and
omit `--check-summary` unless a reference for that exact scenario is available.
The supported 28-inch comparison is selected with `--prop-diameter 28`.

The helper writes `calibration-summary.json` and `calibration-audit.md`. The
stored [summary](results/calibration-summary.json) records package/source
identity, raw-input hashes, declared geometry, bins, model curves and residuals.
The [scientific audit](results/calibration-audit.md) provides fit details.
`--check-summary` compares provenance exactly and numeric values using `1e-9`
absolute/relative tolerance. Compare the same code version, inputs and
scenario; the module SHA-256 is byte-sensitive, including line endings.

Wheels omit the large raw logs. A wheel installation can run the same helper
from a repository clone with `--data-root` pointing to that clone's public
calibration directory. The legacy command
`multicopter-range analyze-calibration --data-root ...` remains a fixed
**28-inch, 12.4 kg preset**; it does not select the G29 experiment above.

## July 21 replay from derived observations

```bash
python examples/reproduce_validation.py \
  --calibration-root data/calibration/2026-07-03 \
  --validation-root data/validation/2026-07-21 \
  --prop-diameter 29 --mass 12.4 \
  --output-dir validation-output \
  --check-summary docs/results/validation-summary.json
```

This rebuilds the current July 3 fit, freezes its coefficients, and evaluates
the published July 21 derived observations. It writes `validation-summary.json`
and `validation-bins.csv`; see the stored
[validation summary](results/validation-summary.json) and
[derived-data provenance](../data/validation/2026-07-21/README.md).
The replay exposes all nine bins from the scalar-acceleration-gated first-ten-
lap selection, all sixteen from the historical first-ten-lap selection, and
the separate historical post-intervention selection. Here **historical names
describe selection rules**, not the model implementation: all replay
predictions use the current fit and declared geometry. Both dates are
normalized by the **July 3 ESC-sum hover reference**. July 21 does not supply
an independent hover denominator, and the curve is not transferred to a
separately established July 21 mass. Cancellation of an unknown electrical
scale requires that scale to remain identical across the two dates.

Public derived rows allow readers to inspect selection and residual
calculations. They do not reproduce the original BIN/UDAT decoding, establish
sensor wiring or prove clock synchronization. The retained joins used a
`-56.18 s` DataLink shift against a GPS-based coordinate that is 18 seconds
ahead of actual UTC. A `-74.18 s` shift would preserve those joins if the flight
timestamps were corrected to UTC. See [Methodology](METHODOLOGY.md) for this
limitation and the scope of the scalar acceleration gate.

### Why two old bins showed about 0.3–0.6%

The previously reported values correspond to approximately `+0.2719%` and `+0.6109%`
Zeng residuals at two high-speed bins in the old first-ten-lap selection without
the extra acceleration gate. They are not whole-flight errors, an average over
all selected bins, or results for the newly corrected G29 model. Other bins
had materially larger errors: the same historical selection's Zeng mean
absolute residual over all sixteen bins was about 10.82%, as recorded in the
[source-pinned historical summary](https://github.com/tzi4/Multicopter_Battery_and_Range_Calculations/blob/081da67771f68ab89b6d1f057c58684456ed8c3e/docs/results/july21-local-summary.json).
The public replay reports complete selections with current predictions.

July 3 MAE is a dimensionless absolute error in normalized power. July 21
percent residual is `100 * (observation / prediction - 1)`, with mean absolute
residuals computed equally over selected bins. Frozen coefficients do not
remove uncertainty in mass, hardware, wind, clock alignment or selection.
The comparison is retrospective, not prospectively blinded.

## Electrical interpretation and version boundaries

The measured input to the fit is the four-ESC sum of `voltage × current`.
Single-branch and doubled vehicle values in legacy reports are a conditional
archive convention: physical wiring is unverified, and a parallel battery
count alone does not justify multiplying the ESC sum by two. The adopted
25.2 Ah capacity basis is not remeasured by this flight. Absolute endurance
therefore remains conditional on the chosen energy/power scenario.

The `0.1.1rc1` audit is preserved in
[Historical audit](HISTORICAL_AUDIT_0.1.1rc1.md), with result links pinned to its
source commit. It used 28-inch preset metadata and the earlier Kirschstein
radius error. `0.1.2rc1` corrects that term to total disk area and uses area
scaling in transfer; [References](REFERENCES.md) identifies the supporting
paper and corrigendum. Old numerical-equivalence records and test counts
apply to their named hashes, not the corrected source or new G29 experiment.
Public July 3 telemetry is retained; changed model results are recorded with
new source provenance.

Run the current software checks with:

```bash
python -m pytest -q
python -m pip check
```

Repository CI checks supported Python versions and installed-wheel
reproduction. Source code publication, a prepared release candidate, a GitHub
release and a PyPI upload are distinct events; candidate metadata alone does
not establish that a release or package upload occurred.
