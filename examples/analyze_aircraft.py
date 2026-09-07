"""Run both stages together after editing aircraft_inputs.py.

The preflight estimate uses the empirical CF. The postflight demonstration uses
the saved report's power/energy scenario and an explicit 10% reserve. These are
two estimates with different evidence and energy conventions, not two factors
to multiply together.
"""

from preflight_estimate import main as preflight
from bundled_flight_demo import main as postflight


def main():
    print("Before flight: Bauersfeld first estimate")
    preflight()
    print("\nAfter flight: three models fitted to the included aircraft logs")
    postflight()


if __name__ == "__main__":
    main()
