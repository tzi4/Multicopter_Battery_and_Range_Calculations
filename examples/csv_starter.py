"""Fit the compact real-flight CSV, export a report, and reuse the saved fit.

Install from the repository or starter ZIP with ``python -m pip install -e .``.
Edit the paths and electrical references below; edit aircraft_inputs.py for
the aircraft configuration. Run: python examples/csv_starter.py
"""

from pathlib import Path

from flight_workflow import Aircraft, FitOptions, FlightFit, fit_flight, load_flight_csv
from aircraft_inputs import (
    MASS_KG, NUM_ROTORS, PROPELLER_INCH, REFERENCE_AREA_CM2,
    REPRESENTATIVE_RPM, postflight_energy_basis,
)


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/starter/flight.csv"
OUTPUT_DIR = ROOT / "starter-output"
AIRCRAFT = Aircraft(
    name="July 3 CSV starter aircraft",
    mass_kg=MASS_KG,
    num_rotors=NUM_ROTORS,
    prop_diameter_inch=PROPELLER_INCH,
    reference_area_m2=REFERENCE_AREA_CM2 / 10000,
    hover_rpm=REPRESENTATIVE_RPM,
)
# The CSV records the original four-ESC sum. Normalize with that same boundary.
# Replace this with your own measured hover reference when changing the CSV.
LOG_HOVER_POWER_W = 757.891

# Absolute predictions retain the author's separate historical scenario.
# Use calibrated whole-aircraft power and energy for your own aircraft.
ENERGY_BASIS = postflight_energy_basis()
PREDICTION_HOVER_POWER_W = ENERGY_BASIS["hover_power_w"]
USABLE_ENERGY_WH = ENERGY_BASIS["usable_energy_wh"]  # Already excludes reserve.
PLANNED_SPEED_MS = 10.0
MAX_PLOT_SPEED_MS = 20.0
OPTIONS = FitOptions()


def main():
    samples = load_flight_csv(CSV_PATH)
    fit = fit_flight(samples, AIRCRAFT, LOG_HOVER_POWER_W, options=OPTIONS)
    outputs = fit.export(
        OUTPUT_DIR, PREDICTION_HOVER_POWER_W, USABLE_ENERGY_WH,
        speed_ms=PLANNED_SPEED_MS, max_speed_ms=MAX_PLOT_SPEED_MS,
    )
    print(f"Input samples: {fit.metadata['sample_count']}")
    print(f"Retained speed bins: {len(fit.observations)}")
    low, high = fit.fitted_speed_range
    print(f"Fitted speed-bin range: {low:.2f} to {high:.2f} m/s")
    for label, path in outputs.items():
        print(f"{label}: {path}")

    # Reuse this JSON on a later day without parsing or fitting the CSV again.
    restored = FlightFit.load(outputs["fit"])
    predictions = restored.predict(
        PLANNED_SPEED_MS, PREDICTION_HOVER_POWER_W, USABLE_ENERGY_WH,
    )
    for name, row in predictions.items():
        domain = "within fitted range" if row["within_fitted_speed_range"] else "extrapolation"
        print(f"{name} at {PLANNED_SPEED_MS:g} m/s: {row['power_w']:.1f} W, "
              f"{row['endurance_min']:.2f} min, {row['range_km']:.2f} km ({domain})")
    return fit, outputs, predictions


if __name__ == "__main__":
    main()
