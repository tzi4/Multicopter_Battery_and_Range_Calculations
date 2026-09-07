"""Editable author inputs recovered from the latest saved aircraft report.

These are the author's working assumptions, not universal aircraft constants.
See docs/AUTHOR_DEFAULTS.md for the source and electrical interpretation.
"""

import multicopter_range as model


MASS_KG = 12.4
NUM_ROTORS = 4
PROPELLER_INCH = 29.0
MOTOR_POWER_TABLE = model.u8lite_kv190_g29_data  # Keep this consistent with the propeller.
REFERENCE_AREA_CM2 = 450.0
BATTERY_PACKS = 2
CELLS_PER_PACK = 6
CAPACITY_MAH_PER_PACK = 27000.0
BATTERY_TYPE = "liion"
RESERVE_FRACTION = 0.10
PLANNED_SPEED_MS = 17.0
REPRESENTATIVE_RPM = 2149.761904761904  # July 3 stable-bin RPM statistic, not hover-only.

# Empirical Vibe reference used by the author's original standard-CF menu.
REFERENCE_MASS_KG = 19.5
REFERENCE_PACKS = 4
REFERENCE_CELLS_PER_PACK = 6
REFERENCE_CAPACITY_MAH = 17000.0
REFERENCE_HOVER_MIN = 35.0


def standard_correction_factor():
    reference_wh = model.calculate_real_energy_wh(
        REFERENCE_PACKS * REFERENCE_CELLS_PER_PACK,
        REFERENCE_CAPACITY_MAH,
        "lihv",
    )
    reference_power_w = 4 * model.get_power_from_thrust(
        REFERENCE_MASS_KG * 1000 / 4, model.p80_thrust_power
    )
    return REFERENCE_HOVER_MIN / (60 * reference_wh / reference_power_w)


# Set a different value here after calibrating your own aircraft.
CORRECTION_FACTOR = standard_correction_factor()  # 0.6159319356, approximately 0.62.


def nominal_energy_wh():
    # Pack count multiplies energy; this does not describe a physical 12S wiring.
    return model.calculate_real_energy_wh(
        BATTERY_PACKS * CELLS_PER_PACK, CAPACITY_MAH_PER_PACK, BATTERY_TYPE
    )


def preflight_inputs():
    """The author's U8 Lite KV190 + G29 bench-based first-estimate inputs."""
    return {
        "hover_power_w": NUM_ROTORS * model.get_power_from_thrust(
            MASS_KG * 1000 / NUM_ROTORS, MOTOR_POWER_TABLE
        ),
        "correction_factor": CORRECTION_FACTOR,
        "battery_wh": nominal_energy_wh(),
        "total_mass_kg": MASS_KG,
        "drag_area_cm2": REFERENCE_AREA_CM2,
        "prop_diameter_inch": PROPELLER_INCH,
        "num_rotors": NUM_ROTORS,
    }


def postflight_energy_basis():
    """Reproduce the saved report's electrical scenario, then deduct reserve.

    The legacy factor of two is retained for comparison, not inferred from the
    number of battery packs. Replace this basis with calibrated whole-aircraft
    measurements for another aircraft or sensor setup. CF is not applied here.
    """
    source_esc_hover_w = 757.891
    historical_vehicle_multiplier = 2.0
    historical_source_bench_w = 4 * model.get_power_from_thrust(
        12400.0 / 4, model.u8lite_kv190_data
    )
    hover_w = preflight_inputs()["hover_power_w"] * (
        historical_vehicle_multiplier * source_esc_hover_w / historical_source_bench_w
    )
    usable_before_reserve_wh = nominal_energy_wh() * (25.2 / 27.0)
    return {
        "hover_power_w": hover_w,
        "usable_before_reserve_wh": usable_before_reserve_wh,
        "usable_energy_wh": usable_before_reserve_wh * (1 - RESERVE_FRACTION),
    }
