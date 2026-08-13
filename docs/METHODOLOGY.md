# Methodology and limitations

## Calculation model

The general calculator uses the optimum-speed relationships reported by
Bauersfeld and Scaramuzza together with measured hover power, battery energy,
total mass, rotor geometry, and projected reference area. The correction factor
multiplies the entered energy basis and is an explicit user input; it is not
silently inferred for arbitrary aircraft.

The fitted constants in `BauersfeldRangeCalculator` follow:

> Leonard Bauersfeld and Davide Scaramuzza, “Range, Endurance, and Optimal
> Speed Estimates for Multicopters,” *IEEE Robotics and Automation Letters*,
> 2022. [DOI: 10.1109/LRA.2022.3145063](https://doi.org/10.1109/LRA.2022.3145063).

The calculator uses the paper's projected-area input in square centimetres;
this input is distinct from the aerodynamic `CdA` terms used in the fitted
Zeng/Faessler/Kirschstein model implementations.

## Calibration pipeline

The bundled calibration combines two independent telemetry sources:

1. ArduPilot `.BIN` logs provide UTC alignment, vehicle state, and ground speed.
2. T-MOTOR DataLink `.udat` records provide per-motor voltage, current, and RPM.

Sessions are matched by time overlap. Samples are filtered for valid motor
count and plausible electrical/mechanical values, aligned to flight state, and
reduced to stable speed bins. The resulting normalized `P(V) / P_hover` points
are fitted with Zeng, Faessler, and Kirschstein model families.

Each fitted family is intentionally limited to two free parameters. Hover
power, induced hover velocity, and propeller tip speed are measured or derived
inputs rather than additional fit parameters. This constraint prevents an
apparently close curve from hiding an underdetermined model.

## Important calibration assumptions

- Calibration profile: 12.4 kg quadrotor, 28-inch propeller metadata, and an
  approximately 80 m/s measured hover tip speed.
- The calibration aircraft had a 6S2P battery. The DataLink current sensor saw
  only one parallel branch, so measured absolute power and energy represent half
  of the aircraft total. Power ratios are unaffected because the factor cancels.
- A measured usable capacity of 25.2 Ah is used against a 27 Ah nominal pack.
- The raw DataLink RPM field is `eRPM / 10`. For the 42-pole motor, mechanical
  RPM is therefore calculated with a `10 / 21` scale.
- Forward-flight fitting uses stable samples and does not claim validity outside
  the measured speed interval. Extrapolated results should be treated as design
  hypotheses requiring flight validation.
- Ground speed is used by the current log pipeline. Wind can therefore bias the
  inferred airspeed/power relationship.

## Model transfer

The optional transfer logic decomposes a fitted curve into physical terms such
as induced loss, profile drag, body drag area, and rotor drag. It then rebuilds
the curve for a new mass, rotor count, propeller diameter, and tip speed. An
identity transfer back to the calibration aircraft is covered by tests.

The three model families are nearly indistinguishable inside the calibration
speed range. Their separation outside that range is a model-structure effect,
not independent high-speed validation.

## Output interpretation

- The general `calculate` command is a Bauersfeld-based estimate. It does not
  automatically apply the DataLink-fitted forward-flight curves.
- `analyze-calibration` reconstructs the bundled empirical/fitted calibration;
  it does not claim that the resulting curve is valid for an arbitrary vehicle.
- Reported range assumes still-air speed and constant modeled power. Wind,
  manoeuvres, climb/descent, battery voltage sag, temperature, and reserve
  policy can materially change an actual flight.
