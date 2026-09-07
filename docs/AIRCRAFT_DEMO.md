# Interactive aircraft example

Download [`aircraft-demo.html`](https://raw.githubusercontent.com/tzi4/Multicopter_Battery_and_Range_Calculations/main/docs/aircraft-demo.html), save it as an HTML file, and open it in a browser. It contains its own plotting library, styles and fonts, so it works offline without Python or a server. It does not upload inputs or read flight logs.

This is an English adaptation of the author's existing July 28 aircraft dashboard. It keeps the original controls and two Zeng-based plots: power relative to hover, and range/endurance versus speed. Use the [Python workflow](USAGE.md) to fit your own logs and compare all three models.

## Configuration shared with the Python examples

| Input | Value |
| --- | --- |
| Source fit | July 3 flight data, 12.4 kg, four rotors, G29 |
| Selected motor / propeller | U8 Lite KV190 / G29×9.5 |
| Reference area | 450 cm² |
| Battery | Two parallel 6S, 27 Ah packs; 3.7 V per cell |
| Nominal energy | 1,198.8 Wh |
| Usable energy before reserve | 1,118.88 Wh, using the original 25.2/27 usable-capacity ratio |
| Flight energy after 10% reserve | 1,006.992 Wh |
| Conditional whole-aircraft hover basis | 1,485.6942539603501 W |

The hover basis retains the author's historical scaling: the four-ESC power sum of 757.891 W is multiplied by two, divided by the original G28 motor-table hover power of 1,123.9685039370079 W, and applied to the entered motor table. Parallel battery count alone does not establish that electrical multiplier. Treat the resulting watts and minutes as the original calibrated scenario until the electrical scale is independently checked.

The author's approximately 0.616 empirical correction used with Bauersfeld belongs to the separate preflight calculation. It is not applied to these fitted power curves or their usable-energy budget.

## Changes from the original HTML

The original dashboard embedded a G28 source fit and transferred it to the selected G29 aircraft. This public version embeds the current Python G29 coefficients and anchors the RPM-table scaling to that G29 source. At the default geometry, its power-ratio curve therefore matches the current Python Zeng fit directly.

The default entered mass and pack capacity have changed from the older HTML's 10.93 kg and 26 Ah to the later documented 12.4 kg and 27 Ah. The optional LiHV energy basis now matches Python’s empirical `3.7 × 7/6` factor rather than the old HTML’s 4.35 V value. The English reserve label now states the 10% actually used by the calculation; the old label said 7%. Unused Faessler and Kirschstein JavaScript helpers were removed. The original local HTML is unchanged.

With both pages set to 12.4 kg, G29 and 27 Ah per pack, the original HTML gives a modeled maximum range of 33.43 km at 18.76 m/s. The updated page gives 34.37 km at 19.42 m/s. This difference follows from the deliberate G28-to-G29 source-fit change, not from a JavaScript/Python discrepancy. Both optimum speeds lie beyond the fitted speed-bin range and are extrapolated model outputs, not measured maximum-range flights.

## Interpretation and checks

The shaded power-plot interval spans the source flight's fitted speed-bin medians, approximately 2.46–12.34 m/s. Red points always represent that source aircraft, including after changing the controls. Fit your own logs before applying the model to your aircraft.

Changing geometry uses the same physical coefficient transfer as `transfer_zeng_params_to_vehicle` in Python. The reference-area slider retains the original dashboard's additional CdA adjustment: `(entered_area_cm2 - 450) / 10000`, equivalent to an incremental drag coefficient of one. This interactive adjustment is separate from a fresh log fit. The other motor presets retain their original approximate RPM lookup; motor tables clamp thrust requests outside their tabulated ranges.

Browser calculations were compared against the current Python implementation for ten mass, propeller, area and cell-voltage configurations, with 2,491 speeds per configuration. Across 74,730 power-ratio, range and endurance values, the maximum absolute difference was below `5e-14` in the corresponding units. The standalone file was also checked with network access blocked: both graphs rendered without JavaScript errors or external requests. Desktop and 390-pixel mobile layouts were checked.

The embedded dependencies are Plotly.js 2.27.0, styles compiled with Tailwind CSS 3.4.17, and Font Awesome Free 6.4.0. Their license notices are included inside the HTML. No dependency download is needed to run it.

The numerical comparison is also retained in `tests/test_browser_demo.py`. It executes the actual embedded application code with Node.js, refits the public logs in Python, and checks the full speed grid, including the LiHV energy option. Run `python -m pytest -q tests/test_browser_demo.py`; it skips when Node.js is unavailable.
