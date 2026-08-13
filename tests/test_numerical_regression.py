"""Golden values captured from pre-cleanup commit 3d338ab33209d168a8393f167b96a316b7cd10ce."""

import pytest

import multicopter_range


def test_bauersfeld_public_example_matches_legacy_result():
    result = multicopter_range.BauersfeldRangeCalculator(
        hover_power_w=1500.0,
        correction_factor=0.93,
        battery_wh=1200.0,
        total_mass_kg=12.4,
        drag_area_cm2=450.0,
        prop_diameter_inch=28.0,
        num_rotors=4,
    ).solve()

    assert result == pytest.approx(
        {
            "vi_h": 5.589791639464894,
            "max_range_km": 26.818697600145192,
            "optimal_speed_ms": 10.934146422998264,
            "flight_time_min_range": 40.879120879120876,
            "power_range_w": 1638.0,
            "max_endurance_min": 48.84026258205689,
            "optimal_endurance_speed_ms": 6.711228919637015,
            "power_endurance_w": 1371.0,
            "max_range_km_endurance": 19.666690961001947,
        },
        abs=1e-12,
    )


@pytest.mark.parametrize(
    ("cells", "capacity_mah", "chemistry", "expected_wh"),
    [
        (6, 5000, "lipo", 111.0),
        (6, 5000, "lihv", 119.88),
        (12, 27000, "liion", 1198.8),
    ],
)
def test_battery_energy_matches_legacy_result(
    cells, capacity_mah, chemistry, expected_wh
):
    assert multicopter_range.calculate_real_energy_wh(
        cells, capacity_mah, chemistry
    ) == pytest.approx(expected_wh, abs=1e-12)


def test_representative_speed_result_matches_legacy_result():
    row = multicopter_range.calculate_flight_for_speed(
        speed_ms=10.0,
        power_ratio=1.05,
        hover_power_w=1500.0,
        battery_wh=1200.0,
        correction_factor=0.93,
    )

    assert row["power_w"] == pytest.approx(1575.0, abs=1e-12)
    assert row["time_20_min"] == pytest.approx(42.51428571428571, abs=1e-12)
    assert row["range_20_km"] == pytest.approx(25.50857142857143, abs=1e-12)
    assert row["time_10_min"] == pytest.approx(47.82857142857143, abs=1e-12)
    assert row["range_10_km"] == pytest.approx(28.697142857142858, abs=1e-12)
