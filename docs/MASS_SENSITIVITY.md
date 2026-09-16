# Different masses on the two flight dates

The aircraft owner recalls masses between **12.4 and 13.0 kg**. This experiment
allows the July 3 calibration mass and July 21 comparison mass to differ,
using G29×9.5 propellers and four U8 Lite KV190 motors throughout.
The existing README comparison remains the declared 12.4 kg scenario.

Changing a common mass in both dates' metadata is a different experiment from
transferring a July 3 fit to a heavier or lighter July 21 aircraft. The earlier
[common-mass study](FLIGHT_CONFIGURATION.md#model-sensitivity-without-choosing-mass-by-error)
refitted at 12.4, 12.8 and 13 kg; all three models still had approximately
11.7–12.1% mean absolute residual over the same nine comparison bins.

## Fixed observations and exploratory mass selection

The source and target masses each span 12.4–13.0 kg in 0.1 kg increments,
giving **49 combinations**. July 3 supplies the fitted coefficients. The July 21
phase, clock pairing, electrical measurements, nine retained bins and residual
definition remain fixed. Rotor count, propeller diameter and air density also
remain fixed. No speed groups are removed to improve the result.

For every source-mass assumption, the July 3 fit is rebuilt with the
corresponding induced velocity and mass-dependent priors. The existing transfer
functions then rebuild the power curve at each target mass. Tip speed is
anchored to the source measurement and changed by the ratio of the G29 bench
RPMs at the two per-rotor thrusts.

The [manufacturer's 24 V bench table](https://store.tmotor.com/product/u8-lite-u-efficiency-kv190.html)
gives approximately 1101.66 W at 12.4 kg total thrust and 1187.44 W at 13 kg
total thrust for four motors, a 7.8% difference. These are static bench values;
they are not independently calibrated electrical measurements of these flights.

All predictions must use the same power reference as the measured comparison:
July 3's ESC-sum hover reference. A target-normalized `P/Ph` curve therefore
needs the target/source hover-power ratio before it can be compared with those
observations. The study records the assumed hover scaling explicitly, including
the historical electrical scaling convention and the effect of the transfer
algorithm when source and target masses are identical.

Selecting the lowest-error combination uses the July 21 comparison data to
choose parameters. It is an **exploratory fit to this comparison**, not a
measurement of either flight's mass or independent validation of the selected
configuration. A minimum on this 0.1 kg grid is not a proof of a continuous
optimum. All combinations and retained bins are reported together.

## Results on the unchanged nine bins

| Model | Nominal untransferred 12.4 kg comparison | Best model-hover transfer | Source → target mass |
|---|---:|---:|---|
| Zeng | 11.7583% | 10.9556% | 12.4 → 13.0 kg |
| Faessler-inspired | 11.6991% | 10.8036% | 12.4 → 13.0 kg |
| Kirschstein-inspired | 12.0078% | 11.2707% | 12.4 → 13.0 kg |

The means give each of the nine bins equal weight and use
`100 × (observation / prediction − 1)`, followed by an absolute value. The
mass range improves the fit to these observations modestly; it does not
recover sub-percent accuracy across the nine groups. The README's original
plots and nominal comparison remain unchanged.

The lower mean comes with a tradeoff: the maximum absolute bin residual grows
to **28.8698% / 28.6336% / 28.1598%** for Zeng / Faessler / Kirschstein at
these selected masses. The mass adjustment does not improve every speed bin.

Two explicit hover-power assumptions are evaluated for every combination:

1. **Model hover power:** use each transfer function's rebuilt absolute hover
   power divided by the source hover power, multiplied by the transferred
   normalized curve. This preserves the model's own component-power prediction.
2. **Bench hover anchor:** use the manufacturer target/source hover-power ratio
   in place of that model ratio. This assumes the static bench relationship
   transfers to the flight conditions and the electrical gain is unchanged.

With the bench anchor, the lowest means are **10.9566%, 10.8055% and 11.3153%**.
Zeng and Faessler again select 12.4 → 13.0 kg; Kirschstein selects
12.4 → 12.9 kg. Neither hover interpretation removes the discrepancy.

The transfer API retains its historical factor-of-two electrical convention.
That is an explicit assumption, not evidence of the actual sensor wiring.
Zeng and Faessler recover their original curves under same-mass transfer to
within `1e-9`. Kirschstein includes a refit when rebasing the electrical
reference; at 12.4 kg its maximum same-mass difference over 0–25 m/s is
`0.00102585` in `P/Ph`. A separately reported diagnostic divides out the
same-mass transfer response before applying the mass change. Its best
Kirschstein mean is **11.2818%** with model hover and **11.3262%** with bench
hover. This isolates the mass effect from that small reconstruction difference.

The [full result JSON](results/mass-transfer-sensitivity.json) records all
49 pairs under both assumptions, every retained bin, same-mass checks, source
parameters, and input/code provenance. Coefficients are frozen during each
target-mass evaluation; only the source-mass calibration uses July 3 data.

## Reproduce

After installation, from the repository root:

```bash
python examples/analyze_mass_sensitivity.py \
  --data-root data/calibration/2026-07-03 \
  --validation-root data/validation/2026-07-21 \
  --output-dir mass-sensitivity-output \
  --check-summary docs/results/mass-transfer-sensitivity.json
```

The script parses July 3 once, performs seven source-mass fits, evaluates the
49 pairs and compares the saved result with exact source/input provenance and
`1e-9` numeric tolerance. The code also checks that observations and source
coefficients remain unchanged during target evaluation. The hover/RPM audit
in [Flight configuration](FLIGHT_CONFIGURATION.md) explains why these scenarios
cannot establish the individual flights' actual masses.
