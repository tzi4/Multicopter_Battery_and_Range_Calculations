"""Edit the aircraft inputs below, then run this file for a first estimate.

Install the project with ``python -m pip install -e .`` first. Hover power can
come from a propulsion test or a previous hover measurement. The values here
are illustrative, not measurements reconstructed from the bundled flights.
"""

from multicopter_range import BauersfeldRangeCalculator


def main():
    aircraft = BauersfeldRangeCalculator(
        hover_power_w=1500.0,       # Whole-aircraft electrical hover power [W].
        correction_factor=0.93,    # Fraction of entered energy available to use.
        battery_wh=1200.0,         # Whole-pack energy basis [Wh].
        total_mass_kg=12.4,        # Include the battery and payload.
        drag_area_cm2=450.0,       # Projected reference area, not CdA [cm^2].
        prop_diameter_inch=29.0,
        num_rotors=4,
    )
    result = aircraft.solve()
    print(f"Best-range speed: {result['optimal_speed_ms']:.2f} m/s")
    print(f"Best-range power: {result['power_range_w']:.1f} W")
    print(f"Best-range flight time: {result['flight_time_min_range']:.2f} min")
    print(f"Maximum range: {result['max_range_km']:.2f} km")
    print(f"Best-endurance speed: {result['optimal_endurance_speed_ms']:.2f} m/s")
    print(f"Maximum endurance: {result['max_endurance_min']:.2f} min")


if __name__ == "__main__":
    main()
