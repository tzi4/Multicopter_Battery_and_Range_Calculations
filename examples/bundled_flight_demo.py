"""Rebuild the included G29 fit and its two main plots; no command-line flags.

Run from a repository clone after installation. These logs describe one
aircraft. Fit your own flight logs before applying the models to your aircraft.
The power and energy basis follows the author's saved report. Its electrical
scaling is a historical scenario; see docs/AUTHOR_DEFAULTS.md.
"""

from pathlib import Path

from flight_workflow import FlightFit, from_calibration_suite
from reproduce_calibration import build_calibration_suite
from aircraft_inputs import MASS_KG, NUM_ROTORS, PROPELLER_INCH, REFERENCE_AREA_CM2, PLANNED_SPEED_MS, postflight_energy_basis


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data/calibration/2026-07-03"
OUTPUT_DIR = ROOT / "flight-output"
ENERGY_BASIS = postflight_energy_basis()
HOVER_POWER_W = ENERGY_BASIS["hover_power_w"]
USABLE_ENERGY_WH = ENERGY_BASIS["usable_energy_wh"]  # Already excludes reserve.


def main():
    if NUM_ROTORS != 4 or REFERENCE_AREA_CM2 != 450.0:
        raise ValueError(
            "The bundled logs use four rotors and a 450 cm^2 reference area. "
            "Use postflight_fit.py with your own logs for another airframe."
        )
    print("Example aircraft only: fit your own logs before using these curves.")
    suite = build_calibration_suite(DATA_ROOT, mass_kg=MASS_KG, prop_diameter_inch=PROPELLER_INCH)
    fit = from_calibration_suite(suite)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fit.save(OUTPUT_DIR / "aircraft-fit.json")
    fit.plot(
        OUTPUT_DIR,
        hover_power_w=HOVER_POWER_W,
        usable_energy_wh=USABLE_ENERGY_WH,
        max_speed_ms=20.0,
    )

    # Subsequent estimates need only this JSON and the electrical inputs.
    saved_fit = FlightFit.load(OUTPUT_DIR / "aircraft-fit.json")
    predictions = saved_fit.predict(
        speed_ms=PLANNED_SPEED_MS,
        hover_power_w=HOVER_POWER_W,
        usable_energy_wh=USABLE_ENERGY_WH,
    )
    for name, row in predictions.items():
        print(
            f"{name}: {row['power_w']:.1f} W, "
            f"{row['endurance_min']:.2f} min, {row['range_km']:.2f} km "
            f"(within fitted speed range: {row['within_fitted_speed_range']})"
        )
    print(f"Fit and figures: {OUTPUT_DIR}")
    return predictions


if __name__ == "__main__":
    main()
