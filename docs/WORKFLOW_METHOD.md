# From an initial estimate to a flight-informed model

The project has two complementary uses. Before flight, the Bauersfeld-based
calculator estimates useful cruise speeds, endurance and range from an aircraft
description and an electrical hover-power estimate. After a representative
flight, the fitting workflow uses that aircraft's measured power and motion to
build speed-dependent curves. These curves support comparisons for later flights
of the same configuration; fitting a curve does not guarantee that every future
mission will follow it.

The Python examples and input schema are in [Usage](USAGE.md). This page explains
what the inputs and predictions mean. The supplied July 3/July 21 experiment has
additional historical assumptions documented in [Methodology](METHODOLOGY.md);
those assumptions are not defaults to adopt for another aircraft.

## The two outputs after fitting

The first figure, `power_ratio.png`, compares **normalized electrical power**,
`P(v) / P_hover`, against horizontal speed in metres per second. A ratio of 1.2
means that the model predicts 20% more power than the supplied hover reference. This is not a
thrust-to-weight ratio, and the horizontal axis is not normalized speed.

The second figure, `range_endurance.png`, converts the same power curves into
**range and endurance against speed**. For a steady speed `v`, power `P` in watts
and energy `E` in watt-hours after the chosen reserve (`usable_energy_wh`):

```text
P(v) = P_hover × power_ratio(v)
endurance_minutes(v) = 60 × E / P(v)
range_km(v) = 3.6 × v × E / P(v)
```

These are steady operating-point estimates. Range is distance flown at that
speed, not an outbound mission radius. Climb, descent, acceleration, loiter,
return legs and changing winds require their own energy allowance or a mission
calculation. An optimum read from a curve is the best point in the evaluated
speed interval, not proof that the aircraft can safely fly at that speed.

## Record a useful calibration flight

Use the configuration you intend to model: takeoff mass, propellers, rotor
count, payload and battery arrangement should be recorded independently.
Include a stable hover segment and sustained, approximately level flight at
several speeds. A log consisting mainly of hover or rapid manoeuvres cannot
identify the forward-flight curve reliably. Keep another flight for checking
the resulting predictions before making performance claims.

The inputs must describe power and motion on a consistent time base. In an
ArduPilot BIN file, the EKF horizontal velocity components supply **ground
speed**, `sqrt(VN² + VE²)`. Ground speed is an imperfect substitute for airspeed:
a headwind and a tailwind can produce different aerodynamic power at the same
ground speed. Prefer calm conditions for a first calibration and record the
conditions used. The fitted curve does not contain a wind estimator.

`load_ardupilot_log` joins the selected electrical messages to `XKF1` samples
using timestamps within one BIN file. It does not reuse the included
experiment's date filters, filename time zones or session offsets. The default
maximum nearest-message separation is 0.35 seconds; an explicit electrical
timestamp shift is available when an independently established offset requires
one. CSV input must already be synchronized. Use one flight per fit rather than
concatenating timestamps that restart at each flight.

Choose an electrical measurement that represents the stated power boundary:

- A calibrated battery monitor can provide whole-aircraft electrical power as
  voltage times current. Select the intended monitor instance and verify its
  scale against a trusted measurement; a plausible-looking channel is not a
  calibration certificate.
- A sum over ESC voltage/current channels represents the power recorded by
  those ESCs. It requires all intended motors and consistent samples. It may
  omit avionics and other loads. Use a hover reference with the same measurement
  boundary, and account for omitted loads before interpreting absolute flight
  time as a whole-aircraft estimate.

Do not infer a power multiplier from the number of parallel battery packs.
Scaling both energy and power by the same number preserves their ratio but does
not establish that either absolute measurement is correct. The supplied example
data come from one aircraft and retain their own documented electrical
uncertainty. Refit using your own logs for another aircraft.

## What the fit estimates

The workflow reduces eligible, approximately steady measurements to speed-bin
medians. A bin's median electrical power is divided by the same hover reference
used to interpret the predictions. Binning limits the effect of individual
spikes and provides a compact curve comparison; it does not make adjacent log
samples statistically independent. Sample counts describe support for each bin,
not the number of independent flights.

`FitOptions` makes the selection explicit. Defaults use 1 m/s bins from 2 to
25 m/s, at least 80 stable samples per bin, at least three eligible bins and a
stable fraction of at least 0.5 within each bin. Stability requires horizontal
**vector** acceleration at most 0.8 m/s², absolute vertical speed at most 1 m/s
and total tilt at most 25 degrees. Differences are not evaluated across gaps
longer than one second; samples without suitable neighbours are excluded.
These are adjustable selection rules, not universal aircraft operating limits.

All three fitted models use literature-derived speed dependences, with a small
number of coefficients fitted to the selected power bins:

- **Zeng-inspired:** combines profile, induced and cubic parasite-power terms.
- **Faessler-inspired:** adds an attitude-derived drag-shape estimate to the
  normalized rotor-power model.
- **Kirschstein-inspired:** combines a component-power baseline with fitted
  induced-relief and cubic correction terms.

These are the repository's fitted adaptations, not full reproductions of every
model in the papers. The equation mapping and citations are in
[References](REFERENCES.md). In particular, the Kirschstein rotor term uses total
disc area, `N × pi × r²`; its electrical baseline is anchored to the declared
hover power. Its fitted terms do not independently measure propulsion
efficiency or prove that a mechanical component equals a measured electrical
component.

The Faessler-inspired prior interprets tilt in suitable, near-steady,
approximately level flight samples as a drag estimate:

```text
tilt = acos(cos(pitch) × cos(roll))
estimated_horizontal_drag = mass × g × tan(tilt)
drag(v) ≈ 0.5 × density × CdA × v² + lambda × v
```

This approximation becomes unreliable during acceleration, turns or vertical
motion, and when ground speed differs materially from airspeed. Its coefficients
describe a fitted drag shape under the selected conditions; they are not a direct
wind-tunnel measurement of body drag or rotor drag. When an attitude prior is
unavailable, the own-flight workflow stops and reports insufficient data; it
does not borrow an attitude prior from the bundled aircraft. By default the
prior requires at least 20 stable samples between 3 and 7.2 m/s and sufficient
speed variation to separate the quadratic and linear drag terms. These
thresholds are also available in `FitOptions`.

Rotor tip speed is `pi × propeller_diameter × mechanical_RPM / 60`. Electrical
RPM, vendor-scaled RPM and mechanical RPM are not interchangeable. A declared
fallback RPM remains an input assumption, not a value recovered from the flight.
Changing the propeller or RPM convention can alter the fitted curve even when
the raw electrical measurements are unchanged.

`FlightFit.save` records the fitted coefficients, selected bin observations,
aircraft profile, selection settings and source metadata in a JSON file.
`FlightFit.load` restores those coefficients without running another fit.
`predict` takes a requested speed, electrical hover-power reference and usable
energy **after reserve**; it applies no extra reserve multiplier. Its output
includes a flag indicating whether the requested speed lies between the lowest
and highest fitted bin medians. Supplying a new power or energy value does not
update the fitted mass, geometry or drag coefficients.

Inspect `metadata["parameter_warnings"]` on a custom fit. A low residual can
coexist with coefficients that lack a useful physical interpretation. The
prediction interface rejects nonpositive or nonfinite power at the requested
speed; passing that check establishes a calculable value, not measured accuracy.

## Using a fit for later flights

Keep the fitted coefficients fixed when checking another flight. Evaluate its
measured power against the saved curve using a stated hover-reference policy;
refitting to the check flight turns it into calibration data. Compare the full
selected speed interval and the residuals, including difficult bins. A small
error at one operating point does not establish the same accuracy everywhere.

Predictions beyond the fitted speed interval are extrapolations. A smooth curve
or agreement between models is not an independent accuracy guarantee. Changes
in mass, payload geometry, propellers, battery condition, density, temperature,
wind or sensor calibration can change the relationship. Refit or verify the
curve when these change, and supply a measured usable-energy estimate and a
reserve policy when converting power into endurance and range.

The intended workflow is simple: make an initial estimate, fly a representative
calibration flight, fit the curves, and check them on another flight. Each stage
adds evidence about a particular aircraft and operating envelope.
