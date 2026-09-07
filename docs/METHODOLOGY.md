# Methodology and limitations

## Model and experiment scope

The general `calculate` command uses the simple optimum-speed and power-ratio
relationships from Bauersfeld and Scaramuzza. Inputs include electrical hover
power, battery energy, takeoff mass, rotor geometry and projected reference
area. The correction factor explicitly multiplies available energy. Use a
factor of 1 when the entered energy already represents usable energy.
The projected-area input is in square centimetres and is distinct from the
aerodynamic `CdA` used by the fitted forward-flight curves.

The calibration pipeline fits Zeng-type normalized power curves and Faessler-
and Kirschstein-inspired hybrids. Each fits two coefficients against speed
bins, with further inputs and estimates supplied by the profile, hover
reference, RPM statistics and attitude-derived drag prior. This is not a claim
that the entire pipeline has only two estimated quantities. The exact
paper-to-implementation mapping, DOIs and corrected Kirschstein disk-area term
are in [References](REFERENCES.md).

## Declared geometry and flight-specific mass

The current reproduction example defaults to a four-rotor **G29*9.5 CF,
29-inch configuration**, selected by the aircraft owner. It accepts
`--prop-diameter 29 --mass 12.4` explicitly. Here 12.4 kg is a declared scenario
input, not a measured mass recovered from telemetry. The reported 12.4, 12.8
and 13 kg values can describe different flights/configurations; no common
weighed mass is established for all dates. A mass estimate inferred from
hover remains conditional on the thrust calibration and operating conditions.

The reproduction helper updates the propeller/mass profile before fitting and
selects the corresponding KV190 G28 or G29 manufacturer table. In contrast,
the legacy `analyze-calibration` CLI still uses its fixed **28-inch, 12.4 kg**
July 3 preset. Its `--data-root` changes input location, not aircraft geometry.
A current run with `--prop-diameter 28` is a geometry comparison using current
code; it does not restore the old Kirschstein implementation.

## Telemetry, alignment and selection

ArduPilot BIN logs supply vehicle state and ground speed. DataLink UDAT records
supply the four ESC slots' voltage, current and RPM fields. Sessions are
matched by time overlap, samples are filtered for plausible values and valid
motor count, and aligned observations are reduced to stable speed bins.
The pipeline uses **ground speed**, so wind can bias its relationship to
aerodynamic power.

DataLink filename clocks are interpreted as Europe/Istanbul time (UTC+3) for
these inputs. However, the retained `_gps_week_ms_to_utc` helper assigns GPS
week/milliseconds to a UTC-labelled timestamp without subtracting the 18-second
GPS–UTC offset applicable to July 2026. Its coordinate is therefore 18 seconds
ahead of actual UTC. Session overlap does not prove correct clock alignment.
The current calibration preserves that legacy join convention for comparison;
correcting it requires a separately identified raw-data rejoin and regenerated
fit, not merely changing a timestamp label.

The published July 21 derived data preserve the historical joins. The applied
DataLink shift was `-56.18 s` in the legacy coordinate; shifting to true UTC
while preserving those joins would require `-74.18 s`. These offsets are
specific to that analysis. Public replay recalculates selections and residuals
from derived rows; it cannot independently verify the raw-log alignment.

The primary July 21 comparison selects the first ten uninterrupted laps and
applies the historical stability conditions plus absolute **scalar speed
acceleration** at most 1 m/s². A constant-speed turn can pass that acceleration
gate. The alternative first-ten-lap selection omits that extra gate; a
post-intervention selection is reported separately. Selection and alignment
were developed after examining the flight, so this is not a prospectively
blinded experiment.

## Electrical quantities, energy and RPM

The directly parsed electrical quantity is the sum of `voltage × current`
over four ESC slots. The archive calls it a single sensed battery branch and
uses a factor of two to obtain a vehicle equivalent. **Physical sensor wiring
has not been verified.** A 6S2P battery description alone does not establish
that the ESC sum should be doubled. Output fields retaining branch/vehicle
terminology represent this conditional historical scenario.

The energy basis of 25.2 Ah at `6 × 3.7 V` gives 559.44 Wh; the archive's
conditional doubled basis is 1118.88 Wh. This is adopted from prior analysis,
not a usable-capacity measurement performed by the calibration command.
Integrating power over the joined flight produces a different quantity and
does not measure full-discharge capacity. Scaling both power and energy by
the same factor leaves `E/P` and normalized `P/P_hover` unchanged; this algebra
does not verify either absolute scale. Endurance and range calculated from
these quantities must retain the scenario assumptions.

The original July 3 battery-monitor current/energy channels are flagged as
suspect and do not drive the electrical power fit. That finding does not
classify every later flight's battery monitor.

The implemented DataLink convention converts the raw RPM field with `10/21`
for a 42-pole motor. The official T-MOTOR page supports 21 pole pairs but does
not specify the telemetry factor of ten. Manufacturer thrust/RPM values are
a consistency check, not an independent protocol or absolute-accuracy test.
Tip speed is proportional to the declared propeller diameter. The reported
tip-speed statistic is the median of stable speed-bin medians, not a hover-only
RPM measurement, despite the legacy field name `hover_rpm_estimate`.

## Residuals and transfer

July 3 calibration-bin MAE is the unweighted mean of
`abs(predicted P/P_hover - observed P/P_hover)`. It is a dimensionless fit
residual, not a percentage or an independent validation score.
July 21 percent residual is `100 * (observed_ratio / predicted_ratio - 1)`;
reported mean absolute residuals weight the selected bins equally. These two
metrics cannot be compared as if they were the same error measure.

Both dates' power ratios use the **July 3 ESC-sum hover reference**, not an
independently measured July 21 hover denominator. A constant unknown
electrical multiplier cancels between dates only if that multiplier is the
same for both measurement sets. A change in sensor gain or wiring would
invalidate that assumption.

Replay evaluates the fitted July 3 coefficients on July 21 observations
without refitting them to July 21 or transferring them to a separately
established July 21 mass. This is a comparison with a fixed curve under
declared calibration inputs; it does not establish matched mass, wind,
sensor calibration or hardware across flights. The archive's
combined July 3/July 21 fit trains on both dates and therefore does not provide
held-out evidence for its July 21 training points.

Transfer routines rebuild assumed physical terms for a new mass, rotor count,
diameter and tip speed. Identity and mass-response tests check computational
properties; they do not establish predictive accuracy on a different aircraft.
Nearly coincident calibration curves also do not establish independent
physical validity. Outside the measured interval, predictions are
extrapolations. Wind, manoeuvres, climb/descent, voltage sag, temperature and
reserve policy can change actual range and endurance.
