# References and model attribution

The general calculator uses Bauersfeld's simple range/endurance estimates. The
calibration pipeline uses Zeng-type power curves with locally fitted coefficients
and Faessler- and Kirschstein-inspired adaptations. These paths do not reproduce
every model, controller or experiment in the cited papers. Their accuracy must
be assessed on the package's own data and assumptions.

Machine-readable citations are available in [references.bib](references.bib).

## Paper-to-implementation mapping

| Source | Contribution used here | Local adaptation and limits |
| --- | --- | --- |
| [Bauersfeld and Scaramuzza (2022)](#bauersfeld-and-scaramuzza-2022) | `BauersfeldRangeCalculator`: hover induced velocity, simple optimal-speed regressions and range/endurance power ratios; Eqs. 4, 17–18 and Table II. | Electrical hover power and usable-energy inputs come from the caller. The full blade-element/motor/battery simulator, wind regressions and capacity polynomial are not implemented. |
| [Zeng, Xu and Zhang (2019)](#zeng-xu-and-zhang-2019) | `zeng_profile_ratio` and `zeng_induced_ratio`: profile- and induced-power speed dependence from preprint Eq. 6, with a cubic parasite term. | `fit_weighted_zeng_ratio` fits normalized coefficients to local speed bins. The communications and trajectory optimization from the paper are outside this implementation. |
| [Faessler, Franchi and Scaramuzza (2018)](#faessler-franchi-and-scaramuzza-2018) | The linear rotor-drag dynamics motivate a linear drag term in `estimate_faessler_drag_from_attitude_log`. | The code infers drag from attitude under steady-flight assumptions, fits linear/quadratic force terms, and adds the resulting power terms to a Zeng curve in `fit_faessler_drag_constrained_zeng`. This scalar hybrid is not the paper's full dynamics or flatness controller. |
| [Kirschstein (2020), corrected 2022](#kirschstein-2020-and-corrigendum-2022) | `power_kirschstein_component`: level-flight adaptation of the component-power decomposition in Eq. 5. | Hover anchoring and locally fitted induced-relief/extra cubic terms make `fit_kirschstein_all_data` a hybrid surrogate. It does not implement the paper's complete parcel-delivery or energy-supply model. |

The July 3 speed bins are calibration data. Agreement with those bins measures
fit residuals, not independent validation. A later-flight comparison only tests
the coefficients and selection actually used in that comparison; it does not
inherit accuracy claims from these publications. See
[Methodology](METHODOLOGY.md) and [Reproducibility](REPRODUCIBILITY.md).

### Kirschstein profile-power correction

The original paper's Appendix A defines total rotor disk area as
`A_total = N * pi * r^2`. With density `rho`, tip speed `Utip`, solidity `sigma`
and blade-drag coefficient `delta`, the hover profile term is
`P_profile_hover = rho * A_total * Utip^3 * sigma * delta / 8`.
The [2022 corrigendum](https://doi.org/10.1016/j.trd.2022.103457) specifies the
forward-speed multiplier `1 + 3 * (v / Utip)^2`.

The current implementation uses this area term in `build_kirschstein_params`
and scales vehicle-transfer profile power with `N * r^2 * Utip^3`, holding
density, solidity and blade drag fixed. This corrects the `0.1.1rc1`
implementation's use of radius where disk area was required, including its
linear-radius transfer ratio. The multiplier 3 was already present. Numerical
results from before the area correction must be identified by their source
version; they are not interchangeable with regenerated results.

## Scholarly references

### Bauersfeld and Scaramuzza (2022)

Leonard Bauersfeld and Davide Scaramuzza. *Range, Endurance, and Optimal Speed
Estimates for Multicopters*. IEEE Robotics and Automation Letters, 7(2),
2953–2960, 2022. [DOI: 10.1109/LRA.2022.3145063](https://doi.org/10.1109/LRA.2022.3145063).
[Author-hosted paper](https://rpg.ifi.uzh.ch/docs/Arxiv21_Bauersfeld.pdf);
[arXiv:2109.04741](https://arxiv.org/abs/2109.04741).

### Zeng, Xu and Zhang (2019)

Yong Zeng, Jie Xu and Rui Zhang. *Energy Minimization for Wireless Communication
With Rotary-Wing UAV*. IEEE Transactions on Wireless Communications, 18(4),
2329–2345, 2019. [DOI: 10.1109/TWC.2019.2902559](https://doi.org/10.1109/TWC.2019.2902559).
[Author preprint, arXiv:1804.02238](https://arxiv.org/abs/1804.02238), first posted
in 2018; the journal publication year is 2019.

### Faessler, Franchi and Scaramuzza (2018)

Matthias Faessler, Antonio Franchi and Davide Scaramuzza. *Differential Flatness
of Quadrotor Dynamics Subject to Rotor Drag for Accurate Tracking of High-Speed
Trajectories*. IEEE Robotics and Automation Letters, 3(2), 620–626, 2018.
[DOI: 10.1109/LRA.2017.2776353](https://doi.org/10.1109/LRA.2017.2776353).
[Author preprint, arXiv:1712.02402](https://arxiv.org/abs/1712.02402).
The DOI contains 2017; the journal publication year is 2018.

### Kirschstein (2020) and corrigendum (2022)

Thomas Kirschstein. *Comparison of energy demands of drone-based and
ground-based parcel delivery services*. Transportation Research Part D:
Transport and Environment, 78, 102209, 2020.
[DOI: 10.1016/j.trd.2019.102209](https://doi.org/10.1016/j.trd.2019.102209).

Thomas Kirschstein. *Corrigendum to “Comparison of energy demands of drone-based
and ground-based parcel delivery services” [Transp. Res. Part D: Transp. Environ.
78 (2020) 102209]*. Transportation Research Part D: Transport and Environment,
111, 103457, 2022.
[DOI: 10.1016/j.trd.2022.103457](https://doi.org/10.1016/j.trd.2022.103457).

## Official technical references

- [T-MOTOR U8 Lite KV190 specifications and load tests](https://store.tmotor.com/product/u8-lite-u-efficiency-kv190.html).
  The relevant tables are **KV190, 6S (24 V), G28*9.2 CF and G29*9.5 CF**.
  `U8LITE_KV190_THRUST_RPM_TABLES` uses their per-motor thrust/mechanical-RPM
  pairs. Corresponding thrust/power arrays use electrical input power from
  the same bench configurations; the G29 power array omits the lowest row.
  The page lists 42 magnetic poles, implying 21 pole pairs, but does not specify
  the DataLink field's factor of 10. Bench values do not establish the flight's
  propeller, operating voltage, sensor topology or absolute RPM accuracy.
- [ArduPilot: Motor Thrust Scaling](https://ardupilot.org/copter/docs/motor-thrust-scaling.html).
  `MOT_THST_EXPO` controls thrust-curve shape; it is not an exponent converting
  throttle directly to mass. Converting actuator output to force requires a
  thrust curve for the applicable motor, propeller, ESC and battery conditions.
  Manufacturer bench throttle percentages are not automatically identical to
  ArduPilot normalized thrust demands.
- [ArduPilot: Setting Hover Throttle](https://ardupilot.org/copter/docs/ac_throttlemid.html).
  `MOT_THST_HOVER` is a learned hover level, not a measurement in kilograms.
  Weight inference requires a calibrated propulsion model and assumptions such
  as steady, level hover. A sensitivity plot that varies either parameter must
  state those assumptions.

Technical pages were checked on 7 September 2026. The package distributes
citations and implementation notes; the cited papers and manufacturer PDFs
are not bundled.
