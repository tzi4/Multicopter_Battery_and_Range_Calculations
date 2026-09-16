"""Rebuild the README data tables and PNG/SVG figures with one command."""

import argparse
import json
from pathlib import Path

from reproduce_calibration import reproduce as reproduce_calibration, check_summary
from reproduce_validation import reproduce as reproduce_validation
from render_readme_figures import calibration_figure, validation_figure


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=root / "data/calibration/2026-07-03")
    parser.add_argument("--validation-root", type=Path, default=root / "data/validation/2026-07-21")
    parser.add_argument("--output-dir", type=Path, default=Path("showcase-output"))
    parser.add_argument("--prop-diameter", type=float, choices=(28.0, 29.0), default=29.0)
    parser.add_argument("--mass", type=float, default=12.4)
    parser.add_argument("--check-results", type=Path, help="Directory containing reference JSON summaries for this exact scenario")
    args = parser.parse_args()
    try:
        # Read references before writing any outputs, including when paths coincide.
        expected = {
            name: json.loads((args.check_results / f"{name}-summary.json").read_text(encoding="utf-8"))
            for name in ("calibration", "validation")
        } if args.check_results else {}
        calibration = reproduce_calibration(args.data_root, args.output_dir, args.mass, args.prop_diameter)
        validation = reproduce_validation(args.data_root, args.validation_root, args.output_dir, args.mass, args.prop_diameter)
        for name, result in (("calibration", calibration), ("validation", validation)):
            if expected:
                check_summary(result, expected[name], name)
        figures = args.output_dir / "figures"
        figures.mkdir(parents=True, exist_ok=True)
        calibration_figure(calibration, figures)
        validation_figure(calibration, validation, figures)
        print(f"All data tables and figures: {args.output_dir.resolve()}")
        if expected:
            print("Both saved summaries match (exact provenance; numeric tolerance 1e-9).")
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
