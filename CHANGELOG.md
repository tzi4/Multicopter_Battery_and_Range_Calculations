# Release notes

## 0.1.2rc1 — 2026-09-07

- Add README flight plots, downloadable bin tables, derived July 21 telemetry
  and scripts to reproduce both calibration and later-flight comparisons.
- Declare G29×9.5 and mass explicitly in the reproduction examples; retain the
  legacy CLI's fixed G28 profile for historical comparisons. Record unknown
  flight-specific mass and sensor wiring as assumptions.
- Cite the four model papers, Kirschstein's corrigendum and official technical
  documentation, with an equation-to-code mapping and BibTeX.
- Correct Kirschstein profile power to use total rotor disk area `N π r²`,
  including squared-radius scaling during transfer. Add area regression checks.
  The Zeng and Faessler implementations are unchanged.
- Preserve prior numerical audits as historical evidence. Report all retained
  comparison bins; two old sub-percent results are not an overall accuracy claim.

This is a local release candidate; these notes do not imply a published tag,
GitHub release or PyPI upload.

## 0.1.1rc1 — 2026-09-07

Release candidate. The version in `pyproject.toml` is `0.1.1rc1`; the proposed
tag is `v0.1.1rc1`. These notes do not imply a published GitHub or PyPI release.

- Allow `analyze-calibration --data-root PATH` to use the public July 3 data
  from a wheel installation. Select the attitude prior from that same directory
  and explain missing data in CLI errors.
- Reject NaN and infinite physical inputs in `calculate`.
- Add a compact calibration reproduction example with source/input SHA-256
  hashes, model residuals, and explicit branch/vehicle power and energy.
- Correct setup examples and report labels; document why the old 168.1 m/s
  tip-speed report predates the `10/21` RPM correction.
- Mark diagnostic curves as dashed outside the actual measured-bin interval
  and keep each model's color consistent across that boundary.
- Separate public calibration reproduction, historical numerical regression,
  and the local July 21 held-out comparison in the research audit.
- Exercise a clean wheel installation outside the checkout in CI on Python
  3.10 and 3.12, in addition to the existing test suites.

The retained numerical models, RPM scale, battery chemistry conventions,
calibration inputs, and author/license attributions are unchanged. The July 21
raw logs remain in the local research archive; this candidate adds no raw logs.

See [reproduction evidence](docs/REPRODUCIBILITY.md) for commands, values, and
the limits of the validation claim.
