from pathlib import Path

import menzil2


def _sample_udat_path():
    return Path(
        "Some Datalink Data/datalink/"
        "UART-260625-021604/UART-260625-040328-040715.udat"
    )


def test_parse_datalink_udat_file_extracts_power_rpm_and_utip():
    parsed = menzil2.parse_datalink_udat_file(_sample_udat_path(), prop_diameter_inch=29.0)

    assert parsed["record_count"] > 1000
    assert parsed["active_motor_count_median"] == 4
    assert 15.0 <= parsed["sample_rate_hz"] <= 25.0
    assert 20.0 <= parsed["voltage_median_v"] <= 24.5
    assert parsed["power_median_w"] > 500.0
    # Mekanik olcek: ham eRPM/10 alani DATALINK_RPM_SCALE (=10/21) ile cevrilir.
    assert 1400.0 <= parsed["rpm_median"] <= 3350.0
    assert 57.0 <= parsed["utip_median_ms"] <= 110.0
    assert len(parsed["samples"]) == parsed["record_count"]


def test_datalink_hover_reference_normalizes_speed_observations():
    joined = []
    for _ in range(4):
        joined.append({
            "speed_ms": 0.4,
            "power_w": 750.0,
            "power_ratio": 0.75,
            "rpm_median": 2095.0,
            "utip_ms": 81.0,
        })
    for _ in range(4):
        joined.append({
            "speed_ms": 5.8,
            "power_w": 765.0,
            "power_ratio": 0.765,
            "rpm_median": 2105.0,
            "utip_ms": 81.4,
        })

    hover_power_w = menzil2.estimate_datalink_hover_power(joined, min_samples=3)
    observations = menzil2.build_datalink_speed_observations(
        joined,
        min_speed_ms=5.0,
        max_speed_ms=6.5,
        min_samples=3,
        power_reference_w=hover_power_w,
    )

    assert hover_power_w == 750.0
    assert len(observations) == 1
    assert observations[0]["power_ratio"] == 765.0 / 750.0
