#!/usr/bin/env python3
"""
20 m/s range/power research helper.

This script intentionally does not modify menzil1.py.  It reproduces the
current 12.4 kg case, checks the 6 m/s stadium voltage data against the
SOC anchors, and compares several possible continuations for P(v) / P_hover.
"""

from __future__ import annotations

from dataclasses import dataclass

import menzil1 as base


RHO = 1.225


@dataclass(frozen=True)
class Scenario:
    mass_kg: float = 12.4
    motor_count: int = 4
    prop_diameter_in: float = 28.0
    drag_area_cm2: float = 450.0
    total_cells: int = 12
    capacity_mah: float = 27000.0
    battery_type: str = "lipo"


def standard_cf() -> float:
    ref_mass_g = 19500.0
    ref_thrust_per_motor = ref_mass_g / 4.0
    ref_energy_wh = base.calculate_real_energy_wh(24, 17000, "lihv")
    ref_motor_power = base.get_power_from_thrust(ref_thrust_per_motor, base.p80_thrust_power)
    ref_total_power = ref_motor_power * 4.0
    ref_theory_min = ref_energy_wh / ref_total_power * 60.0
    return 35.0 / ref_theory_min


def current_case(s: Scenario):
    thrust_per_motor_g = s.mass_kg * 1000.0 / s.motor_count
    motor_power_w = base.get_power_from_thrust(thrust_per_motor_g, base.u8lite_kv190_data)
    hover_power_w = motor_power_w * s.motor_count
    energy_wh = base.calculate_real_energy_wh(s.total_cells, s.capacity_mah, s.battery_type)
    cf = standard_cf()

    bau = base.BauersfeldMenzilHesaplayici(
        hover_power_w=hover_power_w,
        correction_factor=cf,
        battery_wh=energy_wh,
        total_mass_kg=s.mass_kg,
        drag_area_cm2=s.drag_area_cm2,
        prop_diameter_inch=s.prop_diameter_in,
        num_rotors=s.motor_count,
    ).solve()

    return thrust_per_motor_g, motor_power_w, hover_power_w, energy_wh, cf, bau


def menzil1_quadratic_coeffs(v_endurance: float, v_range: float):
    return base.calculate_poly_coeffs(v_endurance, v_range)


def menzil1_quadratic(v: float, a: float, b: float) -> float:
    return 1.0 + a * v * v + b * v


def range_tangent_cubic_tail(
    v: float,
    v_range: float,
    p_range_ratio: float,
    hover_power_w: float,
    drag_area_cm2: float,
    cd_effective: float,
) -> float:
    """Power ratio for v >= v_range.

    The first term is the lower bound imposed by the max-range condition:
    P(v) / v cannot be lower than P_range / v_range.

    The second term is the extra curvature from parasite drag after removing
    the tangent at v_range, so value and slope stay continuous there.
    """

    area_m2 = drag_area_cm2 / 10000.0
    k = 0.5 * RHO * cd_effective * area_m2 / hover_power_w
    dv = v - v_range
    cubic_excess = k * dv * dv * (v + 2.0 * v_range)
    return p_range_ratio * (v / v_range) + cubic_excess


def hermite_mid(v: float, v_endurance: float, v_range: float) -> float:
    """Conservative in-band curve that respects endurance/range optima.

    0..ve: simple U-shape with a minimum at ve.
    ve..vr: cubic Hermite with f'(ve)=0 and f'(vr)=f(vr)/vr.
    """

    p_end = 0.914
    p_range = 1.092

    if v <= v_endurance:
        x = (v - v_endurance) / v_endurance
        return p_end + (1.0 - p_end) * x * x

    t = (v - v_endurance) / (v_range - v_endurance)
    h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
    h10 = t**3 - 2.0 * t**2 + t
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2
    m0 = 0.0
    m1 = p_range / v_range
    length = v_range - v_endurance
    return h00 * p_end + h10 * length * m0 + h01 * p_range + h11 * length * m1


def piecewise_recommended(
    v: float,
    v_endurance: float,
    v_range: float,
    hover_power_w: float,
    drag_area_cm2: float,
    cd_effective: float = 1.0,
) -> float:
    if v <= v_range:
        return hermite_mid(v, v_endurance, v_range)
    return range_tangent_cubic_tail(
        v=v,
        v_range=v_range,
        p_range_ratio=1.092,
        hover_power_w=hover_power_w,
        drag_area_cm2=drag_area_cm2,
        cd_effective=cd_effective,
    )


def cubic_through_anchors(v: float, v_endurance: float, v_range: float) -> float:
    """Minimal cubic-tail shape: f(v)=1+b*v+c*v^3 through trusted anchors."""

    d_pe = 0.914 - 1.0
    d_pr = 1.092 - 1.0
    det = v_endurance * v_range**3 - v_range * v_endurance**3
    b = (d_pe * v_range**3 - d_pr * v_endurance**3) / det
    c = (v_endurance * d_pr - v_range * d_pe) / det
    return 1.0 + b * v + c * v**3


def flight_time_and_range(
    speed_ms: float,
    power_ratio: float,
    hover_power_w: float,
    energy_wh: float,
    cf: float,
) -> tuple[float, float]:
    t_min = energy_wh / (hover_power_w * power_ratio) * 60.0 * cf
    range_km = speed_ms * 3.6 * t_min / 60.0
    return t_min, range_km


ANCHOR_V_REST = [4.178, 3.815, 3.718, 3.643, 3.360]
ANCHOR_AH_USED = [0.000, 11.600, 14.880, 17.662, 25.200]
USABLE_AH = 25.2
ANCHOR_SOC = [100.0 * (1.0 - ah / USABLE_AH) for ah in ANCHOR_AH_USED]


def soc_from_rest_cell_voltage(v_cell: float) -> float:
    pairs = sorted(zip(ANCHOR_V_REST, ANCHOR_SOC))
    if v_cell <= pairs[0][0]:
        return pairs[0][1]
    if v_cell >= pairs[-1][0]:
        return pairs[-1][1]

    for (v0, soc0), (v1, soc1) in zip(pairs, pairs[1:]):
        if v0 <= v_cell <= v1:
            t = (v_cell - v0) / (v1 - v0)
            return soc0 + t * (soc1 - soc0)
    raise RuntimeError("unreachable")


def stadium_voltage_check(hover_20_min: float):
    volts = [23.00, 22.9, 22.8, 22.8, 22.7, 22.6, 22.6, 22.5, 22.4, 22.4]
    speed_ms = 6.0
    speed_kmh = speed_ms * 3.6
    hover_range_if_ratio_1 = speed_kmh * hover_20_min / 60.0

    rows = []
    for sag_per_cell in [0.03, 0.10, 0.20]:
        soc = [soc_from_rest_cell_voltage(v / 6.0 + sag_per_cell) for v in volts]
        delta_soc = soc[0] - soc[-1]
        # Measurement 1 to measurement 10 spans nine known intervals. If the
        # first value was effectively at mission start, use the full 2.8 km.
        for distance_km, label in [(2.52, "nine_intervals"), (2.80, "full_2p8km")]:
            range_80_km = distance_km * 80.0 / delta_soc
            ratio_from_range = hover_range_if_ratio_1 / range_80_km
            rows.append((sag_per_cell, label, soc[0], soc[-1], delta_soc, range_80_km, ratio_from_range))
    return rows


def main() -> None:
    s = Scenario()
    thrust_g, motor_power_w, hover_power_w, energy_wh, cf, bau = current_case(s)
    hover_20_min = energy_wh / hover_power_w * 60.0 * cf

    v_end = bau["optimal_endurance_speed_ms"]
    v_range = bau["optimal_speed_ms"]
    q_a, q_b = menzil1_quadratic_coeffs(v_end, v_range)

    print("=== Reproduced 12.4 kg menzil1.py case ===")
    print(f"Thrust per motor: {thrust_g:.1f} g")
    print(f"Hover power: {hover_power_w:.1f} W ({motor_power_w:.1f} W/motor)")
    print(f"Battery energy: {energy_wh:.1f} Wh")
    print(f"Standard CF: {cf:.6f}")
    print(f"Hover time to 20% reserve: {hover_20_min:.2f} min")
    print(f"vi,h={bau['vi_h']:.3f} m/s, ve={v_end:.3f} m/s, vr={v_range:.3f} m/s")
    print()

    print("=== 6 m/s stadium voltage check ===")
    print("sag_cell  span             SOC_start  SOC_end  dSOC   range80  P/Ph@6")
    for row in stadium_voltage_check(hover_20_min):
        sag, label, soc0, soc1, dsoc, range80, ratio = row
        print(f"{sag:7.2f}  {label:15s}  {soc0:8.2f}  {soc1:7.2f}  {dsoc:5.2f}  {range80:7.2f}  {ratio:6.3f}")
    print()

    print("=== 20 m/s model comparison ===")
    print("model                         P/Ph     t20_min  range20_km")

    models = []
    models.append(("current_menzil1_quadratic", menzil1_quadratic(20.0, q_a, q_b)))
    models.append(("range_tangent_cd0_lower", range_tangent_cubic_tail(20.0, v_range, 1.092, hover_power_w, s.drag_area_cm2, 0.0)))
    for cd in [0.5, 1.0, 1.3, 1.5, 2.0, 3.0]:
        models.append((f"range_tangent_cd{cd:g}", piecewise_recommended(20.0, v_end, v_range, hover_power_w, s.drag_area_cm2, cd)))
    models.append(("minimal_bv_plus_cv3", cubic_through_anchors(20.0, v_end, v_range)))

    for name, ratio in models:
        t_min, range_km = flight_time_and_range(20.0, ratio, hover_power_w, energy_wh, cf)
        print(f"{name:29s}  {ratio:5.3f}    {t_min:7.2f}    {range_km:8.2f}")

    print()
    print("=== Speed table: quadratic vs cubic vs recommended ===")
    speed_models = [
        ("quadratic_current", lambda v: menzil1_quadratic(v, q_a, q_b)),
        ("cubic_1_plus_bv_cv3", lambda v: cubic_through_anchors(v, v_end, v_range)),
        ("recommended_cd1", lambda v: piecewise_recommended(
            v, v_end, v_range, hover_power_w, s.drag_area_cm2, 1.0
        )),
    ]
    print("speed  model                  P/Ph   t20_min  km20    t10_min  km10")
    for speed_ms in [10.0, 15.0, 20.0]:
        for model_name, model_fn in speed_models:
            ratio = model_fn(speed_ms)
            t20_min, km20 = flight_time_and_range(speed_ms, ratio, hover_power_w, energy_wh, cf)
            print(
                f"{speed_ms:5.1f}  {model_name:21s}  {ratio:5.3f}"
                f"  {t20_min:7.2f}  {km20:6.2f}"
                f"  {t20_min * 1.125:7.2f}  {km20 * 1.125:6.2f}"
            )

    print()
    print("=== Current quadratic speed samples ===")
    for v in [0, 6, v_end, v_range, 14.104, 20]:
        ratio = menzil1_quadratic(v, q_a, q_b)
        print(f"v={v:6.3f} m/s  P/Ph={ratio:6.3f}  P/v={ratio / v if v else float('nan'):.4f}")


if __name__ == "__main__":
    main()
