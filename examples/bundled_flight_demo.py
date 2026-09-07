"""Rebuild the included G29 fit and its two main plots; no command-line flags.

Run from a repository clone after installation. These logs describe one
aircraft. Fit your own flight logs before applying the models to your aircraft.
The whole-aircraft power and energy inputs below are illustrative.
"""

from pathlib import Path

from flight_workflow import FlightFit, from_calibration_suite
from reproduce_calibration import build_calibration_suite


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data/calibration/2026-07-03"
OUTPUT_DIR = ROOT / "flight-output"
HOVER_POWER_W = 1500.0
USABLE_ENERGY_WH = 1100.0  # Already excludes the energy you keep in reserve.


def main():
    print("Example aircraft only: fit your own logs before using these curves.")
    suite = build_calibration_suite(DATA_ROOT, mass_kg=12.4, prop_diameter_inch=29.0)
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
        speed_ms=17.0,
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


if __name__ == "__main__":
    main()
