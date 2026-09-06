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


@pytest.mark.parametrize(
    "option",
    ["--hover-power", "--battery-energy", "--mass", "--drag-area", "--prop-diameter", "--correction-factor"],
)
@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf"])
def test_calculate_command_rejects_nonfinite_inputs(option, invalid, capsys):
    args = {
        "--hover-power": "1500",
        "--battery-energy": "1200",
        "--mass": "12.4",
        "--drag-area": "450",
        "--prop-diameter": "28",
        "--rotors": "4",
        "--correction-factor": "1.0",
    }
    args[option] = invalid
    with pytest.raises(SystemExit) as exc:
        multicopter_range.main(["calculate", *[f"{key}={value}" for key, value in args.items()]])
    assert exc.value.code == 2
    assert "all physical inputs must be finite" in capsys.readouterr().err


def test_calibration_command_uses_external_data_and_its_attitude_prior(
    monkeypatch, tmp_path, capsys
):
    # Model an installed module with no adjacent repository data. The explicit
    # dataset must also select its attitude prior instead of a silent fallback.
    monkeypatch.setattr(multicopter_range, "__file__", str(tmp_path / "site-packages/module.py"))
    data_root = tmp_path / "calibration"
    data_root.mkdir()
    attitude = data_root / "flight_attitude.csv"
    attitude.touch()
    (data_root / "00000076.BIN").touch()
    session = data_root / "Datalink" / "UART-260703-120000"
    session.mkdir(parents=True)
    (session / "UART-260703-120000-121000.udat").touch()

    def analyze(profile, *_args, log_root, make_graph):
        assert log_root == data_root
        assert multicopter_range.find_attitude_log_path(profile) == attitude
        assert make_graph is False
        return {
            "joined_sample_count": 42,
            "measured_hover_power_w": 757.891,
            "utip_ms": 80.05357530658453,
            "speed_bin_observations": [{"speed_ms": 5.0}],
        }

    monkeypatch.setattr(multicopter_range, "run_datalink_measured_curve_analysis", analyze)
    multicopter_range.main(["analyze-calibration", "--data-root", str(data_root)])
    output = capsys.readouterr().out
    assert "Joined samples: 42" in output
    assert "one sensed branch): 757.89 W" in output
    assert "tip speed: 80.05 m/s" in output


def test_calibration_command_explains_missing_wheel_data(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(multicopter_range, "__file__", str(tmp_path / "module.py"))
    with pytest.raises(SystemExit) as exc:
        multicopter_range.main(["analyze-calibration"])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "--data-root" in error
    assert "source repository, not the wheel" in error
    assert "Traceback" not in error


@pytest.mark.parametrize("root_kind", ["missing", "file", "no_attitude"])
def test_calibration_command_rejects_incomplete_data_root(root_kind, tmp_path, capsys):
    root = tmp_path / "calibration"
    if root_kind == "file":
        root.touch()
    elif root_kind == "no_attitude":
        root.mkdir()
    with pytest.raises(SystemExit) as exc:
        multicopter_range.main(["analyze-calibration", "--data-root", str(root)])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "not found" in error
    assert "Traceback" not in error


@pytest.mark.parametrize("graphs", [False, True])
def test_calibration_command_rejects_empty_telemetry(monkeypatch, tmp_path, capsys, graphs):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flight_attitude.csv").touch()
    args = ["analyze-calibration", "--data-root", str(tmp_path)]
    if graphs:
        args.append("--graphs")
    with pytest.raises(SystemExit) as exc:
        multicopter_range.main(args)
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "No usable July 3 calibration telemetry" in output.err
    assert "completed" not in output.out
    assert not list(tmp_path.glob("*.png"))
