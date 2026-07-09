# Multicopter Battery and Range Calculation Toolkit

This repository contains an interactive Python workflow for estimating multicopter hover endurance, forward-flight range, and DataLink-calibrated power-speed behavior. The current working entry point is `menzil2.py`. Other Python files are retained primarily for legacy reference, earlier exploratory calculations, or compatibility with previous development steps; routine users should start with `menzil2.py` unless they are deliberately auditing historical calculations.

## Primary Scope

`menzil2.py` combines motor data, battery energy assumptions, empirical DataLink measurements, and several fitted power-speed model families. The most important current workflow is the DataLink-assisted analysis based on the 3 July flight logs. In that workflow, measured motor telemetry and ArduPilot log data are used to infer a normalized power curve, compare fitted model families, and convert those curves into endurance and range estimates.

The code is intended as an engineering analysis tool rather than a certified flight-performance predictor. Its outputs should therefore be interpreted as model-based estimates whose validity depends on the selected battery chemistry, the representativeness of the input logs, and the similarity between the calibrated aircraft and the aircraft being evaluated.

## Installation

Use Python 3.10 or newer. The repository has been used with Python 3.12.

```powershell
git clone https://github.com/tzi4/Multicopter-Battery-and-Range-Calculations.git
cd Multicopter-Battery-and-Range-Calculations

python -m venv .venv
.\.venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt
python menzil2.py
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## Recommended Usage

Run the program with:

```powershell
python menzil2.py
```

The script opens an interactive menu. Enter the aircraft mass, battery configuration, motor selection, and requested analysis mode when prompted. For current work, the recommended path is the `Preset/log DataLink fit analysis` option, followed by the DataLink-fitted model selection. Selecting all available DataLink-fitted models produces the three figures shown below.

### Battery Chemistry Requirement

When Konino Li-ion or solid-state Li-ion packs are used, the battery type prompt must be answered with `LiIon`. Selecting `LiPo` or `LiHV` for Konino packs applies the wrong voltage and energy convention, so the resulting endurance and range values will not be physically consistent with the current calibration. In short: Konino batteries should be modeled with the `LiIon` option.

## Default 3 July Data Set

The repository includes the 3 July DataLink and ArduPilot log data used by the current calibrated workflow:

```text
3 Temmuz Tüm Test Logları/
  00000076.BIN
  00000077.BIN
  Datalink/
    UART-260703-.../
      *.udat
```

If no custom DataLink/log folder is supplied in the main DataLink analysis path, `menzil2.py` searches the repository directory for a folder whose name starts with `3 Temmuz` and uses it as the default log root. The default date hint is `260703`, corresponding to 3 July 2026 in the log naming convention.

Additional flight data can be added by imitating the same structure:

```text
<new-log-folder>/
  <ArduPilot log>.BIN
  Datalink/
    UART-YYMMDD-HHMMSS/
      UART-YYMMDD-HHMMSS-HHMMSS.udat
```

When using a different data set, provide the new folder path at the DataLink/log folder prompt and provide the matching `YYMMDD` date hint. The folder layout matters because the code matches ArduPilot `.BIN` time spans against DataLink `.udat` sessions.

## Figures

The figures below were generated from the included 3 July DataLink data with all DataLink-fitted model families enabled.

### Empirical DataLink Interpolation

![DataLink empirical interpolation](datalink_all_empirical_interpolation.png)

This figure shows the measured stable speed bins extracted from the joined DataLink and ArduPilot samples. The black curve is a within-range empirical interpolation of the observed normalized power ratio, `P(V) / P_hover(DataLink)`. Bauersfeld reference markers are shown for qualitative comparison, but the interpolation itself is measurement-driven.

### Fitted Power-Speed Model Comparison

![DataLink fitted power ratio comparison](datalink_all_power_ratio.png)

This plot compares the DataLink-fitted Zeng, Faessler, and Kirschstein model families against the measured bins. The vertical axis is normalized by the measured DataLink hover reference, which makes the figure useful for comparing curve shape independently of the absolute battery capacity used later in the range calculation.

### Range and Endurance Projection

![DataLink range and endurance comparison](datalink_all_range_time.png)

This figure converts the fitted power-speed curves into practical outputs: range at 10 percent reserve and endurance at 10 percent reserve. The projection depends on both the fitted power ratio and the selected range/time battery basis. Therefore, changing the aircraft battery, reserve convention, or hover reference changes the numerical result even when the normalized curve shape remains the same.

## Repository Layout

- `menzil2.py`: the current primary interactive analysis program.
- `requirements.txt`: Python dependencies required for the current workflow.
- `3 Temmuz Tüm Test Logları/`: default DataLink and ArduPilot logs for the calibrated 3 July analysis.
- `flight_attitude_00000075.csv` and `flight_attitude_00000075_armed.csv`: attitude-derived support data used by the model-fitting workflow.
- `menzil1.py` and other Python scripts: legacy or auxiliary files retained for comparison, continuity, and earlier analyses.

## License

This project is distributed under the MIT License. See `LICENSE` for details.
