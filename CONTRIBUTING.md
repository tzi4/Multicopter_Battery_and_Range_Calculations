# Contributing

Thank you for helping improve the project.

1. Open an issue for substantial changes so the model assumptions can be
   discussed first.
2. Create a focused branch and keep commits small.
3. Install development dependencies with `python -m pip install -e '.[dev]'`.
4. Run `python -m pytest -q` before opening a pull request.
5. Explain any change to physical assumptions, calibration constants, or log
   selection in the pull request and update `docs/METHODOLOGY.md`.

Do not commit credentials, personal information, unrelated flight logs, cache
directories, or generated plots. New flight data should include provenance,
aircraft configuration, units, sensor scaling, and a test that consumes it.
