# Flight configuration and hover evidence

The owner selected **G29×9.5** for the new showcase. The nominal **12.4 kg** is an assumption; the owner recalls other flights at **12.8 or 13 kg**. The available hover logs support a configuration sensitivity analysis, but do not reliably identify which of these masses belonged to each flight. Neither the propeller choice nor a mass was selected by minimizing prediction error.

The calculations below use the [T-Motor U8 Lite KV190, 24 V tables](https://store.tmotor.com/product/u8-lite-u-efficiency-kv190.html), the original flight logs, and the logged firmware revision. [The aggregate evidence](results/flight-hover-summary.json) includes input hashes, source-code hashes, quartiles, exclusions and alternative assumptions. These are local raw-log audit results; reproducing the package's public derived-data replay does not independently reproduce this raw-log extraction.

## What the hover values mean

All five logs report `ArduCopter V4.6.3 (3fc7011a)`. At that [exact revision](https://github.com/ArduPilot/ardupilot/blob/3fc7011a/ArduCopter/Log.cpp), `CTUN.ThO` records `motors->get_throttle()`: filtered, normalized thrust demand before motor mixing and thrust linearization. Despite the log label “throttle output,” it is not the PWM percentage sent to the ESC. `CTUN.ThH` records the adaptive hover estimate. `MOT_THST_HOVER` parameter records capture saved values, which can start with an estimate learned on an earlier flight. The [learning implementation](https://github.com/ArduPilot/ardupilot/blob/3fc7011a/libraries/AP_Motors/AP_MotorsMulticopter.cpp) adjusts this estimate toward the current normalized demand when the learning conditions are met.

Each flight was filtered using its own `TimeUS`, without any GPS-clock join: XKF1 core 0; horizontal speed ≤1 m/s; |vertical speed| ≤0.3 m/s; |roll| and |pitch| ≤8°; centered horizontal vector acceleration ≤0.5 m/s² over a stencil no longer than 0.5 s; height ≥2 m above the arm-start reference; and `ThO` ≥0.05. CTUN, XKF1, BAT, MOTB and RCOU records were matched within 0.15 s. Coverage sums adjacent accepted samples separated by at most 0.25 s. These gates were fixed before mass hypotheses were calculated.

Log 77 has a disarm record but no preceding arm record. Its interval before that disarm is explicitly inferred, with the first XKF1 altitude as the ground reference and the same physical gates. Other logs use recorded arm windows. These are hover candidates: ground speed does not establish still air, and the gates do not measure rotor thrust.

| Flight | Accepted rows / coverage | Saved `MOT_THST_HOVER`, chronological | Steady `ThO` median [Q1–Q3] | Steady `ThH` median | BAT voltage median |
|---|---:|---|---|---:|---:|
| July 3, 76 | 1,812 / 181 s | 0.587 → 0.275 → 0.281 | 0.298 [0.285–0.306] | 0.298 | 21.33 V |
| July 3, 77 | 1,184 / 120 s | 0.281 → 0.326 | 0.317 [0.311–0.323] | 0.305 | 20.54 V |
| July 21, 85 | 1,496 / 149 s | 0.309 → 0.295 → 0.304 | 0.304 [0.297–0.311] | 0.300 | 21.21 V |
| July 24, 90 | 796 / 79 s | 0.461 → 0.412 → 0.277 | 0.414 [0.396–0.422] | 0.422 | 23.47 V |
| July 24, 91 | 2,788 / 283 s | 0.277 → 0.259 → 0.265 → 0.272 → 0.285 | 0.273 [0.264–0.283] | 0.272 | 22.92 V |

## Check against the actual motor outputs

The [firmware thrust conversion](https://github.com/ArduPilot/ardupilot/blob/3fc7011a/libraries/AP_Motors/AP_Motors_Thrust_Linearization.cpp) uses expo, the spin limits and a filtered voltage ratio. Its [mixer](https://github.com/ArduPilot/ardupilot/blob/3fc7011a/libraries/AP_Motors/AP_MotorsMatrix.cpp) also applies voltage and density compensation. Under a symmetric hover approximation with density ratio 1, the voltage `LiftMax` factors cancel, giving this useful check:

```text
x = (-(1-e) + sqrt((1-e)^2 + 4*e*h)) / (2*e)
u = clamp(x / MOTB.BatVolt, 0, 1)
PWM = PWMmin + (PWMmax-PWMmin) * (spin_min + (spin_max-spin_min)*u)
```

Here `h` is `CTUN.ThO`, `e=0.4`, the PWM endpoints are 1100/1940 µs, and the spin limits are 0.16/0.95. This scalar check approximates the average motor output; individual motors also receive attitude and yaw commands. The median reconstructed PWM minus the actual four-channel mean was **+1.48, +0.88, −0.85, −1.39 and −2.34 µs** for logs 76, 77, 85, 90 and 91, respectively. Their actual mean-PWM medians were **1631.75, 1653.25, 1640.25, 1589.25 and 1607.00 µs**. This close agreement checks the controller normalization, not the thrust-to-mass conversion.

Logs 76, 77, 85 and 91 configured voltage limits of 33/50.4 V while measuring roughly 20–24 V. The firmware clamps its voltage input to the configured minimum: their recorded `MOTB.BatVolt` is approximately **0.654765**, and `LiftMax` approximately **0.564346**. These configured limits are not evidence of a physical 12S battery.

Log 90 provides a direct warning against interpreting hover demand as mass. Its voltage limits changed from 19.2/25.2 V to 33/50.4 V. Comparing its first and last arm windows, median `ThO` fell **0.4168 → 0.2643**, while actual mean PWM changed only **1588.0 → 1596.9 µs** and battery voltage **23.49 → 23.28 V**. The parameter change explains why the normalized hover number can change greatly without a corresponding change in motor output. A different mass cannot be established from those hover numbers alone.

## Testing the inverse-expo idea

The manufacturer supplies 20 throttle/thrust points for each of G28×9.2 and G29×9.5 at 24 V. Fitting `T_normalized=(1-e)u+e*u²` by least squares gives:

| Hypothetical mapping of the bench throttle column | G28 fitted expo | G29 fitted expo |
|---|---:|---:|
| 1000–2000 µs endpoints | 0.5636 | 0.5431 |
| 1100–1940 µs endpoints | 0.2972 | 0.2721 |

The source does not establish the bench's actual PWM endpoints or zero-thrust deadband. Endpoint sensitivity therefore matters: with the maximum fixed at 2000 µs, assumed minimum endpoints of **1079.9 µs for G28** or **1070.5 µs for G29** each produce a fitted expo of 0.4. Only supplied points were fitted; no low-throttle measurements were invented. The 1940 µs normalization uses interpolation within the table. This experiment shows that configured expo 0.4 does not discriminate the two propellers under the available normalization information. The showcase uses G29 because the owner selected it.

## Conditional mass estimates from RPM and PWM

For RPM, the calculation sums the four motors' individually interpolated G29 static thrusts. It does not apply a voltage-squared correction: the independent variable is already measured RPM. All four RPM values must fall within the actual table range, **1616–3125 RPM**; excluded rows are not extrapolated. The historical mechanical conversion `raw × 10/21` is retained. Bench atmosphere, propeller condition, inflow, RPM-scale accuracy and tilt are not independently calibrated, so the output is **bench-equivalent thrust expressed in kg**, not weighed aircraft mass.

The July 3 table below preserves the historical relative join, whose GPS-derived time labels are 18 seconds ahead of UTC. Repeating with unshifted GPS UTC changes the medians to 14.149 and 13.699 kg, and excludes 668/1798 and 436/1184 matched rows. Thus this clock alternative does not resolve the mass discrepancy. July 21 uses its archived relative offset, equivalently DataLink filename time minus 74.18 s against UTC; this is an inherited alignment, not newly verified clock calibration.

| Flight | Matched hover rows | Rows excluded outside bench RPM range | Median of four RPM, then median over rows | G29 bench-equivalent kg, median [Q1–Q3] |
|---|---:|---:|---:|---:|
| July 3, 76 | 1,812 | 286 | 2116.5 | 14.110 [13.848–14.322] |
| July 3, 77 | 1,184 | 285 | 2113.3 | 13.671 [13.509–13.827] |
| July 21, 85 | 1,494 | 0 | 2181.7 | 14.100 [13.814–14.370] |

The individual motor RPM values differ substantially, especially on July 3; applying the thrust table to a single four-motor median would discard that information. July 21 RPM comes from its separate DataLink session, not its BIN. No matching RPM source was identified for July 24 logs 90/91.

A second calculation applies the manufacturer's throttle/thrust table to the actual four RCOU outputs. It assumes either 1000/2000 µs bench endpoints or the configured 1100/1940 µs endpoints, and then applies the explicitly approximate voltage law `thrust ∝ V²` relative to the 24 V bench. That law and the bench PWM mapping are unverified. The resulting medians are:

| Flight | Assumed 1000/2000 bench endpoints | Assumed 1100/1940 bench endpoints |
|---|---:|---:|
| July 3, 76 | 12.146 kg | 12.198 kg |
| July 3, 77 | 11.587 kg | 11.721 kg |
| July 21, 85 | 12.238 kg | 12.327 kg |
| July 24, 90 | 13.104 kg | 12.874 kg |
| July 24, 91 | 12.844 kg | 12.744 kg |

The JSON also reports the substantially higher results obtained by applying the 24 V table without voltage scaling, the results using learned `ThH` instead of measured PWM, and the rows outside the supplied throttle range. The disagreement between the RPM and PWM methods exceeds the 0.4–0.6 kg distinction being investigated. Quartiles describe correlated flight-sample dispersion, not a confidence interval for mass. These estimates therefore cannot justify assigning 12.4, 12.8 or 13 kg to individual flights.

At equal rotor loading, the G29 table predicts **2046.6, 2074.9 and 2093.7 RPM** for those three masses. The full 12.4-to-13 kg distinction is only about **47 RPM, or 2.3%**. The current uncertainty in the physical conversion is greater than that resolution.

## Model sensitivity without choosing mass by error

[The mass sensitivity result](results/g29-mass-sensitivity.json) holds the July 3 observations and hover-power normalization fixed, recomputes geometry and mass-dependent physics for G29, and refits only July 3 at each assumed common mass. It uses the corrected Kirschstein disc-area term. All nine historical July 21 validation bins remain fixed:

| Assumed common mass | Zeng mean absolute residual | Faessler mean absolute residual | Kirschstein mean absolute residual |
|---|---:|---:|---:|
| 12.4 kg | 11.7583% | 11.6991% | 12.0078% |
| 12.8 kg | 11.8019% | 11.6909% | 12.0427% |
| 13.0 kg | 11.8233% | 11.6870% | 12.0598% |

These are residuals `100*(observation/prediction−1)`, averaged after taking absolute values; they are not a new blinded validation. Small changes in these errors do not identify flight mass. A common assumed mass for calibration and validation is also not a correction for different masses on different flights: normalized `P(v)/P_hover` removes an overall power scale, while induced velocity, drag relative to hover power and rotor operating point still depend on mass. Flight-specific transfer needs independently supported mass/configuration inputs and a stated hover-reference policy. The nominal 12.4 kg showcase and the 12.8/13 kg sensitivity cases remain explicit assumptions.
