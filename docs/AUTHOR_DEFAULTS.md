# The author's working inputs

The editable defaults in [`examples/aircraft_inputs.py`](../examples/aircraft_inputs.py)
recover the author's July 29 saved aircraft report and original standard-CF
calculation. They replace the earlier illustrative 1500 W / 1200 Wh / CF 0.93
example. The declared propeller remains G29, as selected by the aircraft owner.

| Input | Default | Basis |
|---|---:|---|
| Aircraft mass | 12.4 kg | Declared analysis mass; actual mass varied between flights. |
| Rotors | 4 | Quadrotor configuration. |
| Propulsion | U8 Lite KV190, G29×9.5 CF | Author-selected configuration. |
| Reference area | 450 cm² | Original aircraft input. |
| Battery | Two 6S, 27 Ah Li-ion packs | 1198.8 Wh at 3.7 V/cell; multiplying pack energy does not make this a physical 12S supply. |
| First-estimate hover power | 1101.6581197 W | Sum of four G29 manufacturer-table values at 3100 g thrust per motor. |
| First-estimate correction factor | 0.6159319356 | Original Vibe hover benchmark, detailed below. |
| Postflight hover basis | 1485.6942540 W | Calibrated entered-vehicle scenario from the saved report. |
| Postflight usable energy before reserve | 1118.88 Wh | Nominal energy multiplied by the archived 25.2/27 capacity fraction. |
| Postflight reserve | 10% | 1006.992 Wh remains for the modeled flight segment. |

## Why the CF is approximately 0.62

The original code derives its standard correction factor from the team's Vibe
reference aircraft: 19.5 kg, four P80 motors, four 6S 17 Ah LiHV packs and a
reported 35-minute hover. The archived energy convention gives 1761.2 Wh and
the motor table gives 1859.6217 W. The corresponding theoretical hover time is
56.8244606 minutes:

```text
CF = observed hover time / estimated hover time
   = 35 / 56.8244606
   = 0.6159319356
```

The author reports using this working correction on the team's own aircraft
with cylindrical arms. The recovered calculation establishes this particular
reference value; it does not establish one universal factor for all aircraft
with cylindrical arms. It is an empirical correction supplied to the
Bauersfeld-based calculator, not a coefficient taken from the Bauersfeld paper.

An empirical CF can absorb discrepancies in the energy basis and the
manufacturer-derived power estimate. It should not be interpreted as a direct
measurement that only 61.6% of a battery's charge is usable. In the code it
multiplies time and distance through the effective energy budget; it does not
change optimum speeds or the predicted normalized power curves.

The saved outputs round this factor to 0.6159 or 0.616. The earlier 0.72 value
belongs to comparison/test inputs. The earlier README's 0.93 was an illustrative
energy multiplier, separate from both the empirical CF and the archived
25.2/27 usable-capacity fraction.

## Why the fitted plots do not multiply by CF again

The latest saved report explicitly separates the standard-CF menu calculation
from the power/energy basis used for fitted-model graphs. Reproduce that basis
with:

```text
historical hover scale = (2 × 757.891 W) / 1123.9685039 W
entered G29 hover      = 1101.6581197 W × historical hover scale
                      = 1485.6942540 W
usable energy         = 1198.8 Wh × 25.2 / 27 = 1118.88 Wh
energy after reserve  = 1118.88 Wh × 0.90    = 1006.992 Wh
```

The 1123.9685039 W denominator is the historical G28 source-table hover
estimate. It is retained in this electrical scale to reproduce the saved
report, while the current demonstration's normalized curves use the declared
G29 fit. This is an explicit archived scenario, not a new sensor calibration.
The factor of two assumes the old branch-to-vehicle interpretation; the
physical wiring has not been established by these logs. A parallel-pack count
alone does not justify that multiplier. See [Methodology](METHODOLOGY.md).

The postflight Python example receives 1006.992 Wh as energy **after** reserve.
It applies neither CF nor a second reserve deduction. For another aircraft,
replace the inherited hover and energy basis with suitable calibrated inputs.

## One file to edit, one script to run

Edit [`examples/aircraft_inputs.py`](../examples/aircraft_inputs.py), then run:

```bash
python examples/analyze_aircraft.py
```

This runs the preflight calculation and then the bundled flight-data fit,
saved-model prediction and two plots. The separate stage examples remain
available. The bundled fit retains its four-rotor, 450 cm² source-airframe
assumptions; changing those requires your own calibration data rather than
silently reusing the archived airframe. [`examples/postflight_fit.py`](../examples/postflight_fit.py) is the
entry point for fitting your own BIN or synchronized CSV logs; it requires your
actual log path and calibrated sensor inputs.

The author's original long script combined these functions with an interactive
menu. The public calculator retains its numerical functions, while example
scripts and `flight_workflow.py` provide explicit Python inputs and saved fits.
The custom-log workflow has its own documented filters and attitude-prior
estimator; use the bundled reproduction path when comparing the published
July 3 experiment. See [local comparison](LOCAL_PARITY.md) for measured
differences between the current public and archived implementations.
