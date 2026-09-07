"""Render standalone PNG/SVG figures from the public reproduction summaries."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


MODELS = {
    "zeng_datalink_fit": ("Zeng fit", "#1769aa", "-"),
    "faessler_datalink_fit": ("Faessler-inspired fit", "#bc541a", "--"),
    "kirschstein_datalink_fit": ("Kirschstein-inspired fit", "#267452", ":"),
}


def axes_pair(title, subtitle):
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.5), sharex=True,
                             gridspec_kw={"height_ratios": [2.1, 1]}, layout="constrained")
    fig.suptitle(title + "\n" + subtitle, fontsize=13, fontweight="medium")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.2)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Electrical power / July 3 hover reference, P/Ph")
    axes[1].axhline(0, color="#777777", linewidth=0.8)
    axes[1].set_xlabel("Ground speed (m/s)")
    return fig, axes


def save(fig, output_dir, name):
    for extension in ("png", "svg"):
        path = output_dir / f"{name}.{extension}"
        fig.savefig(path, dpi=160, facecolor="white")
        if extension == "svg":
            # Matplotlib emits trailing spaces in SVG paths; keep repository diffs clean.
            path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")
    plt.close(fig)


def calibration_figure(calibration, output_dir):
    profile = calibration["profile"]
    fig, (ax, residual) = axes_pair(
        "July 3 calibration · all 11 retained speed bins",
        f"G{profile['prop_diameter_inch']:g} scenario · {profile['mass_kg']:g} kg assumed · fitted on these observations",
    )
    bins = calibration["bins"]
    speeds = [row["speed_ms"] for row in bins]
    ax.axvspan(min(speeds), max(speeds), color="#edf2f5", zorder=0)
    curves = [row for row in calibration["model_curves"] if min(speeds) <= row["speed_ms"] <= max(speeds)]
    for name, (label, color, style) in MODELS.items():
        ax.plot([r["speed_ms"] for r in curves], [r[name] for r in curves],
                label=label, color=color, linestyle=style, linewidth=2)
        residual.plot(speeds, [r["predicted_ratio"][name] - r["power_ratio"] for r in bins],
                      marker="o", markersize=4, color=color, linestyle=style)
    ax.scatter(speeds, [r["power_ratio"] for r in bins], s=38, color="#202a35", zorder=4,
               label="Measured bin medians")
    ax.legend(loc="upper left", fontsize=9, frameon=False, ncols=2)
    ax.set_ylim(0.9, 1.16)
    residual.set_ylabel("Prediction − observation\n(P/Ph)")
    residual.set_xlim(2, 13)
    save(fig, output_dir, "calibration")


def validation_figure(calibration, validation, output_dir):
    variant = validation["variants"]["current_scalar_accel_gate"]
    bins = variant["bins"]
    profile = calibration["profile"]
    fig, (ax, residual) = axes_pair(
        f"July 21 comparison · all {len(bins)} retained speed bins",
        f"July 3 coefficients held fixed · G{profile['prop_diameter_inch']:g} / {profile['mass_kg']:g} kg scenario · retrospective selection",
    )
    curves = calibration["model_curves"]
    low, high = min(r["speed_ms"] for r in calibration["bins"]), max(r["speed_ms"] for r in calibration["bins"])
    for pane in (ax, residual):
        pane.axvspan(low, high, color="#edf2f5", zorder=0)
    speeds = [r["speed_ms"] for r in bins]
    for name, (label, color, style) in MODELS.items():
        ax.plot([r["speed_ms"] for r in curves], [r[name] for r in curves],
                label=label, color=color, linestyle=style, linewidth=2)
        residual.plot(speeds, [r["percent_residual"][name] for r in bins],
                      color=color, linestyle=style, marker="o", markersize=4)
    ax.scatter(speeds, [r["measured_ratio"] for r in bins], s=38, color="#202a35", zorder=4,
               label="July 21 bin medians")
    ax.legend(loc="upper left", fontsize=9, frameon=False, ncols=2)
    ax.text(0.02, 0.03, "Shading: July 3 calibration speed interval", transform=ax.transAxes,
            fontsize=9, color="#4e5964")
    residual.set_ylabel("100 × (observation /\nprediction − 1), %")
    residual.set_xlim(2, 18)
    save(fig, output_dir, "validation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("docs/results"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/assets"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.hashsalt": "multicopter-range"})
    calibration = json.loads((args.results_dir / "calibration-summary.json").read_text())
    validation = json.loads((args.results_dir / "validation-summary.json").read_text())
    if calibration["profile"] != validation["profile"]:
        raise ValueError("Calibration and validation summaries must declare the same scenario")
    if calibration["module_sha256"] != validation["module_sha256"]:
        raise ValueError("Calibration and validation summaries must use the same model source")
    calibration_figure(calibration, args.output_dir)
    validation_figure(calibration, validation, args.output_dir)
    print(f"Saved calibration and validation figures to {args.output_dir}")


if __name__ == "__main__":
    main()
