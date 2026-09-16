"""Edit aircraft_inputs.py, then run this file for the author's first estimate.

Install the project with ``python -m pip install -e .`` first. Hover power can
come from a propulsion test or a previous hover measurement. This example uses
the author's manufacturer-table power and recovered empirical standard CF.
"""

from multicopter_range import BauersfeldRangeCalculator
from aircraft_inputs import preflight_inputs


def main():
    inputs = preflight_inputs()
    aircraft = BauersfeldRangeCalculator(**inputs)
    result = aircraft.solve()
    print(f"Empirical correction factor: {inputs['correction_factor']:.6f}")
    print(f"Bench hover-power estimate: {inputs['hover_power_w']:.2f} W")
    print(f"Nominal energy: {inputs['battery_wh']:.2f} Wh")
    print(f"Best-range speed: {result['optimal_speed_ms']:.2f} m/s")
    print(f"Best-range power: {result['power_range_w']:.1f} W")
    print(f"Best-range flight time: {result['flight_time_min_range']:.2f} min")
    print(f"Maximum range: {result['max_range_km']:.2f} km")
    print(f"Best-endurance speed: {result['optimal_endurance_speed_ms']:.2f} m/s")
    print(f"Maximum endurance: {result['max_endurance_min']:.2f} min")
    return result


if __name__ == "__main__":
    main()
