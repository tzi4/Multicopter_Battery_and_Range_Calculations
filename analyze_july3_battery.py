from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import fitz
import numpy as np
from pymavlink import mavutil

import menzil2


ROOT = Path(__file__).resolve().parent
LOG_ROOT = next(path for path in ROOT.iterdir() if path.is_dir() and path.name.startswith("3 Temmuz"))
BIN_PATHS = sorted(LOG_ROOT.glob("*.BIN"))
DATASHEET = Path(
    r"D:\Takım\itünom ikinci sene\Suas Batarya Seçimi\Konino Test\datahseets\PL9887187-27Ah DATASHEET.pdf"
)
OUT_DIR = ROOT / "analysis_outputs" / "july3_battery"


def pct(values, p):
    values = [value for value in values if value is not None and math.isfinite(value)]
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), p))


def med(values):
    values = [value for value in values if value is not None and math.isfinite(value)]
    return statistics.median(values) if values else None


def mean(values):
    values = [value for value in values if value is not None and math.isfinite(value)]
    return statistics.fmean(values) if values else None


def gps_week_ms_to_utc(week, ms):
    gps_epoch = datetime(1980, 1, 6, tzinfo=timezone.utc)
    return gps_epoch + timedelta(weeks=week, milliseconds=ms - 18_000)


def get_time_anchor(bin_path: Path):
    log = mavutil.mavlink_connection(str(bin_path), robust_parsing=True)
    while True:
        msg = log.recv_match(type="GPS", blocking=False)
        if msg is None:
            break
        data = msg.to_dict()
        if data.get("GWk") and data.get("GMS") and "TimeUS" in data:
            return {
                "timeus_s": data["TimeUS"] / 1e6,
                "utc": gps_week_ms_to_utc(data["GWk"], data["GMS"]),
            }
    return None


def utc_from_timeus(anchor, timeus):
    if not anchor or timeus is None:
        return None
    return anchor["utc"] + timedelta(seconds=timeus / 1e6 - anchor["timeus_s"])


def inspect_types(bin_path: Path, limit=None):
    log = mavutil.mavlink_connection(str(bin_path), robust_parsing=True)
    counts = Counter()
    fields = {}
    n = 0
    while True:
        msg = log.recv_match(blocking=False)
        if msg is None:
            break
        typ = msg.get_type()
        counts[typ] += 1
        if typ not in fields:
            fields[typ] = sorted(msg.to_dict().keys())
        n += 1
        if limit and n >= limit:
            break
    return counts, fields


def read_series(bin_path: Path):
    anchor = get_time_anchor(bin_path)
    series = {
        "BARO": [],
        "BAT": [],
        "XKF1": [],
        "GPS": [],
        "MODE": [],
    }
    log = mavutil.mavlink_connection(str(bin_path), robust_parsing=True)
    while True:
        msg = log.recv_match(blocking=False)
        if msg is None:
            break
        typ = msg.get_type()
        if typ not in series:
            continue
        data = msg.to_dict()
        t = data.get("TimeUS")
        timestamp_utc = utc_from_timeus(anchor, t)
        if typ == "BARO":
            series["BARO"].append({
                "time_s": t / 1e6 if t is not None else None,
                "timestamp_utc": timestamp_utc,
                "alt": data.get("Alt"),
                "press": data.get("Press"),
                "temp": data.get("Temp"),
                "cr_t": data.get("CRt"),
                "sms": data.get("SMS"),
                "offset": data.get("Offset"),
                "gnd_temp": data.get("GndTemp"),
                "health": data.get("Health"),
            })
        elif typ == "BAT" and data.get("Inst", 0) == 0:
            series["BAT"].append({
                "time_s": t / 1e6 if t is not None else None,
                "timestamp_utc": timestamp_utc,
                "volt": data.get("Volt"),
                "voltr": data.get("VoltR"),
                "curr": data.get("Curr"),
                "currtot": data.get("CurrTot"),
                "enrgtot": data.get("EnrgTot"),
                "rempct": data.get("RemPct"),
                "res": data.get("Res"),
            })
        elif typ == "XKF1" and data.get("C", 0) == 0:
            vn = data.get("VN", 0.0) or 0.0
            ve = data.get("VE", 0.0) or 0.0
            vd = data.get("VD", 0.0) or 0.0
            series["XKF1"].append({
                "time_s": t / 1e6 if t is not None else None,
                "timestamp_utc": timestamp_utc,
                "speed_ms": math.hypot(vn, ve),
                "vn": vn,
                "ve": ve,
                "vertical_speed_ms": -vd,
                "altitude_m": -(data.get("PD", 0.0) or 0.0),
                "roll_deg": data.get("Roll"),
                "pitch_deg": data.get("Pitch"),
                "yaw_deg": data.get("Yaw"),
            })
        elif typ == "GPS":
            series["GPS"].append({
                "time_s": t / 1e6 if t is not None else None,
                "timestamp_utc": timestamp_utc,
                "alt": data.get("Alt"),
                "spd": data.get("Spd"),
                "gms": data.get("GMS"),
                "gwk": data.get("GWk"),
                "status": data.get("Status"),
            })
        elif typ == "MODE":
            series["MODE"].append({
                "time_s": t / 1e6 if t is not None else None,
                "timestamp_utc": timestamp_utc,
                "mode": data.get("Mode"),
                "mode_num": data.get("ModeNum"),
                "rson": data.get("Rsn"),
            })
    return anchor, series


def smooth(values, window):
    if not values:
        return []
    arr = np.asarray(values, dtype=float)
    if window <= 1 or len(arr) < window:
        return arr.tolist()
    kernel = np.ones(window, dtype=float) / float(window)
    padded = np.pad(arr, (window // 2, window - 1 - window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid").tolist()


def baro_airborne_segment(baro_rows):
    valid = [
        row for row in baro_rows
        if row.get("time_s") is not None and row.get("alt") is not None and math.isfinite(row["alt"])
    ]
    if len(valid) < 20:
        return None
    times = [row["time_s"] for row in valid]
    alts = [row["alt"] for row in valid]
    ground_alt = pct(alts[: min(300, len(alts))], 10)
    rel = [alt - ground_alt for alt in alts]
    smoothed = smooth(rel, 51)

    # A barometer-only airborne mask. The threshold is intentionally low; later
    # duration checks use the longest continuous island and not the ARM state.
    mask = [value > 1.5 for value in smoothed]
    segments = []
    start_idx = None
    for idx, is_air in enumerate(mask):
        if is_air and start_idx is None:
            start_idx = idx
        elif not is_air and start_idx is not None:
            end_idx = idx - 1
            if times[end_idx] - times[start_idx] > 30:
                segments.append((start_idx, end_idx))
            start_idx = None
    if start_idx is not None:
        end_idx = len(mask) - 1
        if times[end_idx] - times[start_idx] > 30:
            segments.append((start_idx, end_idx))
    if not segments:
        return None
    start_idx, end_idx = max(segments, key=lambda item: times[item[1]] - times[item[0]])
    start_time = times[start_idx]
    end_time = times[end_idx]
    rel_slice = rel[start_idx:end_idx + 1]
    return {
        "start_time_s": start_time,
        "end_time_s": end_time,
        "duration_s": end_time - start_time,
        "ground_alt_m": ground_alt,
        "max_rel_alt_m": max(rel_slice),
        "median_rel_alt_m": med(rel_slice),
        "start_rel_alt_m": rel[start_idx],
        "end_rel_alt_m": rel[end_idx],
        "segments": [
            {
                "start_time_s": times[s],
                "end_time_s": times[e],
                "duration_s": times[e] - times[s],
                "max_rel_alt_m": max(rel[s:e + 1]),
            }
            for s, e in segments
        ],
    }


def filter_time(rows, start_s, end_s):
    return [
        row for row in rows
        if row.get("time_s") is not None and start_s <= row["time_s"] <= end_s
    ]


def integrate_power_rows(rows, power_key="power_w", max_dt_s=1.0):
    rows = [row for row in sorted(rows, key=lambda item: item["timestamp_utc"] or datetime.min.replace(tzinfo=timezone.utc))
            if row.get(power_key) is not None and math.isfinite(row[power_key])]
    total_wh = 0.0
    duration_s = 0.0
    for prev, cur in zip(rows, rows[1:]):
        if prev.get("timestamp_utc") is None or cur.get("timestamp_utc") is None:
            continue
        dt = (cur["timestamp_utc"] - prev["timestamp_utc"]).total_seconds()
        if 0 < dt <= max_dt_s:
            total_wh += 0.5 * (prev[power_key] + cur[power_key]) * dt / 3600.0
            duration_s += dt
    avg_power = total_wh * 3600.0 / duration_s if duration_s > 0 else None
    return total_wh, duration_s, avg_power


def integrate_power_current_chunks(rows, max_dt_s=1.0, split_gap_s=60.0):
    rows = [
        row for row in sorted(rows, key=lambda item: item["timestamp_utc"])
        if row.get("timestamp_utc")
        and row.get("power_w") is not None
        and row.get("current_total_a") is not None
        and math.isfinite(row["power_w"])
        and math.isfinite(row["current_total_a"])
    ]
    chunks = []
    current = []
    for row in rows:
        if current:
            dt = (row["timestamp_utc"] - current[-1]["timestamp_utc"]).total_seconds()
            if dt > split_gap_s:
                chunks.append(current)
                current = []
        current.append(row)
    if current:
        chunks.append(current)

    summaries = []
    total_wh = 0.0
    total_ah = 0.0
    total_duration_s = 0.0
    for chunk in chunks:
        wh = 0.0
        ah = 0.0
        duration_s = 0.0
        for prev, cur in zip(chunk, chunk[1:]):
            dt = (cur["timestamp_utc"] - prev["timestamp_utc"]).total_seconds()
            if 0 < dt <= max_dt_s:
                wh += 0.5 * (prev["power_w"] + cur["power_w"]) * dt / 3600.0
                ah += 0.5 * (prev["current_total_a"] + cur["current_total_a"]) * dt / 3600.0
                duration_s += dt
        speeds = [row["speed_ms"] for row in chunk]
        currents = [row["current_total_a"] for row in chunk]
        voltages = [row["voltage_v"] for row in chunk]
        powers = [row["power_w"] for row in chunk]
        summary = {
            "start_utc": chunk[0]["timestamp_utc"].isoformat(),
            "end_utc": chunk[-1]["timestamp_utc"].isoformat(),
            "duration_s": duration_s,
            "energy_wh": wh,
            "capacity_ah": ah,
            "avg_power_w": wh * 3600.0 / duration_s if duration_s > 0 else None,
            "avg_current_a": ah * 3600.0 / duration_s if duration_s > 0 else None,
            "median_speed_ms": med(speeds),
            "median_current_a": med(currents),
            "median_voltage_v": med(voltages),
            "median_power_w": med(powers),
            "sample_count": len(chunk),
        }
        summaries.append(summary)
        total_wh += wh
        total_ah += ah
        total_duration_s += duration_s
    return {
        "total_energy_wh": total_wh,
        "total_capacity_ah": total_ah,
        "total_duration_s": total_duration_s,
        "avg_power_w": total_wh * 3600.0 / total_duration_s if total_duration_s > 0 else None,
        "avg_current_a": total_ah * 3600.0 / total_duration_s if total_duration_s > 0 else None,
        "chunks": summaries,
    }


def gap_aware_baro_segments(baro_rows, rel_alt_threshold_m=1.5, max_gap_s=5.0):
    valid = [
        row for row in baro_rows
        if row.get("time_s") is not None and row.get("alt") is not None and math.isfinite(row["alt"])
    ]
    if len(valid) < 20:
        return {"ground_alt_m": None, "segments": [], "total_duration_s": 0.0}
    ground_alt = pct([row["alt"] for row in valid[: min(300, len(valid))]], 10)
    segments = []
    start_idx = None
    prev_idx = None
    for idx, row in enumerate(valid):
        if prev_idx is not None:
            gap = row["time_s"] - valid[prev_idx]["time_s"]
            if gap > max_gap_s and start_idx is not None:
                end_idx = prev_idx
                if valid[end_idx]["time_s"] - valid[start_idx]["time_s"] > 30:
                    segments.append((start_idx, end_idx))
                start_idx = None
        is_air = row["alt"] - ground_alt > rel_alt_threshold_m
        if is_air and start_idx is None:
            start_idx = idx
        elif not is_air and start_idx is not None:
            end_idx = idx - 1
            if valid[end_idx]["time_s"] - valid[start_idx]["time_s"] > 30:
                segments.append((start_idx, end_idx))
            start_idx = None
        prev_idx = idx
    if start_idx is not None:
        end_idx = len(valid) - 1
        if valid[end_idx]["time_s"] - valid[start_idx]["time_s"] > 30:
            segments.append((start_idx, end_idx))

    rows = []
    for start_idx, end_idx in segments:
        chunk = valid[start_idx:end_idx + 1]
        duration_s = chunk[-1]["time_s"] - chunk[0]["time_s"]
        rows.append({
            "start_utc": chunk[0]["timestamp_utc"].isoformat() if chunk[0].get("timestamp_utc") else None,
            "end_utc": chunk[-1]["timestamp_utc"].isoformat() if chunk[-1].get("timestamp_utc") else None,
            "start_time_s": chunk[0]["time_s"],
            "end_time_s": chunk[-1]["time_s"],
            "duration_s": duration_s,
            "max_rel_alt_m": max(row["alt"] - ground_alt for row in chunk),
            "median_rel_alt_m": med(row["alt"] - ground_alt for row in chunk),
        })
    return {
        "ground_alt_m": ground_alt,
        "rel_alt_threshold_m": rel_alt_threshold_m,
        "max_gap_s": max_gap_s,
        "segments": rows,
        "total_duration_s": sum(row["duration_s"] for row in rows),
    }


def nearest_rows_by_time(left_rows, right_rows, max_dt_s=0.35):
    if not left_rows or not right_rows:
        return []
    right = sorted([row for row in right_rows if row.get("timestamp_utc")], key=lambda row: row["timestamp_utc"])
    joined = []
    idx = 0
    for left in sorted([row for row in left_rows if row.get("timestamp_utc")], key=lambda row: row["timestamp_utc"]):
        t = left["timestamp_utc"]
        while idx + 1 < len(right) and right[idx + 1]["timestamp_utc"] <= t:
            idx += 1
        candidates = [right[idx]]
        if idx + 1 < len(right):
            candidates.append(right[idx + 1])
        nearest = min(candidates, key=lambda row: abs((row["timestamp_utc"] - t).total_seconds()))
        dt = abs((nearest["timestamp_utc"] - t).total_seconds())
        if dt <= max_dt_s:
            joined.append((left, nearest, dt))
    return joined


def summarize_batt(rows):
    rows = [row for row in rows if row.get("timestamp_utc")]
    if not rows:
        return {}
    voltages = [row["volt"] for row in rows if row.get("volt") is not None]
    voltrs = [row["voltr"] for row in rows if row.get("voltr") is not None]
    currents = [row["curr"] for row in rows if row.get("curr") is not None]
    currtots = [row["currtot"] for row in rows if row.get("currtot") is not None]
    enrgs = [row["enrgtot"] for row in rows if row.get("enrgtot") is not None]
    return {
        "rows": len(rows),
        "start_utc": rows[0]["timestamp_utc"].isoformat(),
        "end_utc": rows[-1]["timestamp_utc"].isoformat(),
        "duration_s": (rows[-1]["timestamp_utc"] - rows[0]["timestamp_utc"]).total_seconds(),
        "volt_start": voltages[0] if voltages else None,
        "volt_end": voltages[-1] if voltages else None,
        "volt_min": min(voltages) if voltages else None,
        "volt_mean": mean(voltages),
        "voltr_start": voltrs[0] if voltrs else None,
        "voltr_end": voltrs[-1] if voltrs else None,
        "voltr_min": min(voltrs) if voltrs else None,
        "voltr_mean": mean(voltrs),
        "curr_median": med(currents),
        "curr_mean": mean(currents),
        "currtot_delta": currtots[-1] - currtots[0] if len(currtots) >= 2 else None,
        "enrgtot_delta": enrgs[-1] - enrgs[0] if len(enrgs) >= 2 else None,
        "rempct_start": rows[0].get("rempct"),
        "rempct_end": rows[-1].get("rempct"),
    }


def datasheet_text():
    doc = fitz.open(str(DATASHEET))
    pages = []
    for idx, page in enumerate(doc):
        text = page.get_text("text")
        pages.append({"page": idx + 1, "text": text})
    return pages


def render_datasheet_first_page():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(DATASHEET))
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    out = OUT_DIR / "datasheet_page1.png"
    pix.save(str(out))
    return out


def build_datalink_result():
    profile = menzil2.build_speed_model_profile("1", 12.4, 4, 29.0, 450.0)
    hover_power_static = (
        menzil2.get_power_from_thrust(12400.0 / 4.0, menzil2.u8lite_kv190_g29_data)
        * 4.0
    )
    battery_wh_model = menzil2.calculate_real_energy_wh(12, 27000, "liion")
    correction_factor = 0.72
    sonuc = menzil2.BauersfeldMenzilHesaplayici(
        hover_power_static,
        correction_factor,
        battery_wh_model,
        profile["mass_kg"],
        450.0,
        profile["prop_diameter_inch"],
        profile["num_rotors"],
    ).solve()
    result = menzil2.run_datalink_measured_curve_analysis(
        profile,
        sonuc,
        hover_power_static,
        battery_wh_model,
        correction_factor,
        log_root=LOG_ROOT,
        date_hint="260703",
        make_graph=False,
    )
    return profile, hover_power_static, battery_wh_model, correction_factor, result


def collect_joined_for_fit(profile, hover_power_w, log_root=LOG_ROOT, date_hint="260703",
                           timestamp_mode="filename_trt"):
    datalink_root = log_root / "Datalink"
    normalized_date_hint = menzil2.normalize_datalink_date_hint(date_hint)
    sessions = menzil2.find_datalink_session_dirs(datalink_root)
    sessions = menzil2.filter_datalink_sessions_by_date_hint(sessions, normalized_date_hint)
    bin_spans = [menzil2.read_ardupilot_bin_time_span(path) for path in sorted(log_root.glob("*.BIN"))]
    overlaps = menzil2.find_datalink_bin_overlaps(sessions, bin_spans, min_overlap_s=30.0)
    joined_for_fit = []
    sync_report = []
    parsed_session_cache = {}
    for overlap in overlaps:
        cache_key = (overlap["session"]["name"], overlap["timestamp_mode"])
        if cache_key not in parsed_session_cache:
            parsed_session_cache[cache_key] = menzil2._parse_datalink_session_samples(
                overlap["session"],
                overlap["timestamp_mode"],
                profile["prop_diameter_inch"],
            )
        datalink_samples = [
            sample for sample in parsed_session_cache[cache_key]
            if overlap["start_utc"] <= sample["timestamp_utc"] <= overlap["end_utc"]
        ]
        flight_samples = menzil2.read_ardupilot_flight_samples(
            overlap["bin_span"]["path"],
            overlap["start_utc"],
            overlap["end_utc"],
        )
        joined = menzil2.join_datalink_and_flight_samples(datalink_samples, flight_samples, hover_power_w)
        accepted = bool(joined) and overlap["timestamp_mode"] == timestamp_mode
        if accepted:
            joined_for_fit.extend(joined)
        sync_report.append({
            "session": overlap["session"]["name"],
            "bin": Path(overlap["bin_span"]["path"]).name,
            "timestamp_mode": overlap["timestamp_mode"],
            "start_utc": overlap["start_utc"].isoformat(),
            "end_utc": overlap["end_utc"].isoformat(),
            "overlap_s": overlap["overlap_s"],
            "datalink_samples": len(datalink_samples),
            "flight_samples": len(flight_samples),
            "joined_samples": len(joined),
            "accepted_for_fit": accepted,
        })
    return menzil2.annotate_joined_sample_stability(joined_for_fit), sync_report


def summarize_joined_hover(joined_samples):
    stable = menzil2.annotate_joined_sample_stability(joined_samples)
    hover = [
        row for row in stable
        if row.get("stable")
        and row.get("speed_ms", 999) <= 1.5
        and abs(row.get("vertical_speed_ms", 999)) <= 0.5
        and abs(row.get("pitch_deg", 999)) <= 8
        and abs(row.get("roll_deg", 999)) <= 8
    ]
    low_speed = [
        row for row in stable
        if row.get("stable")
        and row.get("speed_ms", 999) <= 2.5
        and abs(row.get("vertical_speed_ms", 999)) <= 0.7
        and abs(row.get("pitch_deg", 999)) <= 10
        and abs(row.get("roll_deg", 999)) <= 10
    ]
    summaries = {}
    for name, rows in [("strict_hover", hover), ("low_speed_hover_like", low_speed), ("all_joined", stable)]:
        powers = [row["power_w"] for row in rows]
        summaries[name] = {
            "n": len(rows),
            "power_median_w": med(powers),
            "power_mean_w": mean(powers),
            "power_p10_w": pct(powers, 10),
            "power_p90_w": pct(powers, 90),
            "speed_median_ms": med(row["speed_ms"] for row in rows),
            "vertical_speed_median_ms": med(row["vertical_speed_ms"] for row in rows),
            "voltage_median_v": med(row["voltage_v"] for row in rows),
            "current_total_median_a": med(row["current_total_a"] for row in rows),
        }
    return summaries


def capacity_table(power_w, pack_wh_nominal, usable_fracs):
    rows = []
    for label, usable_frac in usable_fracs:
        usable_wh = pack_wh_nominal * usable_frac
        rows.append({
            "target_remaining": label,
            "usable_fraction": usable_frac,
            "usable_wh": usable_wh,
            "minutes": usable_wh / power_w * 60.0 if power_w and power_w > 0 else None,
        })
    return rows


def capacity_table_ah(current_a, pack_ah, usable_fracs):
    rows = []
    for label, usable_frac in usable_fracs:
        usable_ah = pack_ah * usable_frac
        rows.append({
            "target_remaining": label,
            "usable_fraction": usable_frac,
            "usable_ah": usable_ah,
            "minutes": usable_ah / current_a * 60.0 if current_a and current_a > 0 else None,
        })
    return rows


def write_csv(path: Path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rendered = render_datasheet_first_page()
    data = {
        "log_root": str(LOG_ROOT),
        "bin_paths": [str(path) for path in BIN_PATHS],
        "datasheet": str(DATASHEET),
        "datasheet_render_page1": str(rendered),
        "datasheet_text_pages": datasheet_text(),
        "bins": {},
    }

    for bin_path in BIN_PATHS:
        counts, fields = inspect_types(bin_path)
        anchor, series = read_series(bin_path)
        baro_seg = baro_airborne_segment(series["BARO"])
        bin_summary = {
            "size_bytes": bin_path.stat().st_size,
            "type_counts_top": counts.most_common(40),
            "fields": {key: fields.get(key) for key in ["BARO", "BAT", "XKF1", "GPS", "MODE"]},
            "time_anchor_utc": anchor["utc"].isoformat() if anchor else None,
            "time_anchor_timeus_s": anchor["timeus_s"] if anchor else None,
            "baro_airborne_segment": baro_seg,
            "series_counts": {key: len(value) for key, value in series.items()},
        }
        if baro_seg:
            start_s = baro_seg["start_time_s"]
            end_s = baro_seg["end_time_s"]
            bin_summary["batt_airborne"] = summarize_batt(filter_time(series["BAT"], start_s, end_s))
            bin_summary["xkf_airborne"] = {
                "rows": len(filter_time(series["XKF1"], start_s, end_s)),
                "speed_median_ms": med(row["speed_ms"] for row in filter_time(series["XKF1"], start_s, end_s)),
                "speed_p90_ms": pct([row["speed_ms"] for row in filter_time(series["XKF1"], start_s, end_s)], 90),
                "vertical_speed_abs_median_ms": med(abs(row["vertical_speed_ms"]) for row in filter_time(series["XKF1"], start_s, end_s)),
                "altitude_median_m": med(row["altitude_m"] for row in filter_time(series["XKF1"], start_s, end_s)),
            }
        bin_summary["baro_segments_gap_aware"] = gap_aware_baro_segments(series["BARO"])
        data["bins"][bin_path.name] = bin_summary

        write_csv(
            OUT_DIR / f"{bin_path.stem}_baro.csv",
            [
                {
                    **{k: v for k, v in row.items() if k != "timestamp_utc"},
                    "timestamp_utc": row["timestamp_utc"].isoformat() if row.get("timestamp_utc") else None,
                }
                for row in series["BARO"]
            ],
        )
        write_csv(
            OUT_DIR / f"{bin_path.stem}_bat.csv",
            [
                {
                    **{k: v for k, v in row.items() if k != "timestamp_utc"},
                    "timestamp_utc": row["timestamp_utc"].isoformat() if row.get("timestamp_utc") else None,
                }
                for row in series["BAT"]
            ],
        )

    profile, hover_power_static, battery_wh_model, correction_factor, dl_result = build_datalink_result()
    joined_for_fit, joined_sync_report = collect_joined_for_fit(profile, hover_power_static)
    joined_energy = integrate_power_current_chunks(joined_for_fit)
    data["firfir_context"] = {
        "profile": profile,
        "hover_power_static_w": hover_power_static,
        "menzil2_battery_wh_model": battery_wh_model,
        "menzil2_correction_factor_current": correction_factor,
    }
    data["datalink_measured"] = {
        "measured_hover_power_w": dl_result.get("measured_hover_power_w"),
        "power_reference_w": dl_result.get("power_reference_w"),
        "joined_sample_count": dl_result.get("joined_sample_count"),
        "sync_report": dl_result.get("sync_report"),
        "joined_rebuilt_sync_report": joined_sync_report,
        "battery_qc_report": {
            key: value for key, value in dl_result.get("battery_qc_report", {}).items()
            if key not in {"rows"}
        },
        "hover_summaries": summarize_joined_hover(joined_for_fit),
        "joined_energy_current": joined_energy,
        "speed_bin_observations": dl_result.get("speed_bin_observations"),
        "empirical_curve": dl_result.get("empirical_curve"),
    }

    # Capacity basis: the local flight notes identify the aircraft pack as
    # 6S 27 Ah nominal, with 25.2 Ah measured usable capacity to the practical
    # 3.36 V/cell anchor. The datasheet itself is a 3.7 V 27 Ah cell spec.
    measured_usable_ah = 25.2
    datasheet_nominal_ah = 27.0
    measured_usable_wh_3_7 = 6 * 3.7 * measured_usable_ah
    datasheet_nominal_wh_3_7 = 6 * 3.7 * datasheet_nominal_ah
    hover_candidates = data["datalink_measured"]["hover_summaries"]
    power_bases = {
        "datalink_measured_hover_power": data["datalink_measured"]["measured_hover_power_w"],
        "strict_hover_median_power": hover_candidates["strict_hover"]["power_median_w"],
        "low_speed_hover_like_median_power": hover_candidates["low_speed_hover_like"]["power_median_w"],
        "full_joined_mean_power": hover_candidates["all_joined"]["power_mean_w"],
    }
    current_bases = {
        "strict_hover_median_current": hover_candidates["strict_hover"]["current_total_median_a"],
        "low_speed_hover_like_median_current": hover_candidates["low_speed_hover_like"]["current_total_median_a"],
        "full_joined_mean_current": joined_energy["avg_current_a"],
    }
    usable_fracs = [
        ("20%", 0.80),
        ("10%", 0.90),
        ("5%", 0.95),
        ("0%", 1.00),
    ]
    data["endurance_tables"] = {}
    for name, power in power_bases.items():
        if not power:
            continue
        data["endurance_tables"][name] = {
            "power_w": power,
            "measured_usable_6s_25p2ah_wh": measured_usable_wh_3_7,
            "datasheet_nominal_6s_27ah_wh": datasheet_nominal_wh_3_7,
            "times_measured_usable_25p2ah": capacity_table(power, measured_usable_wh_3_7, usable_fracs),
            "times_datasheet_nominal_27ah": capacity_table(power, datasheet_nominal_wh_3_7, usable_fracs),
        }
    data["endurance_tables_ah"] = {}
    for name, current in current_bases.items():
        if not current:
            continue
        data["endurance_tables_ah"][name] = {
            "current_a": current,
            "times_measured_usable_25p2ah": capacity_table_ah(current, measured_usable_ah, usable_fracs),
            "times_datasheet_nominal_27ah": capacity_table_ah(current, datasheet_nominal_ah, usable_fracs),
        }

    total_baro_airborne_s = sum(
        value.get("baro_segments_gap_aware", {}).get("total_duration_s", 0.0)
        for value in data["bins"].values()
    )
    data["observed_datalink_energy"] = {
        "joined_integrated_wh": joined_energy["total_energy_wh"],
        "joined_integrated_ah": joined_energy["total_capacity_ah"],
        "integrated_duration_s": joined_energy["total_duration_s"],
        "gap_aware_baro_airborne_s": total_baro_airborne_s,
        "avg_power_w": joined_energy["avg_power_w"],
        "avg_current_a": joined_energy["avg_current_a"],
        "measured_usable_25p2ah_fraction_used_wh": joined_energy["total_energy_wh"] / measured_usable_wh_3_7,
        "measured_usable_25p2ah_fraction_used_ah": joined_energy["total_capacity_ah"] / measured_usable_ah,
        "datasheet_nominal_27ah_fraction_used_wh": joined_energy["total_energy_wh"] / datasheet_nominal_wh_3_7,
        "datasheet_nominal_27ah_fraction_used_ah": joined_energy["total_capacity_ah"] / datasheet_nominal_ah,
    }

    out_json = OUT_DIR / "july3_battery_analysis.json"
    out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({
        "output": str(out_json),
        "bins": {
            key: {
                "baro_airborne_duration_min": value.get("baro_airborne_segment", {}).get("duration_s", 0) / 60
                if value.get("baro_airborne_segment") else None,
                "batt_airborne": value.get("batt_airborne"),
            }
            for key, value in data["bins"].items()
        },
        "measured_hover_power_w": data["datalink_measured"]["measured_hover_power_w"],
        "hover_summaries": data["datalink_measured"]["hover_summaries"],
        "endurance_tables": data["endurance_tables"],
        "observed_datalink_energy": data["observed_datalink_energy"],
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
