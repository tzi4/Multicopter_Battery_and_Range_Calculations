# 3 July 2026 calibration data

This directory contains the raw inputs required by the end-to-end calibration
tests.

- `00000076.BIN` and `00000077.BIN` are ArduPilot DataFlash logs.
- `Datalink/UART-260703-*/*.udat` contains T-MOTOR DataLink ESC telemetry.
- `flight_attitude.csv` is the attitude/speed extraction used by the
  drag-constrained fit. It is derived from the flight log and retained to make
  that fit reproducible without a separate conversion step.

The timestamps in the DataLink filenames are interpreted as Europe/Istanbul
local time (UTC+3) for this data set. The parser evaluates candidate timestamp
modes and only accepts sessions that overlap the ArduPilot flight windows.

The aircraft used a 6S2P pack while the electrical sensor measured a single
parallel branch. See the [methodology](../../../docs/METHODOLOGY.md) for the
resulting scale convention.

These files are research telemetry. The ArduPilot logs contain the original
flight's GPS positions and non-secret autopilot parameters; they contain no API
credentials or configured board/battery serial number. Before adding new logs,
inspect them for information you do not intend to publish.
