from __future__ import annotations

import csv
import json
import math
import statistics
import traceback
from datetime import timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import analyze_july21_anomaly as july21
import menzil2


ROOT = Path(__file__).resolve().parent
JULY3_ROOT = next(path for path in ROOT.iterdir() if path.is_dir() and path.name.startswith("3 Temmuz"))
JULY21_ROOT = next(path for path in ROOT.iterdir() if path.is_dir() and path.name.startswith("21 temmuz"))
OUTPUT_DIR = JULY21_ROOT / "analiz_ciktilari" / "menzil2_3temmuz_karsilastirma"

JULY21_DATALINK_CLOCK_AHEAD_S = 56.18
JULY21_PROP_DIAMETER_INCH = 28.0
FULL_PACK_PARALLEL_ARMS = menzil2.FIRFIR_BATTERY_PARALLEL_ARMS

MODEL_COLORS = {
    "zeng_datalink_fit": "#1f77b4",
    "faessler_datalink_fit": "#2ca02c",
    "kirschstein_datalink_fit": "#9467bd",
}
MODEL_LABELS = {
    "zeng_datalink_fit": "Zeng — 3 Temmuz fit",
    "faessler_datalink_fit": "Faessler — 3 Temmuz fit",
    "kirschstein_datalink_fit": "Kirschstein — 3 Temmuz fit",
}


def firfir_context():
    profile = menzil2.build_speed_model_profile("1", 12.4, 4, 29.0, 450.0)
    hover_power_w = (
        menzil2.get_power_from_thrust(12400.0 / 4.0, menzil2.u8lite_kv190_g29_data)
        * 4.0
    )
    battery_wh = menzil2.calculate_real_energy_wh(12, 27000, "liion")
    correction_factor = 0.72
    sonuc = menzil2.BauersfeldMenzilHesaplayici(
        hover_power_w,
        correction_factor,
        battery_wh,
        profile["mass_kg"],
        450.0,
        profile["prop_diameter_inch"],
        profile["num_rotors"],
    ).solve()
    return profile, sonuc, hover_power_w, battery_wh, correction_factor


def build_july3_suite():
    profile, sonuc, hover_power_w, battery_wh, correction_factor = firfir_context()
    return menzil2.build_datalink_fitted_model_suite(
        profile,
        sonuc,
        hover_power_w,
        battery_wh,
        correction_factor,
        log_root=JULY3_ROOT,
        date_hint="260703",
    )


def log_time_to_utc(span, time_s):
    return span["first_utc"] + timedelta(seconds=time_s - span["first_timeus_s"])


def build_july21_joined_samples(july3_power_reference_w):
    span, _params, series = july21.read_log()
    flight_start, flight_end = july21.identify_long_flight(series)
    laps = july21.build_laps(series, flight_start, flight_end)
    uninterrupted = [lap for lap in laps if lap["mission_items"] == [2, 3, 4, 5]]
    if len(uninterrupted) != 10:
        raise RuntimeError(f"Beklenen 10 kesintisiz tur yerine {len(uninterrupted)} tur bulundu")

    clean_start_utc = log_time_to_utc(span, uninterrupted[0]["start_t"])
    clean_end_utc = log_time_to_utc(span, uninterrupted[-1]["end_t"])
    flight_start_utc = log_time_to_utc(span, flight_start)
    flight_end_utc = log_time_to_utc(span, flight_end)

    datalink_raw, file_stats = july21.read_datalink()
    datalink_corrected = []
    for row in datalink_raw:
        item = dict(row)
        item["timestamp_utc"] = row["timestamp_utc"] - timedelta(
            seconds=JULY21_DATALINK_CLOCK_AHEAD_S
        )
        datalink_corrected.append(item)
    datalink_corrected.sort(key=lambda row: row["timestamp_utc"])

    flight_samples = menzil2.read_ardupilot_flight_samples(
        july21.BIN_PATH,
        start_utc=flight_start_utc,
        end_utc=flight_end_utc,
    )
    joined = menzil2.join_datalink_and_flight_samples(
        datalink_corrected,
        flight_samples,
        july3_power_reference_w,
        max_dt_s=0.35,
    )
    joined = menzil2.annotate_joined_sample_stability(joined)
    for row in joined:
        if clean_start_utc <= row["timestamp_utc"] <= clean_end_utc:
            row["validation_phase"] = "ilk_10_kesintisiz_tur"
        elif clean_end_utc < row["timestamp_utc"] <= flight_end_utc:
            row["validation_phase"] = "pilot_mudahalesi_sonrasi"
        else:
            row["validation_phase"] = "gorev_disi"

    metadata = {
        "bin": july21.BIN_PATH.name,
        "datalink_session": july21.DL_SESSION.name,
        "clock_correction_s": -JULY21_DATALINK_CLOCK_AHEAD_S,
        "file_stats": file_stats,
        "flight_start_utc": flight_start_utc.isoformat(),
        "flight_end_utc": flight_end_utc.isoformat(),
        "clean_start_utc": clean_start_utc.isoformat(),
        "clean_end_utc": clean_end_utc.isoformat(),
        "joined_sample_count": len(joined),
    }
    return joined, metadata


def validation_observations(samples, phase, power_reference_w):
    selected = [
        row
        for row in samples
        if row.get("validation_phase") == phase
        and 2.0 <= row.get("speed_ms", -1.0) <= 20.0
    ]
    return menzil2.build_datalink_speed_observations(
        selected,
        min_speed_ms=2.0,
        max_speed_ms=20.0,
        bin_width_ms=1.0,
        min_samples=80,
        power_reference_w=power_reference_w,
        stable_only=True,
        min_stable_fraction=0.5,
        extrapolation_start_ms=None,
    )


def validation_rows(observations_by_phase, model_functions, vehicle_hover_power_w):
    rows = []
    for phase, observations in observations_by_phase.items():
        for obs in observations:
            row = {
                "phase": phase,
                "speed_ms": obs["speed_ms"],
                "sample_count": obs["sample_count"],
                "stable_fraction": obs["stable_fraction"],
                "measured_ratio": obs["power_ratio"],
                "measured_vehicle_power_w": obs["power_ratio"] * vehicle_hover_power_w,
                "measured_single_arm_power_w": obs["power_w"],
                "voltage_note": "DataLink voltage is retained in raw joined samples",
            }
            for name, model_fn in model_functions.items():
                predicted_ratio = model_fn(obs["speed_ms"])
                row[f"{name}_predicted_ratio"] = predicted_ratio
                row[f"{name}_predicted_vehicle_power_w"] = (
                    predicted_ratio * vehicle_hover_power_w
                )
                row[f"{name}_residual_percent"] = 100.0 * (
                    obs["power_ratio"] / predicted_ratio - 1.0
                )
            rows.append(row)
    return rows


def raw_plot_samples(samples, phase, stride=20):
    selected = [
        row
        for row in samples
        if row.get("validation_phase") == phase
        and row.get("stable")
        and 2.0 <= row.get("speed_ms", -1.0) <= 20.0
        and 0.2 <= row.get("power_ratio", -1.0) <= 3.5
    ]
    return selected[::stride]


def plot_ratio(suite, samples, observations_by_phase, output_path):
    speeds = [value / 10.0 for value in range(20, 201)]
    fig, ax = plt.subplots(figsize=(12.5, 7.2))

    for name, model_fn in suite["model_functions"].items():
        ax.plot(
            speeds,
            [model_fn(speed) for speed in speeds],
            color=MODEL_COLORS[name],
            linewidth=2.0,
            label=MODEL_LABELS[name],
        )

    july3_obs = suite["observations"]
    ax.scatter(
        [row["speed_ms"] for row in july3_obs],
        [row["power_ratio"] for row in july3_obs],
        marker="o",
        s=50,
        facecolor="black",
        edgecolor="white",
        linewidth=0.7,
        zorder=6,
        label="3 Temmuz fit noktaları",
    )

    phase_style = {
        "ilk_10_kesintisiz_tur": ("#e67e22", "D", "21 Temmuz — ilk 10 kesintisiz tur"),
        "pilot_mudahalesi_sonrasi": ("#c0392b", "X", "21 Temmuz — müdahale sonrası"),
    }
    for phase, (color, marker, label) in phase_style.items():
        raw = raw_plot_samples(samples, phase)
        ax.scatter(
            [row["speed_ms"] for row in raw],
            [row["power_ratio"] for row in raw],
            s=9,
            color=color,
            alpha=0.10,
            linewidth=0,
            zorder=2,
        )
        observations = observations_by_phase[phase]
        ax.scatter(
            [row["speed_ms"] for row in observations],
            [row["power_ratio"] for row in observations],
            marker=marker,
            s=72,
            facecolor=color,
            edgecolor="white",
            linewidth=0.8,
            zorder=7,
            label=label,
        )

    ax.axvline(12.5, color="#777777", linestyle=":", linewidth=1.2, label="3 Temmuz ölçüm üst bölgesi")
    ax.set_title("3 Temmuz menzil2 fitleri üzerinde 21 Temmuz doğrulama noktaları")
    ax.set_xlabel("Yer hızı (m/s)")
    ax.set_ylabel("P / P_hover")
    ax.set_xlim(2.0, 20.0)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8.5, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def plot_vehicle_power(suite, observations_by_phase, output_path):
    speeds = [value / 10.0 for value in range(20, 201)]
    vehicle_hover_power_w = suite["vehicle_measured_hover_power_w"]
    fig, ax = plt.subplots(figsize=(12.5, 7.2))

    for name, model_fn in suite["model_functions"].items():
        ax.plot(
            speeds,
            [model_fn(speed) * vehicle_hover_power_w for speed in speeds],
            color=MODEL_COLORS[name],
            linewidth=2.0,
            label=MODEL_LABELS[name],
        )

    july3_obs = suite["observations"]
    ax.scatter(
        [row["speed_ms"] for row in july3_obs],
        [row["power_ratio"] * vehicle_hover_power_w for row in july3_obs],
        marker="o",
        s=50,
        facecolor="black",
        edgecolor="white",
        linewidth=0.7,
        zorder=6,
        label="3 Temmuz fit noktaları",
    )

    phase_style = {
        "ilk_10_kesintisiz_tur": ("#e67e22", "D", "21 Temmuz — ilk 10 kesintisiz tur"),
        "pilot_mudahalesi_sonrasi": ("#c0392b", "X", "21 Temmuz — müdahale sonrası"),
    }
    for phase, (color, marker, label) in phase_style.items():
        observations = observations_by_phase[phase]
        ax.scatter(
            [row["speed_ms"] for row in observations],
            [row["power_ratio"] * vehicle_hover_power_w for row in observations],
            marker=marker,
            s=72,
            facecolor=color,
            edgecolor="white",
            linewidth=0.8,
            zorder=7,
            label=label,
        )

    ax.axvline(12.5, color="#777777", linestyle=":", linewidth=1.2)
    ax.set_title("3 Temmuz fitleri ve 21 Temmuz ölçülen araç gücü")
    ax.set_xlabel("Yer hızı (m/s)")
    ax.set_ylabel("Araç gücü (W, 6S2P eşdeğeri)")
    ax.set_xlim(2.0, 20.0)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8.5, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize_residuals(rows, model_names):
    result = {}
    for phase in sorted({row["phase"] for row in rows}):
        phase_rows = [row for row in rows if row["phase"] == phase]
        result[phase] = {
            "bin_count": len(phase_rows),
            "speed_min_ms": min(row["speed_ms"] for row in phase_rows),
            "speed_max_ms": max(row["speed_ms"] for row in phase_rows),
            "models": {},
        }
        for name in model_names:
            residuals = [row[f"{name}_residual_percent"] for row in phase_rows]
            result[phase]["models"][name] = {
                "median_residual_percent": statistics.median(residuals),
                "mean_absolute_residual_percent": statistics.fmean(abs(value) for value in residuals),
                "max_absolute_residual_percent": max(abs(value) for value in residuals),
            }
    return result


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    suite = build_july3_suite()
    power_reference_w = suite["power_reference_w"]
    vehicle_hover_power_w = suite["vehicle_measured_hover_power_w"]
    if not power_reference_w or not vehicle_hover_power_w:
        raise RuntimeError("3 Temmuz hover güç referansı üretilemedi")

    samples, metadata = build_july21_joined_samples(power_reference_w)
    observations_by_phase = {
        phase: validation_observations(samples, phase, power_reference_w)
        for phase in ("ilk_10_kesintisiz_tur", "pilot_mudahalesi_sonrasi")
    }
    rows = validation_rows(
        observations_by_phase,
        suite["model_functions"],
        vehicle_hover_power_w,
    )
    residual_summary = summarize_residuals(rows, suite["model_functions"])

    ratio_graph = OUTPUT_DIR / "july3_fit_uzerinde_july21_noktalari.png"
    power_graph = OUTPUT_DIR / "july3_fit_uzerinde_july21_arac_gucu.png"
    plot_ratio(suite, samples, observations_by_phase, ratio_graph)
    plot_vehicle_power(suite, observations_by_phase, power_graph)
    write_csv(OUTPUT_DIR / "july21_validation_hiz_binleri.csv", rows)

    july3_rows = [
        {
            "speed_ms": row["speed_ms"],
            "power_ratio": row["power_ratio"],
            "single_arm_power_w": row["power_w"],
            "vehicle_power_w": row["power_ratio"] * vehicle_hover_power_w,
            "sample_count": row["sample_count"],
            "source_bins": ";".join(row.get("source_bins", [])),
            "source_sessions": ";".join(row.get("source_sessions", [])),
        }
        for row in suite["observations"]
    ]
    write_csv(OUTPUT_DIR / "july3_fit_hiz_binleri.csv", july3_rows)

    summary = {
        "purpose": "3 Temmuz fitleri sabit tutularak 21 Temmuz noktalarının dış doğrulaması",
        "july3_root": str(JULY3_ROOT),
        "july21_root": str(JULY21_ROOT),
        "july3_power_reference_single_arm_w": power_reference_w,
        "july3_vehicle_hover_power_w": vehicle_hover_power_w,
        "july3_fit_observation_count": len(suite["observations"]),
        "july21": metadata,
        "validation_residuals": residual_summary,
        "outputs": {
            "ratio_graph": str(ratio_graph),
            "power_graph": str(power_graph),
            "validation_csv": str(OUTPUT_DIR / "july21_validation_hiz_binleri.csv"),
            "july3_csv": str(OUTPUT_DIR / "july3_fit_hiz_binleri.csv"),
        },
        "important": [
            "21 Temmuz noktaları fit katsayılarını değiştirmez.",
            "21 Temmuz DataLink timestamp değerlerinden 56.18 saniye çıkarılmıştır.",
            "Tur 1-10 ve pilot müdahalesi sonrası ayrı doğrulama gruplarıdır.",
            "Güç grafiğinde tek-kol DataLink gücü 6S2P araç eşdeğeri için ikiyle çarpılmıştır.",
        ],
    }
    (OUTPUT_DIR / "karsilastirma_ozeti.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "calistirma_hatasi.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
        raise
