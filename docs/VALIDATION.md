# Numerical validation

This document records the numerical comparison performed before publishing the
repository. It prevents a source-code cleanup from being mistaken for evidence
that the calculations stayed unchanged.

## Versions compared

- Previous implementation: commit `3d338ab33209d168a8393f167b96a316b7cd10ce`,
  entry point `menzil2.py`.
- Public cleanup: commit `1ebe0df9da7608b6014052156742f6ecb726b96d`,
  entry point `multicopter_range.py`.

Both modules were imported from isolated Git worktrees and called with the same
inputs. Comparisons used full-precision Python values rather than formatted
console text.

## Results

| Comparison | Values/cases checked | Maximum absolute difference |
|---|---:|---:|
| General Bauersfeld calculator | 1,000 aircraft configurations | 0.0 |
| Battery chemistry/energy calculation | 576 cases | 0.0 Wh |
| 31 motor tables and thrust interpolation | 217 points | 0.0 W |
| Core normalized power functions | 3,603 points | 0.0 |
| Flight time/range output values | 672 values | 0.0 |
| Fitted model parameters | 36 values | 0.0 |
| Four aircraft-transfer profiles | 120 parameters | 0.0 |
| Transferred model curves | 1,452 points | 0.0 |

The end-to-end calibration comparison additionally verified all 32 required raw
telemetry/support files by SHA-256. Their contents were identical before and
after the directory rename. Both versions then independently parsed the files.

| End-to-end result | Previous | Public cleanup |
|---|---:|---:|
| Joined samples | 46,175 | 46,175 |
| Measured hover power, sensed branch | 757.8910000000001 W | 757.8910000000001 W |
| Median propeller tip speed | 80.05357530658453 m/s | 80.05357530658453 m/s |
| Stable speed bins | 11 | 11 |

The comparison traversed 181,064 finite numeric values in the two complete
calibration result objects. The structures had no numeric paths unique to one
version, and the number of non-zero differences was zero.

## Persistent regression checks

`tests/test_numerical_regression.py` stores representative outputs from the
previous commit. `tests/test_calibration.py` checks the real-log pipeline,
including its joined-sample count, hover reference, tip speed, and speed-bin
vector. GitHub Actions runs these tests on Python 3.10 and 3.12.

## Scope and intentional differences

The public version is numerically equivalent for the retained calculator,
3 July calibration, fitted-model, and parameter-transfer paths. It is not an
identical user interface or feature set:

- The Turkish interactive menu was replaced by an English command-line
  interface.
- Public class/module names changed to English.
- Experimental one-off analysis scripts and generated figures were removed.
- The 21 July validation path was removed because its required raw data was not
  present in the repository, so that path could not be reproduced by users.

No equivalence claim is made for removed paths.
