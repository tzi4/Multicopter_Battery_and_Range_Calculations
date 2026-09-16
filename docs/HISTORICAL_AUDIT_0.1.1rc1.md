# Historical audit — 0.1.1rc1

This document preserves the numerical findings of the 0.1.1rc1 audit.
The original audit document has SHA-256
`47eb7a20e669ef854ecf997ca8a4d98683f2e6c43ddc8aaee6d657d67e0b27eb`.
Historical supporting artifacts below are identified by their content hashes.
References to “current” code or results in this audit mean that historical
source version.
Use [the current reproduction guide](REPRODUCIBILITY.md) for `0.1.2rc1`.

**Corrections to interpretation:** the archived single-branch/×2 description is
an unverified wiring convention, not an established physical measurement. The
parser sums four ESC voltage/current products; a parallel battery count alone
does not justify doubling them. The 25.2 Ah energy basis is inherited from
prior analysis, not remeasured by the reproduced flight.

The archived run used the fixed **28-inch, 12.4 kg preset**. It does not
establish the propeller or measured mass of every flight. Its GPS-time helper
also omitted the 18-second GPS-to-UTC correction applicable to these 2026
logs. The July 21 `-56.18 s` offset therefore refers to that legacy coordinate;
`-74.18 s` is the equivalent DataLink shift in corrected UTC if the same joins
are preserved. Neither value is a universal device correction.

The archived Kirschstein implementation used rotor radius where disk area was
required. That error is corrected in the current source, as documented in
[References](REFERENCES.md). Old coefficients, residuals, tests and exact
archive/package equivalence below apply to their recorded source versions.
They do not establish numerical equivalence or validation of the corrected
G29 experiment. The original code publication did not publish a GitHub
release, tag or PyPI package.

---

# Reproduction and research audit — 7 September 2026

This release candidate makes a wheel installation usable with the public
calibration data and provides a compact, traceable audit. Three distinct checks
must be kept separate: reproducing the July 3 calibration, comparing old and
current code, and evaluating fixed July 3 fits on later July 21 observations.
Only the first two are reproducible from this public repository alone.

## Public reproduction

Follow the README installation, then run from the repository root:

```bash
python examples/reproduce_calibration.py \
  --data-root data/calibration/2026-07-03 --output-dir calibration-output \
  --check-summary docs/results/calibration-summary.json
python -m pytest -q
```

The example writes a JSON summary (historical `docs/results/calibration-summary.json`, SHA-256
`55e931cb5037dd97587cbcbb257d2e466240e3b2ee3a383d2794c1ba7446587b`) and a
generated scientific audit (historical `docs/results/calibration-audit.md`, SHA-256
`a10eaa0e9d2bddfc09c60aa7a71f63cb5ad9d5815679657cce20bb6b0e166b7b`). The JSON records
the installed module's SHA-256 and a complete inventory of all 32 telemetry
and support files in the supplied directory, including sessions not accepted
for fitting. The scientific report lists the accepted BIN logs and DataLink
sessions. `--check-summary` requires matching source/data provenance and compares
floating-point outputs within `1e-9` absolute/relative tolerance.
The source hash is byte-exact; use LF line endings for that comparison (a CRLF
conversion changes the hash even if the Python code has the same behavior).

These outputs were regenerated with Python 3.12.14. The example reads the
already-public raw inputs and exports aggregate quantities only.

| Executed check | Local result |
|---|---|
| Documented editable install and `calculate` example | Passed; 26.819 km, 48.840 min |
| Complete package suite after the plot correction | 60 passed in 31.43 s |
| Four existing local archive suites | 41 passed in 104.24 s |
| Wheel installed in a separate environment, run outside the checkout | CLI, plots, and stored-summary comparison passed |
| `pip check` in both environments | No broken requirements |
| Built wheel and source distribution | No raw telemetry; MIT license retained |

The general calculator example above and the calibration hover calculation
below have different inputs and models; their endurance figures are not the
same scenario. CI runs package tests and the isolated-wheel reproduction on
Python 3.10 and 3.12.

| Current result | Value |
|---|---:|
| Joined samples accepted for calibration | 46,175 |
| Stable samples in 11 speed bins | 28,095 |
| Measured speed-bin interval | 2.462475–12.338324 m/s |
| Tip speed, median of bin medians | 80.053575 m/s |
| Hover power, sensed branch / whole aircraft | 757.891 / 1515.782 W |
| Usable-energy basis, branch / whole pack | 559.44 / 1118.88 Wh |
| Joined-flight energy integral, branch / vehicle equivalent | 490.273344 / 980.546688 Wh |
| Modeled hover at 10% reserve | 39.860297 min |

The archive documents the one-branch sensing convention on a 6S2P pack. The
parser sums `voltage × current` over four ESC slots; the software cannot prove
sensor placement from those values. Under that convention, power and energy
must both be multiplied by two. The equal endurance calculation is
`60 × 0.9 × 559.44 / 757.891 = 60 × 0.9 × 1118.88 / 1515.782`.
The 25.2 Ah usable-capacity basis comes from the prior battery analysis, not
from integrating this partial flight. The original battery monitor current and
energy remain flagged as suspect; their values do not drive the power fit.

Calibration-bin MAE is the unweighted mean of `abs(predicted P/Ph - measured
P/Ph)` across 11 bins: Zeng `0.027664968`, Faessler `0.027670921`, Kirschstein
`0.027607748`. These are errors on the fitting data, not independent validation
scores. The closely matching curves are diagnostic surrogate fits.
The diagnostic plot now shades that measured-bin interval and uses matching
model colors with dashed curves outside it; the old fixed 18 m/s styling
boundary overstated the interval supported by the observed speed bins.

## Why the old report says 168.1 m/s

The archive's `scientific_model_fit_audit.md` predates the RPM correction.
The implemented motor convention is raw `eRPM/10`, with 21 pole pairs:
mechanical RPM = raw field × `10/21`. Consequently,
`168.112508 × 10/21 = 80.053575 m/s`. The current 28-inch preset converts that
tip-speed statistic to about 2149.76 mechanical RPM; it is a median across
speed bins, despite the legacy field name `hover_rpm_estimate`.

A controlled rerun changed only extracted RPM-derived tip speeds back to the
old scale and refit with unchanged electrical observations, speeds, and
weights. It recovered old Zeng `f0 = 0.817676` and `k_par = 6.903773e-5`.
The current values are `f0 = 0.787906`, `k_par = 5.477336e-5`. Thus the
archive's CLAUDE note quoting approximately `0.800` and `5.2e-5` is itself an
older intermediate result. Model predictions at measured bins change by at
most about `0.000405` in P/Ph; MAE changes slightly, not exactly zero.

The existing G28 datasheet thrust/RPM table gives about 2216 RPM at 3100 g per
rotor, a useful consistency anchor for the corrected scale. This is not an
independent protocol specification. A nominal-voltage KV estimate alone does
not prove the raw field impossible: fully charged 6S voltage is higher than
nominal voltage. No fresh claim about absolute RPM measurement accuracy is
made here.

## Local July 21 held-out comparison

The original local range calculator (SHA-256
`51a13396a005b8731ef1bd4b05dc94cc8606eed314465898d03a41678eff05cc`)
retains `run_july21_validation_against_july3`. That path was rerun in an
isolated directory against the local July 21 data. The July 3 coefficient
dictionary was checked before and after evaluation and was unchanged.
The public package intentionally omits this path because its raw inputs are
not bundled. The summary below is a local audit result; public readers cannot
independently reproduce it using this repository alone.

The current selection uses a `-56.18 s` DataLink clock correction, the first
10 uninterrupted laps, stable samples, and absolute scalar ground-speed
acceleration `<= 1 m/s²`.
Post-intervention observations are excluded. It joins 30,782 samples before
selection and produces nine selected speed bins. The old
`compare_july3_fit_july21_validation.py` was also rerun: it includes a separate
post-intervention phase and lacks the newer acceleration gate. Its residual
summary is therefore a different experiment.

| Fixed July 3 model | July 21 mean absolute percent residual across all nine bins |
|---|---:|
| Zeng | 11.8423% |
| Faessler | 11.6813% |
| Kirschstein | 12.0928% |

Percent residual is `100 × (observation / prediction - 1)`; the
table averages its absolute value equally over bins. It is not the July 3
MAE metric. Some approximately 17 m/s bins agree within a few percent, while
the worst selected-bin errors are about 25.6%. Those favorable high-speed
points do not establish overall model validity. Ground speed, filtering,
clock alignment, and aircraft metadata limit the inference.

In particular, the executed July 3 preset is **28 inches**. Some archive
comments describe July 3 as 29 inches and July 21 as 28 inches, but passing
29 into `build_speed_model_profile("1", ...)` does not override the fixed
28-inch preset. This audit reports executed metadata and does not infer the
historical propeller hardware from that inconsistent prose. The archive's
combined July 3 + July 21 fit is training on both dates, so it is not a held-out
validation result. The selection and clock alignment were developed after
examining the later flight, so this is not a prospectively blinded experiment.
The local comparison summary (historical `docs/results/july21-local-summary.json`, SHA-256
`e809ed49d099fbf2bfc1f671c0ae29b524a9f6052aae161ece3fb2ff3eb6ca5a`) records all
nine bins, the historical script's alternative selection, and source hashes.

## Source, attribution, and release scope

The starting public source was version `0.1.0`, with module SHA-256
`8f86c658d38ca0ad259e83acae18600254cca64d52c40b1d6a182fd4179f13a7`. Retained numerical
models and raw calibration data are unchanged in `0.1.1rc1`; external data
selection and CLI input/error handling are corrected. The prior
code-equivalence record (historical `docs/VALIDATION.md`, SHA-256
`138c19da9ce8118dc63c1a26f1cfcdbbabc0d2f711833cd63662a083bd64b939`) applies to its identified source versions and is
not being presented as a new rerun of every historical comparison grid.

A fresh, separate comparison imported the current Windows archive and the
current public package from isolated locations and independently parsed July 3.
All 362,018 shared finite numeric leaves of the resulting suites matched
exactly, with no numeric paths unique to either suite; 753 model-curve values
over 0–25 m/s also matched exactly. This compares the retained calibration and
curve outputs, not removed menus or the July 21 path. Of the 32 corresponding
source files, 31 are byte-identical; the attitude CSV differs only by CRLF/LF
line endings (13,790 lines). It is therefore text-equivalent, not byte-identical
to the Windows copy. The repository's own 32-file hashes are recorded as-is.
The compact comparison record (historical `docs/results/archive-package-comparison.json`, SHA-256
`6f4f110fa4d60950b2a944a0149e63c5ae0742a07d819a2d306bc7823f767ea3`)
identifies the compared module hashes and the scope of the numeric traversal.

The MIT license and both authors in `pyproject.toml` are retained. The
Bauersfeld/Scaramuzza reference remains in Methodology (historical `docs/METHODOLOGY.md`, SHA-256
`027a47fcd5fd484dffa18b5f8ee083ec43de0ac57655e33067632eafde1e6844`).
Local July research scripts and reports supplied the audit context. Secondary
battery-selection material was inspected locally; manufacturer PDFs and raw
July 21 logs were not copied into this repository. The existing published
July 3 files are unchanged. Remote Drive access was unnecessary because the
needed sources were present locally.

The release candidate is `0.1.1rc1`, proposed tag `v0.1.1rc1`; see
release notes (historical `CHANGELOG.md`, SHA-256
`ffbca05376b715ed51426c151ec306e150c16ae0f856edeb3e52224dd0473aa4`). A prepared candidate is not evidence of a
published GitHub release, a PyPI upload, downloads, or user adoption.
