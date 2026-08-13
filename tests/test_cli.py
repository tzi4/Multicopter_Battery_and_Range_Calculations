import pytest

import multicopter_range


def test_calculate_command_prints_expected_metrics(capsys):
    multicopter_range.main(
        [
            "calculate",
            "--hover-power",
            "1500",
            "--battery-energy",
            "1200",
            "--mass",
            "12.4",
            "--drag-area",
            "450",
            "--prop-diameter",
            "28",
            "--rotors",
            "4",
        ]
    )

    output = capsys.readouterr().out
    assert "Best-range speed:" in output
    assert "Maximum endurance:" in output


def test_calculate_command_rejects_non_positive_physical_inputs():
    with pytest.raises(SystemExit):
        multicopter_range.main(
            [
                "calculate",
                "--hover-power",
                "0",
                "--battery-energy",
                "1200",
                "--mass",
                "12.4",
                "--drag-area",
                "450",
                "--prop-diameter",
                "28",
                "--rotors",
                "4",
            ]
        )


def test_bundled_calibration_root_is_discoverable():
    root = multicopter_range.find_measured_curve_log_root()
    assert root.name == "2026-07-03"
    assert (root / "00000076.BIN").is_file()
    assert (root / "Datalink").is_dir()
