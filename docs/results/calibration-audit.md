> Interpretation: legacy branch/vehicle labels below assume an unverified sensor layout. The directly parsed quantity is the four-ESC electrical sum. Geometry and mass are declared experiment inputs.

# Scientific Model Fit Audit

Fit mode: `measured_datalink_power_curve`
Date hint: `260703`
Joined samples accepted for fit: `46175`

Measured DataLink hover reference (one sensed branch): `757.9 W`
Power reference used: `757.9 W`
Mechanical-RPM Utip: `82.9 m/s`
RPM conversion: raw eRPM/10 multiplied by `10/21 = 0.476190476`.

## Empirical DataLink P(v)

Measured speed range: `2.4624748023768035` - `12.338323946638544` m/s
Stable samples in measured bins: `28095`
Raw samples in measured bins: `28096`
Source BIN logs: `00000076.BIN, 00000077.BIN`
Source DataLink sessions: `UART-260703-103606, UART-260703-141448`

| speed m/s | P/Ph | n | raw n | stable fraction | dt max s | source bins |
|---:|---:|---:|---:|---:|---:|---|
| 2.46 | 1.0161 | 1303 | 1304 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 3.51 | 1.0267 | 1107 | 1107 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 4.53 | 1.0080 | 911 | 911 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 5.59 | 0.9666 | 1760 | 1760 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 6.42 | 1.0036 | 1711 | 1711 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 7.90 | 0.9551 | 4935 | 4935 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 8.08 | 0.9523 | 2020 | 2020 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 9.54 | 1.0839 | 1154 | 1154 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 10.90 | 0.9919 | 8556 | 8556 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 11.09 | 1.0236 | 4552 | 4552 | 1.00 | 0.050 | 00000076.BIN, 00000077.BIN |
| 12.34 | 1.0491 | 86 | 86 | 1.00 | 0.050 | 00000076.BIN |

## Diagnostic Surrogate Fits

These are low-dimensional diagnostic fits against measured DataLink bins; they are not independent physical validation curves.

| model | status | MAE | reasons | warnings |
|---|---|---:|---|---|
| zeng_measured_fit | accepted | 0.02776 |  |  |
| faessler_measured_fit | accepted | 0.02778 |  |  |
| kirschstein_measured_fit | accepted | 0.02769 |  |  |

### Key fitted and derived parameters

| model | parameters |
|---|---|
| zeng_measured_fit | v0_ms=5.39704; utip_ms=82.9126; f0=0.802551; induced_fraction=0.197449; k_par=5.31637e-05 |
| faessler_measured_fit | v0_ms=5.39704; utip_ms=82.9126; f0=0.760324; induced_fraction=0.239676; body_cda_fit_m2=0.154656; body_cd_fit=3.4368; lambda_n_per_ms=1.32527; lambda_source=attitude_log; k_body=0.000124987; k_rotor=0.00174863; drag_scale=0.251749 |
| kirschstein_measured_fit | v0_ms=5.39704; utip_ms=82.9126; body_cda_fit_m2=0.154656; body_cd_fit=3.4368; induced_relief_scale=0.165545; extra_cubic_k=-6.01683e-05; p_profile_hover_w=89.2633; lift_power_per_newton=5.49659 |
