# July 3, 2026 calibration inputs

This directory contains the public inputs used to rebuild the July 3 fit:

- `00000076.BIN` and `00000077.BIN`: ArduPilot DataFlash logs.
- `Datalink/UART-260703-*/*.udat`: T-MOTOR DataLink ESC telemetry.
- `flight_attitude.csv`: the derived attitude/speed input used by the
  drag-constrained fit. It is retained to reproduce that fit without a separate
  extraction step; it is not an independent measurement source.

The current reproduction helper accepts declared aircraft geometry and mass;
the documented scenario is G29*9.5 CF, four rotors and assumed 12.4 kg.
The legacy `analyze-calibration` CLI still uses its fixed 28-inch, 12.4 kg
preset. Neither software default establishes the measured configuration of
every historical flight. See [the reproduction commands](../../../docs/REPRODUCIBILITY.md).

DataLink filenames are interpreted as Europe/Istanbul local time (UTC+3).
Session matching examines candidate timestamp modes and flight overlap.
The retained GPS week/milliseconds helper omits the 18-second GPS-to-UTC
correction applicable to July 2026, so the existing joins use a legacy
coordinate rather than independently verified UTC synchronization. Reproducing
those joins does not validate the clock alignment.

The parser sums `voltage × current` over four ESC slots. The archive describes
a 6S2P battery and treats that sum as a single sensed branch, but physical
sensor placement is unverified. Doubling power and energy is a conditional
historical convention, not a consequence of parallel battery count alone.
The 25.2 Ah energy basis comes from prior analysis and is not remeasured by
integrating this partial flight. Full assumptions are in
[Methodology](../../../docs/METHODOLOGY.md).

Raw July 3 telemetry is retained unchanged. These logs include original flight
GPS positions and autopilot parameters. No raw July 21 or later-flight BIN/UDAT
files are added to this directory; the separate public July 21 replay uses
derived observations with its own provenance record.
