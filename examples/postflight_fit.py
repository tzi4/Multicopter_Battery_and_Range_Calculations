"""Edit this configuration, then run: python examples/postflight_fit.py.

Use your own aircraft and calibrated electrical telemetry. The bundled logs are
specific to one aircraft and are not a ready-made fit for another configuration.
"""

from pathlib import Path

from flight_workflow import Aircraft, FitOptions, FlightFit, fit_flight, load_ardupilot_log


# Replace these illustrative values and the path with your measured inputs.
LOG_PATH = Path("my-logs/flight.BIN")
OUTPUT_DIR = Path("my-flight-output")
AIRCRAFT = Aircraft(
    name="My multicopter",
    mass_kg=12.4,
    num_rotors=4,
    prop_diameter_inch=29.0,
    reference_area_m2=0.045,
    hover_rpm=2200.0,  # Mechanical RPM; needed when BAT has no RPM telemetry.
)
# Hover must match the electrical basis of the log (BAT or selected ESC sum).
LOG_HOVER_POWER_W = 1500.0
# Future estimates need measured whole-aircraft hover and energy after reserve.
PREDICTION_HOVER_POWER_W = 1500.0
USABLE_ENERGY_WH = 1100.0
PLANNED_SPEED_MS = 10.0


def main():
    samples = load_ardupilot_log(
        LOG_PATH,
        power_source="battery",  # Reads BAT.Volt * BAT.Curr from this monitor.
        battery_instance=0,
        current_scale=1.0,  # Change only from an independent sensor calibration.
        time_shift_s=0.0,  # Added to electrical timestamps; establish independently.
        max_dt_s=0.35,
    )
    # With complete ESC telemetry instead:
    # samples = load_ardupilot_log(LOG_PATH, power_source="esc", esc_ids=(0, 1, 2, 3))
    # For synchronized CSV exports from other log formats:
    # from flight_workflow import load_flight_csv
    # samples = load_flight_csv("my-logs/synchronized.csv")
    fit = fit_flight(samples, AIRCRAFT, LOG_HOVER_POWER_W, options=FitOptions())
    fit_path = fit.save(OUTPUT_DIR / "aircraft-fit.json")
    figures = fit.plot(OUTPUT_DIR, PREDICTION_HOVER_POWER_W, USABLE_ENERGY_WH, max_speed_ms=20.0)
    print(f"Saved fit: {fit_path}")
    print(f"Fitted speed-bin range: {fit.fitted_speed_range}")
    for name, path in figures.items():
        print(f"{name}: {path}")

    # On later runs, start here. No raw log parsing or fitting is required.
    saved_fit = FlightFit.load(fit_path)
    for name, prediction in saved_fit.predict(PLANNED_SPEED_MS, PREDICTION_HOVER_POWER_W, USABLE_ENERGY_WH).items():
        domain = "within fitted range" if prediction["within_fitted_speed_range"] else "extrapolation"
        print(f"{name}: {prediction['power_w']:.1f} W, "
              f"{prediction['endurance_min']:.2f} min, {prediction['range_km']:.2f} km ({domain})")


if __name__ == "__main__":
    main()
