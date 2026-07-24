from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pymavlink import mavutil

import menzil2


ROOT = Path(__file__).resolve().parent
LOG_ROOT = next(path for path in ROOT.iterdir() if path.is_dir() and path.name.startswith("21 temmuz"))
BIN_PATH = next(LOG_ROOT.glob("*11-56-15.bin"))
DL_SESSION = LOG_ROOT / "UART-260721-103715"
OUT_DIR = LOG_ROOT / "analiz_ciktilari"

AUTO_MODE = 3
TRT = timezone(timedelta(hours=3))
# DataLink bilgisayar saati, throttle (CTUN.ThO) ile toplam ESC akiminin
# capraz korelasyonuna gore autopilot GPS saatinden 56.18 s ileride.
DATALINK_CLOCK_AHEAD_S = 56.18
WANTED = {
    "ARM", "MODE", "MISE", "MSG", "ERR", "BAT", "MOTB", "CTUN", "ATT", "RATE",
    "PIDR", "PIDP", "PIDY", "RCOU", "VIBE", "GPS", "GPA", "POS", "XKF1", "XKF2",
    "XKF3", "XKF4", "XKF5", "MAG", "POWR", "BARO",
}


def finite(values):
    return [float(value) for value in values if value is not None and math.isfinite(float(value))]


def q(values, percentile):
    values = finite(values)
    return float(np.percentile(values, percentile)) if values else None


def avg(values):
    values = finite(values)
    return statistics.fmean(values) if values else None


def rms(values):
    values = finite(values)
    return math.sqrt(statistics.fmean(value * value for value in values)) if values else None


def wrap180(value):
    return (float(value) + 180.0) % 360.0 - 180.0


def local_clock(span, time_s):
    dt = span["first_utc"] + timedelta(seconds=time_s - span["first_timeus_s"])
    return dt.astimezone(TRT).strftime("%H:%M:%S.%f")[:-3]


def read_log():
    span = menzil2.read_ardupilot_bin_time_span(BIN_PATH)
    series = defaultdict(list)
    params = {}
    log = mavutil.mavlink_connection(str(BIN_PATH), robust_parsing=True)
    while True:
        msg = log.recv_match(blocking=False)
        if msg is None:
            break
        typ = msg.get_type()
        data = msg.to_dict()
        if typ == "PARM":
            params[data["Name"]] = data["Value"]
            continue
        if typ not in WANTED:
            continue
        if "TimeUS" in data:
            data["t"] = data["TimeUS"] / 1e6
        series[typ].append(data)
    return span, params, series


def read_datalink():
    samples = []
    file_stats = []
    for path in sorted(DL_SESSION.glob("*.udat")):
        parsed = menzil2.parse_datalink_udat_file(
            path,
            prop_diameter_inch=28.0,
            timestamp_mode="filename_trt",
        )
        file_stats.append({
            "file": path.name,
            "raw_records": parsed.get("raw_record_count", 0),
            "valid_records": parsed.get("record_count", 0),
            "sample_rate_hz": parsed.get("sample_rate_hz"),
            "voltage_median_v": parsed.get("voltage_median_v"),
            "power_median_w": parsed.get("power_median_w"),
            "rpm_median": parsed.get("rpm_median"),
        })
        samples.extend(parsed.get("samples", []))
    samples.sort(key=lambda row: row["timestamp_utc"])
    return samples, file_stats


def utc_to_log_time(span, timestamp_utc):
    return span["first_timeus_s"] + (timestamp_utc - span["first_utc"]).total_seconds()


def datalink_with_log_time(span, rows):
    result = []
    for row in rows:
        item = dict(row)
        item["t_raw_filename"] = utc_to_log_time(span, row["timestamp_utc"])
        item["t"] = item["t_raw_filename"] - DATALINK_CLOCK_AHEAD_S
        result.append(item)
    return result


def rows_between(rows, start_t, end_t, predicate=None):
    result = []
    for row in rows:
        t = row.get("t")
        if t is None or t < start_t or t > end_t:
            continue
        if predicate is None or predicate(row):
            result.append(row)
    return result


def nearest(rows, time_s, predicate=None):
    candidates = [row for row in rows if row.get("t") is not None and (predicate is None or predicate(row))]
    return min(candidates, key=lambda row: abs(row["t"] - time_s)) if candidates else None


def identify_long_flight(series):
    arms = series["ARM"]
    windows = []
    start = None
    for row in arms:
        if row.get("ArmState") == 1:
            start = row["t"]
        elif row.get("ArmState") == 0 and start is not None:
            windows.append((start, row["t"]))
            start = None
    return max(windows, key=lambda pair: pair[1] - pair[0])


def build_laps(series, flight_start, flight_end):
    mise = [row for row in series["MISE"] if flight_start <= row["t"] <= flight_end]
    starts = []
    for idx, row in enumerate(mise):
        if row.get("CNum") != 2:
            continue
        if not starts:
            starts.append(row)
            continue
        prev = mise[idx - 1] if idx else None
        if prev and prev.get("CNum") == 5 and row["t"] - prev["t"] < 25.0:
            starts.append(row)
    laps = []
    for idx, start in enumerate(starts):
        end_t = starts[idx + 1]["t"] if idx + 1 < len(starts) else flight_end
        events = [row for row in mise if start["t"] <= row["t"] < end_t]
        laps.append({
            "lap": idx + 1,
            "start_t": start["t"],
            "end_t": end_t,
            "mission_items": [row.get("CNum") for row in events],
        })
    return laps


def active_mode_intervals(series, start_t, end_t):
    modes = [row for row in series["MODE"] if start_t <= row["t"] <= end_t]
    result = []
    current = None
    for row in modes:
        if current is not None:
            current["end_t"] = row["t"]
            result.append(current)
        current = {"start_t": row["t"], "end_t": end_t, "mode": row.get("Mode")}
    if current is not None:
        result.append(current)
    return result


def summarize_window(series, datalink, start_t, end_t):
    bat = rows_between(series["BAT"], start_t, end_t, lambda r: r.get("Inst", 0) == 0)
    motb = rows_between(series["MOTB"], start_t, end_t)
    ctun = rows_between(series["CTUN"], start_t, end_t)
    att = rows_between(series["ATT"], start_t, end_t)
    rate = rows_between(series["RATE"], start_t, end_t)
    rcou = rows_between(series["RCOU"], start_t, end_t)
    vibe = rows_between(series["VIBE"], start_t, end_t, lambda r: r.get("IMU", 0) == 0)
    gps = rows_between(series["GPS"], start_t, end_t, lambda r: r.get("I", 0) == 0)
    gpa = rows_between(series["GPA"], start_t, end_t, lambda r: r.get("I", 0) == 0)
    xkf3 = rows_between(series["XKF3"], start_t, end_t, lambda r: r.get("C", 0) == 0)
    xkf4 = rows_between(series["XKF4"], start_t, end_t, lambda r: r.get("C", 0) == 0)
    dl = rows_between(datalink, start_t, end_t)

    att_error = [math.hypot(r.get("DesRoll", 0.0) - r.get("Roll", 0.0), r.get("DesPitch", 0.0) - r.get("Pitch", 0.0)) for r in att]
    attitude_tilt = [math.hypot(r.get("Roll", 0.0), r.get("Pitch", 0.0)) for r in att]
    yaw_error = [abs(wrap180(r.get("DesYaw", 0.0) - r.get("Yaw", 0.0))) for r in att]
    rate_error = [math.hypot(r.get("RDes", 0.0) - r.get("R", 0.0), r.get("PDes", 0.0) - r.get("P", 0.0)) for r in rate]
    motor_values = [[r.get(f"C{i}", float("nan")) for i in range(1, 5)] for r in rcou]
    motor_spread = [max(v) - min(v) for v in motor_values if all(math.isfinite(x) for x in v)]
    dl_spread_rpm = []
    dl_spread_current = []
    for row in dl:
        rpms = [motor["rpm"] for motor in row.get("motors", [])]
        currents = [motor["current_a"] for motor in row.get("motors", [])]
        if len(rpms) == 4:
            dl_spread_rpm.append(max(rpms) - min(rpms))
            dl_spread_current.append(max(currents) - min(currents))

    dl_resistance_mohm = None
    if len(dl) >= 20:
        dl_i = np.asarray([row["current_total_a"] for row in dl], dtype=float)
        dl_v = np.asarray([row["voltage_v"] for row in dl], dtype=float)
        if np.std(dl_i) > 2.0:
            slope = float(np.polyfit(dl_i, dl_v, 1)[0])
            dl_resistance_mohm = max(0.0, -slope * 1000.0)

    motor_specific = {}
    for motor_id in range(1, 5):
        motors = [
            motor
            for row in dl
            for motor in row.get("motors", [])
            if motor.get("motor_id") == motor_id
        ]
        motor_specific[f"m{motor_id}_current_max_a"] = q([motor.get("current_a") for motor in motors], 100)
        motor_specific[f"m{motor_id}_current_med_a"] = q([motor.get("current_a") for motor in motors], 50)
        motor_specific[f"m{motor_id}_rpm_min"] = q([motor.get("rpm") for motor in motors], 0)
        motor_specific[f"m{motor_id}_rpm_med"] = q([motor.get("rpm") for motor in motors], 50)

    return {
        "bat_v_min": q([r.get("Volt") for r in bat], 0),
        "bat_v_p05": q([r.get("Volt") for r in bat], 5),
        "bat_v_med": q([r.get("Volt") for r in bat], 50),
        "bat_v_restored_med": q([r.get("VoltR") for r in bat], 50),
        "dl_v_min": q([r.get("voltage_v") for r in dl], 0),
        "dl_v_med": q([r.get("voltage_v") for r in dl], 50),
        "dl_current_max_a": q([r.get("current_total_a") for r in dl], 100),
        "dl_current_med_a": q([r.get("current_total_a") for r in dl], 50),
        "dl_power_max_w": q([r.get("power_w") for r in dl], 100),
        "dl_power_med_w": q([r.get("power_w") for r in dl], 50),
        "dl_rpm_min": q([r.get("rpm_median") for r in dl], 0),
        "dl_rpm_med": q([r.get("rpm_median") for r in dl], 50),
        "dl_rpm_spread_p95": q(dl_spread_rpm, 95),
        "dl_current_spread_p95": q(dl_spread_current, 95),
        "dl_effective_r_mohm": dl_resistance_mohm,
        "alt_min_m": q([r.get("Alt") for r in ctun], 0),
        "alt_med_m": q([r.get("Alt") for r in ctun], 50),
        "alt_error_abs_max_m": q([abs((r.get("DAlt") or 0.0) - (r.get("Alt") or 0.0)) for r in ctun], 100),
        "climb_rate_min_ms": q([r.get("CRt") for r in ctun], 0),
        "throttle_med": q([r.get("ThO") for r in ctun], 50),
        "throttle_max": q([r.get("ThO") for r in ctun], 100),
        "motb_thlimit_max": q([r.get("ThLimit") for r in motb], 100),
        "motb_batvolt_med": q([r.get("BatVolt") for r in motb], 50),
        "motb_liftmax_min": q([r.get("LiftMax") for r in motb], 0),
        "att_err_p95_deg": q(att_error, 95),
        "att_err_max_deg": q(att_error, 100),
        "att_tilt_med_deg": q(attitude_tilt, 50),
        "att_tilt_p95_deg": q(attitude_tilt, 95),
        "yaw_err_p95_deg": q(yaw_error, 95),
        "rate_err_rms_dps": rms(rate_error),
        "motor_pwm_max": q([max(v) for v in motor_values if all(math.isfinite(x) for x in v)], 100),
        "motor_pwm_spread_p95": q(motor_spread, 95),
        "vibe_xyz_max_p95": q([max(r.get("VibeX", 0.0), r.get("VibeY", 0.0), r.get("VibeZ", 0.0)) for r in vibe], 95),
        "vibe_clip_max": q([r.get("Clip") for r in vibe], 100),
        "gps_speed_min_ms": q([r.get("Spd") for r in gps], 0),
        "gps_speed_med_ms": q([r.get("Spd") for r in gps], 50),
        "gps_nsats_min": q([r.get("NSats") for r in gps], 0),
        "gps_hdop_max": q([r.get("HDop") for r in gps], 100),
        "gps_hacc_max_m": q([r.get("HAcc") for r in gpa], 100),
        "ekf_pos_innov_p95": q([math.hypot(r.get("IPN", 0.0), r.get("IPE", 0.0)) for r in xkf3], 95),
        "ekf_vel_innov_p95": q([math.hypot(r.get("IVN", 0.0), r.get("IVE", 0.0)) for r in xkf3], 95),
        "ekf_yaw_innov_p95": q([abs(r.get("IYAW", 0.0)) for r in xkf3], 95),
        "ekf_pos_test_ratio_max": q([r.get("SP") for r in xkf4], 100),
        "ekf_vel_test_ratio_max": q([r.get("SV") for r in xkf4], 100),
        "motor_pwm_at_max_fraction": avg([
            1.0 if max(values) >= 1890.0 else 0.0
            for values in motor_values
            if all(math.isfinite(value) for value in values)
        ]),
        **motor_specific,
        "sample_counts": {"bat": len(bat), "datalink": len(dl), "gps": len(gps)},
    }


def integrate_datalink(rows, start_t, end_t):
    chosen = rows_between(rows, start_t, end_t)
    wh = ah = duration = 0.0
    for left, right in zip(chosen, chosen[1:]):
        dt = right["t"] - left["t"]
        if 0.0 < dt <= 0.2:
            wh += 0.5 * (left["power_w"] + right["power_w"]) * dt / 3600.0
            ah += 0.5 * (left["current_total_a"] + right["current_total_a"]) * dt / 3600.0
            duration += dt
    return {"energy_wh": wh, "capacity_ah": ah, "duration_s": duration}


def haversine_m(lat1, lon1, lat2, lon2):
    radius_m = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    term = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius_m * math.asin(math.sqrt(term))


def gps_distance_km(series, start_t, end_t):
    gps = rows_between(series["GPS"], start_t, end_t, lambda r: r.get("I", 0) == 0)
    distance_m = 0.0
    for left, right in zip(gps, gps[1:]):
        dt = right["t"] - left["t"]
        if not 0.0 < dt <= 1.0:
            continue
        step_m = haversine_m(left["Lat"], left["Lng"], right["Lat"], right["Lng"])
        if step_m <= 40.0 * dt + 2.0:
            distance_m += step_m
    return distance_m / 1000.0


def integrate_motor_ah(rows, start_t, end_t):
    chosen = rows_between(rows, start_t, end_t)
    result = {motor_id: 0.0 for motor_id in range(1, 5)}
    duration = 0.0
    for left, right in zip(chosen, chosen[1:]):
        dt = right["t"] - left["t"]
        if not 0.0 < dt <= 0.2:
            continue
        left_motors = {m["motor_id"]: m for m in left.get("motors", [])}
        right_motors = {m["motor_id"]: m for m in right.get("motors", [])}
        if not all(motor_id in left_motors and motor_id in right_motors for motor_id in range(1, 5)):
            continue
        for motor_id in range(1, 5):
            result[motor_id] += 0.5 * (
                left_motors[motor_id]["current_a"] + right_motors[motor_id]["current_a"]
            ) * dt / 3600.0
        duration += dt
    return result, duration


def motor_yaw_summary(series, datalink, start_t, end_t):
    dl = rows_between(datalink, start_t, end_t)
    att = rows_between(series["ATT"], start_t, end_t)
    rate = rows_between(series["RATE"], start_t, end_t)
    pidy = rows_between(series["PIDY"], start_t, end_t)
    rcou = rows_between(series["RCOU"], start_t, end_t)
    motor_ah, dl_duration = integrate_motor_ah(datalink, start_t, end_t)
    total_motor_ah = sum(motor_ah.values())
    command_samples = {motor_id: [] for motor_id in range(1, 5)}
    command_alignment_abs_dt = []
    rcou_idx = 0
    for dl_row in dl:
        while rcou_idx + 1 < len(rcou) and abs(rcou[rcou_idx + 1]["t"] - dl_row["t"]) <= abs(rcou[rcou_idx]["t"] - dl_row["t"]):
            rcou_idx += 1
        if not rcou or abs(rcou[rcou_idx]["t"] - dl_row["t"]) > 0.15:
            continue
        command_alignment_abs_dt.append(abs(rcou[rcou_idx]["t"] - dl_row["t"]))
        motors = {motor["motor_id"]: motor for motor in dl_row.get("motors", [])}
        for motor_id in range(1, 5):
            if motor_id not in motors:
                continue
            command_samples[motor_id].append({
                "pwm": rcou[rcou_idx].get(f"C{motor_id}"),
                "rpm": motors[motor_id].get("rpm"),
                "current_a": motors[motor_id].get("current_a"),
                "voltage_v": dl_row.get("voltage_v"),
            })

    result = {
        "start_t": start_t,
        "end_t": end_t,
        "duration_s": end_t - start_t,
        "datalink_integrated_duration_s": dl_duration,
        "yaw_error_p95_deg": q([
            abs(wrap180(row.get("DesYaw", 0.0) - row.get("Yaw", 0.0))) for row in att
        ], 95),
        "yaw_error_max_deg": q([
            abs(wrap180(row.get("DesYaw", 0.0) - row.get("Yaw", 0.0))) for row in att
        ], 100),
        "yaw_rate_error_rms_dps": rms([
            row.get("YDes", 0.0) - row.get("Y", 0.0) for row in rate
        ]),
        "yaw_output_abs_p95": q([abs(row.get("YOut", 0.0)) for row in rate], 95),
        "yaw_output_abs_max": q([abs(row.get("YOut", 0.0)) for row in rate], 100),
        "yaw_integrator_median": q([row.get("I", 0.0) for row in pidy], 50),
        "yaw_integrator_abs_p95": q([abs(row.get("I", 0.0)) for row in pidy], 95),
        "yaw_integrator_abs_max": q([abs(row.get("I", 0.0)) for row in pidy], 100),
        "yaw_pair_pwm_delta_median": q([
            0.5 * ((row.get("C1", 0.0) + row.get("C2", 0.0)) - (row.get("C3", 0.0) + row.get("C4", 0.0)))
            for row in rcou
        ], 50),
        "yaw_pair_pwm_delta_abs_p95": q([
            abs(0.5 * ((row.get("C1", 0.0) + row.get("C2", 0.0)) - (row.get("C3", 0.0) + row.get("C4", 0.0))))
            for row in rcou
        ], 95),
        "command_alignment_abs_dt_p50_s": q(command_alignment_abs_dt, 50),
        "command_alignment_abs_dt_p95_s": q(command_alignment_abs_dt, 95),
        "command_alignment_abs_dt_max_s": q(command_alignment_abs_dt, 100),
        "motors": {},
    }
    for motor_id in range(1, 5):
        motor_rows = [
            motor for row in dl for motor in row.get("motors", []) if motor.get("motor_id") == motor_id
        ]
        pwm = [row.get(f"C{motor_id}") for row in rcou]
        command_bins = {}
        for label, low, high in [
            ("1500_1699", 1500.0, 1700.0),
            ("1700_1799", 1700.0, 1800.0),
            ("1800_1889", 1800.0, 1890.0),
            ("1890_plus", 1890.0, 2000.0),
        ]:
            selected = [row for row in command_samples[motor_id] if low <= row["pwm"] < high]
            command_bins[label] = {
                "count": len(selected),
                "pwm_median": q([row["pwm"] for row in selected], 50),
                "voltage_median_v": q([row["voltage_v"] for row in selected], 50),
                "rpm_median": q([row["rpm"] for row in selected], 50),
                "current_median_a": q([row["current_a"] for row in selected], 50),
            }
        result["motors"][str(motor_id)] = {
            "current_mean_a_from_integral": motor_ah[motor_id] * 3600.0 / dl_duration if dl_duration else None,
            "current_median_a": q([row.get("current_a") for row in motor_rows], 50),
            "current_p95_a": q([row.get("current_a") for row in motor_rows], 95),
            "current_max_a": q([row.get("current_a") for row in motor_rows], 100),
            "integrated_ah": motor_ah[motor_id],
            "current_share_percent": 100.0 * motor_ah[motor_id] / total_motor_ah if total_motor_ah else None,
            "rpm_median": q([row.get("rpm") for row in motor_rows], 50),
            "rpm_p05": q([row.get("rpm") for row in motor_rows], 5),
            "rpm_max": q([row.get("rpm") for row in motor_rows], 100),
            "pwm_median": q(pwm, 50),
            "pwm_p95": q(pwm, 95),
            "pwm_max": q(pwm, 100),
            "pwm_at_max_fraction": avg([1.0 if value >= 1890.0 else 0.0 for value in finite(pwm)]),
            "command_response_bins": command_bins,
        }
    return result


def build_lap_energy_rows(series, datalink, laps):
    rows = []
    for lap in laps:
        integral = integrate_datalink(datalink, lap["start_t"], lap["end_t"])
        distance_km = gps_distance_km(series, lap["start_t"], lap["end_t"])
        nominal_percent = 100.0 * integral["capacity_ah"] / 27.0
        usable_percent = 100.0 * integral["capacity_ah"] / 25.2
        rows.append({
            "lap": lap["lap"],
            "complete_uninterrupted": lap["mission_items"] == [2, 3, 4, 5],
            "duration_s": lap["end_t"] - lap["start_t"],
            "distance_km": distance_km,
            "one_parallel_arm_ah": integral["capacity_ah"],
            "one_parallel_arm_wh": integral["energy_wh"],
            "estimated_full_pack_wh": 2.0 * integral["energy_wh"],
            "nominal_pack_percent": nominal_percent,
            "measured_usable_pack_percent": usable_percent,
            "nominal_percent_per_3_2km": nominal_percent * 3.2 / distance_km if distance_km else None,
            "usable_percent_per_3_2km": usable_percent * 3.2 / distance_km if distance_km else None,
        })
    return rows


def event_table(span, series, datalink, laps, flight_start, flight_end):
    interventions = []
    mode_rows = [row for row in series["MODE"] if flight_start <= row["t"] <= flight_end]
    for row in mode_rows:
        if row.get("Mode") == AUTO_MODE:
            continue
        previous = max((m for m in mode_rows if m["t"] < row["t"]), key=lambda m: m["t"], default=None)
        if previous is None or previous.get("Mode") != AUTO_MODE:
            continue
        lap = next((lap for lap in laps if lap["start_t"] <= row["t"] < lap["end_t"]), None)
        gps = nearest(series["GPS"], row["t"], lambda r: r.get("I", 0) == 0)
        window = summarize_window(series, datalink, row["t"] - 5.0, row["t"] + 2.0)
        pre_window = summarize_window(series, datalink, row["t"] - 5.0, row["t"] - 0.05)
        lane_switches = [
            message for message in series["MSG"]
            if row["t"] - 5.0 <= message["t"] <= row["t"] + 2.0
            and "lane switch" in message.get("Message", "")
        ]
        interventions.append({
            "time_s": row["t"],
            "clock_trt": local_clock(span, row["t"]),
            "lap": lap["lap"] if lap else None,
            "phase_s": row["t"] - lap["start_t"] if lap else None,
            "new_mode": row.get("Mode"),
            "lat": gps.get("Lat") if gps else None,
            "lng": gps.get("Lng") if gps else None,
            "lane_switch_count_around_event": len(lane_switches),
            "seconds_from_nearest_lane_switch": min(
                (abs(message["t"] - row["t"]) for message in series["MSG"] if "lane switch" in message.get("Message", "")),
                default=None,
            ),
            **{f"pre_{key}": value for key, value in pre_window.items() if key != "sample_counts"},
            **window,
        })
    return interventions


def make_lap_rows(span, series, datalink, laps, interventions):
    rows = []
    for lap in laps:
        suspect_start = lap["start_t"] + 20.0
        suspect_end = min(lap["start_t"] + 35.0, lap["end_t"])
        mid_gps = nearest(series["GPS"], lap["start_t"] + 25.0, lambda r: r.get("I", 0) == 0)
        summary = summarize_window(series, datalink, suspect_start, suspect_end)
        matching = [item for item in interventions if item.get("lap") == lap["lap"]]
        rows.append({
            **lap,
            "start_clock_trt": local_clock(span, lap["start_t"]),
            "duration_s": lap["end_t"] - lap["start_t"],
            "phase_lat": mid_gps.get("Lat") if mid_gps else None,
            "phase_lng": mid_gps.get("Lng") if mid_gps else None,
            "pilot_intervention": bool(matching),
            "intervention_clock_trt": matching[0]["clock_trt"] if matching else None,
            **summary,
        })
    return rows


def build_long_leg_rows(span, series, datalink, laps):
    mise = series["MISE"]
    mode_changes = series["MODE"]
    result = []
    for lap in laps:
        events = [row for row in mise if lap["start_t"] <= row["t"] < lap["end_t"]]
        for target_item, leg_name in ((2, "WP5->WP2"), (4, "WP3->WP4")):
            event = next((row for row in events if row.get("CNum") == target_item), None)
            if event is None:
                continue
            following_events = [row["t"] for row in events if row["t"] > event["t"]]
            following_modes = [row["t"] for row in mode_changes if event["t"] < row["t"] < lap["end_t"]]
            natural_end = min(following_events + following_modes + [lap["end_t"]])
            start_t = event["t"] + 8.0
            end_t = min(event["t"] + 30.0, natural_end - 0.2)
            if end_t - start_t < 6.0:
                continue
            summary = summarize_window(series, datalink, start_t, end_t)
            result.append({
                "lap": lap["lap"],
                "leg": leg_name,
                "start_clock_trt": local_clock(span, start_t),
                "window_duration_s": end_t - start_t,
                **summary,
            })
    return result


def vibration_summary(series, start_t, end_t):
    result = {}
    for imu in sorted({row.get("IMU", 0) for row in series["VIBE"]}):
        rows = rows_between(series["VIBE"], start_t, end_t, lambda r, imu=imu: r.get("IMU", 0) == imu)
        result[str(imu)] = {
            "x_p95": q([row.get("VibeX") for row in rows], 95),
            "y_p95": q([row.get("VibeY") for row in rows], 95),
            "z_p95": q([row.get("VibeZ") for row in rows], 95),
            "xyz_max_p95": q([max(row.get("VibeX", 0), row.get("VibeY", 0), row.get("VibeZ", 0)) for row in rows], 95),
            "clip_first": rows[0].get("Clip") if rows else None,
            "clip_last": rows[-1].get("Clip") if rows else None,
        }
    return result


def write_csv(path, rows):
    flat = []
    for row in rows:
        item = dict(row)
        item.pop("sample_counts", None)
        item["mission_items"] = ",".join(str(value) for value in item.get("mission_items", []))
        flat.append(item)
    fields = []
    for row in flat:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flat)


def plot_route(series, laps, interventions, flight_start, flight_end):
    gps = rows_between(series["GPS"], flight_start, flight_end, lambda r: r.get("I", 0) == 0 and r.get("Status", 0) >= 3)
    fig, ax = plt.subplots(figsize=(9, 8))
    color = np.asarray([row["t"] for row in gps])
    scatter = ax.scatter([row["Lng"] for row in gps], [row["Lat"] for row in gps], c=color, s=3, cmap="viridis")
    for item in interventions:
        ax.scatter(item["lng"], item["lat"], s=100, marker="x", color="red", linewidths=2)
        ax.annotate(f"tur {item['lap']}\n{item['clock_trt']}", (item["lng"], item["lat"]), xytext=(5, 5), textcoords="offset points", fontsize=8)
    for idx, lap in enumerate(laps):
        point = nearest(gps, lap["start_t"])
        if point:
            ax.annotate(str(lap["lap"]), (point["Lng"], point["Lat"]), fontsize=7, color="black")
    fig.colorbar(scatter, ax=ax, label="Log time (s)")
    ax.set_title("21 Temmuz uzun uçuş rotası - kırmızı X: AUTO'dan pilot çıkışı")
    ax.set_xlabel("Boylam")
    ax.set_ylabel("Enlem")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "rota_ve_mudahale_noktalari.png", dpi=180)
    plt.close(fig)


def plot_lap_metrics(lap_rows):
    laps = [row["lap"] for row in lap_rows]
    fig, axes = plt.subplots(4, 1, figsize=(12, 13), sharex=True)
    axes[0].plot(laps, [row["bat_v_min"] for row in lap_rows], "o-", label="BAT min")
    axes[0].plot(laps, [row["dl_v_min"] for row in lap_rows], "s--", label="DataLink min")
    axes[0].axhline(19.8, color="gray", ls=":", label="3.30 V/hücre (6S)")
    axes[0].set_ylabel("V")
    axes[0].legend()
    axes[1].plot(laps, [row["dl_current_max_a"] for row in lap_rows], "o-", label="Akım max")
    axes[1].set_ylabel("A")
    axes[1].legend()
    axes[2].plot(laps, [row["att_err_p95_deg"] for row in lap_rows], "o-", label="Attitude hata p95")
    axes[2].plot(laps, [row["motor_pwm_max"] for row in lap_rows], "s--", label="Motor PWM max")
    axes[2].set_ylabel("deg / PWM")
    axes[2].legend()
    axes[3].plot(laps, [row["alt_min_m"] for row in lap_rows], "o-", label="İrtifa min")
    axes[3].plot(laps, [row["gps_speed_min_ms"] for row in lap_rows], "s--", label="Hız min")
    axes[3].set_ylabel("m / m/s")
    axes[3].set_xlabel("Tur")
    axes[3].legend()
    for ax in axes:
        for row in lap_rows:
            if row["pilot_intervention"]:
                ax.axvspan(row["lap"] - 0.25, row["lap"] + 0.25, color="red", alpha=0.12)
        ax.grid(alpha=0.25)
    fig.suptitle("Her turda WP5->WP2 bacağının 20-35 s penceresi")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "tur_bazli_ayni_bolge_karsilastirmasi.png", dpi=180)
    plt.close(fig)


def plot_event_timeline(series, datalink, interventions):
    if not interventions:
        return
    first = interventions[0]["time_s"] - 80.0
    last = interventions[-1]["time_s"] + 80.0
    bat = rows_between(series["BAT"], first, last, lambda r: r.get("Inst", 0) == 0)
    ctun = rows_between(series["CTUN"], first, last)
    motb = rows_between(series["MOTB"], first, last)
    dl = rows_between(datalink, first, last)
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    axes[0].plot([r["t"] for r in bat], [r["Volt"] for r in bat], label="BAT Volt", lw=0.8)
    axes[0].plot([r["t"] for r in dl], [r["voltage_v"] for r in dl], label="DL Volt", lw=0.5, alpha=0.8)
    axes[0].set_ylabel("V")
    axes[0].legend()
    axes[1].plot([r["t"] for r in dl], [r["current_total_a"] for r in dl], label="DL total current", lw=0.6)
    axes[1].set_ylabel("A")
    axes[2].plot([r["t"] for r in ctun], [r["Alt"] for r in ctun], label="Alt", lw=0.8)
    axes[2].plot([r["t"] for r in ctun], [r["DAlt"] for r in ctun], label="DAlt", lw=0.8)
    axes[2].set_ylabel("m")
    axes[2].legend()
    axes[3].plot([r["t"] for r in ctun], [r["ThO"] for r in ctun], label="ThO", lw=0.8)
    axes[3].plot([r["t"] for r in motb], [r["LiftMax"] for r in motb], label="LiftMax", lw=0.8)
    axes[3].set_ylabel("oran")
    axes[3].legend()
    axes[3].set_xlabel("Log time (s)")
    for ax in axes:
        for item in interventions:
            ax.axvline(item["time_s"], color="red", lw=1.0, alpha=0.8)
        ax.grid(alpha=0.25)
    fig.suptitle("Pilot müdahaleleri çevresinde batarya, akım ve irtifa")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "olay_zaman_cizgisi.png", dpi=180)
    plt.close(fig)


def plot_leg_comparison(leg_rows):
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    for leg, style in (("WP5->WP2", "o-"), ("WP3->WP4", "s--")):
        rows = [row for row in leg_rows if row["leg"] == leg]
        axes[0].plot([row["lap"] for row in rows], [row["dl_current_med_a"] for row in rows], style, label=leg)
        axes[1].plot([row["lap"] for row in rows], [row["throttle_med"] for row in rows], style, label=leg)
        axes[2].plot([row["lap"] for row in rows], [row["att_tilt_med_deg"] for row in rows], style, label=leg)
    axes[0].set_ylabel("DataLink akım medyanı (A)")
    axes[1].set_ylabel("Throttle medyanı")
    axes[2].set_ylabel("Tilt medyanı (deg)")
    axes[2].set_xlabel("Tur")
    for ax in axes:
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("İki uzun bacağın yönsel yük karşılaştırması (başlangıçtan 8-30 s)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "uzun_bacak_yonsel_yuk_karsilastirmasi.png", dpi=180)
    plt.close(fig)


def plot_motor_event_details(series, datalink, interventions):
    for item in interventions:
        start_t = item["time_s"] - 10.0
        end_t = item["time_s"] + 5.0
        rcou = rows_between(series["RCOU"], start_t, end_t)
        dl = rows_between(datalink, start_t, end_t)
        att = rows_between(series["ATT"], start_t, end_t)
        ctun = rows_between(series["CTUN"], start_t, end_t)
        bat = rows_between(series["BAT"], start_t, end_t, lambda r: r.get("Inst", 0) == 0)
        fig, axes = plt.subplots(5, 1, figsize=(13, 14), sharex=True)
        for motor_id in range(1, 5):
            axes[0].plot([row["t"] for row in rcou], [row[f"C{motor_id}"] for row in rcou], label=f"C{motor_id}")
            axes[1].plot(
                [row["t"] for row in dl],
                [next(motor["rpm"] for motor in row["motors"] if motor["motor_id"] == motor_id) for row in dl],
                label=f"M{motor_id}",
            )
            axes[2].plot(
                [row["t"] for row in dl],
                [next(motor["current_a"] for motor in row["motors"] if motor["motor_id"] == motor_id) for row in dl],
                label=f"M{motor_id}",
            )
        axes[3].plot([row["t"] for row in att], [row["DesRoll"] for row in att], label="DesRoll", lw=1.0)
        axes[3].plot([row["t"] for row in att], [row["Roll"] for row in att], label="Roll", lw=1.0)
        axes[3].plot([row["t"] for row in att], [row["DesPitch"] for row in att], label="DesPitch", lw=0.8, alpha=0.8)
        axes[3].plot([row["t"] for row in att], [row["Pitch"] for row in att], label="Pitch", lw=0.8, alpha=0.8)
        axes[4].plot([row["t"] for row in bat], [row["Volt"] for row in bat], label="BAT V")
        axes[4].plot([row["t"] for row in dl], [row["voltage_v"] for row in dl], label="DataLink V", alpha=0.8)
        alt_ax = axes[4].twinx()
        alt_ax.plot([row["t"] for row in ctun], [row["Alt"] for row in ctun], color="tab:green", label="Alt")
        axes[0].set_ylabel("PWM")
        axes[1].set_ylabel("RPM")
        axes[2].set_ylabel("A")
        axes[3].set_ylabel("deg")
        axes[4].set_ylabel("V")
        alt_ax.set_ylabel("Alt (m)")
        axes[4].set_xlabel("Log time (s)")
        for ax in axes:
            ax.axvline(item["time_s"], color="red", ls="--", lw=1.0)
            ax.grid(alpha=0.25)
            ax.legend(ncol=4, fontsize=8)
        fig.suptitle(f"Tur {item['lap']} motor olayı - pilot müdahalesi {item['clock_trt']}")
        fig.tight_layout()
        fig.savefig(OUT_DIR / f"motor_olayi_tur_{item['lap']:02d}.png", dpi=180)
        plt.close(fig)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    span, params, series = read_log()
    datalink_raw, file_stats = read_datalink()
    datalink = datalink_with_log_time(span, datalink_raw)
    flight_start, flight_end = identify_long_flight(series)
    laps = build_laps(series, flight_start, flight_end)
    interventions = event_table(span, series, datalink, laps, flight_start, flight_end)
    lap_rows = make_lap_rows(span, series, datalink, laps, interventions)
    lap_energy_rows = build_lap_energy_rows(series, datalink, laps)
    leg_rows = build_long_leg_rows(span, series, datalink, laps)
    dl_integral = integrate_datalink(datalink, flight_start, flight_end)
    full_flight_summary = summarize_window(series, datalink, flight_start, flight_end)
    uninterrupted_laps = [lap for lap in laps if lap["mission_items"] == [2, 3, 4, 5]]
    uninterrupted_start = uninterrupted_laps[0]["start_t"]
    uninterrupted_end = uninterrupted_laps[-1]["end_t"]
    uninterrupted_integral = integrate_datalink(datalink, uninterrupted_start, uninterrupted_end)
    uninterrupted_distance_km = gps_distance_km(series, uninterrupted_start, uninterrupted_end)
    uninterrupted_nominal_percent = 100.0 * uninterrupted_integral["capacity_ah"] / 27.0
    distance_consumption_summary = {
        "uninterrupted_complete_lap_count": len(uninterrupted_laps),
        "distance_km": uninterrupted_distance_km,
        "one_parallel_arm_ah": uninterrupted_integral["capacity_ah"],
        "one_parallel_arm_wh": uninterrupted_integral["energy_wh"],
        "estimated_full_pack_wh": 2.0 * uninterrupted_integral["energy_wh"],
        "nominal_pack_percent": uninterrupted_nominal_percent,
        "measured_usable_pack_percent": 100.0 * uninterrupted_integral["capacity_ah"] / 25.2,
        "nominal_percent_per_3_2km": uninterrupted_nominal_percent * 3.2 / uninterrupted_distance_km,
        "usable_percent_per_3_2km": (
            100.0 * uninterrupted_integral["capacity_ah"] / 25.2 * 3.2 / uninterrupted_distance_km
        ),
    }
    motor_yaw = {
        "uninterrupted_complete_laps": motor_yaw_summary(
            series, datalink, uninterrupted_start, uninterrupted_end
        ),
        "full_armed_flight": motor_yaw_summary(series, datalink, flight_start, flight_end),
    }
    lane_switches = [
        row for row in series["MSG"]
        if flight_start <= row["t"] <= flight_end and "lane switch" in row.get("Message", "")
    ]

    report = {
        "bin": BIN_PATH.name,
        "datalink_session": DL_SESSION.name,
        "datalink_clock_alignment": {
            "filename_clock_ahead_of_gps_s": DATALINK_CLOCK_AHEAD_S,
            "method": "CTUN.ThO ile DataLink toplam akiminin capraz korelasyonu",
            "smoothed_correlation": 0.83,
        },
        "gps_span_utc": {"first": span["first_utc"].isoformat(), "last": span["last_utc"].isoformat()},
        "long_flight": {
            "start_t": flight_start,
            "end_t": flight_end,
            "duration_s": flight_end - flight_start,
            "start_clock_trt": local_clock(span, flight_start),
            "end_clock_trt": local_clock(span, flight_end),
        },
        "key_params": {key: params.get(key) for key in [
            "BATT_CAPACITY", "BATT_LOW_VOLT", "BATT_CRT_VOLT", "BATT_FS_LOW_ACT", "BATT_FS_CRT_ACT",
            "MOT_BAT_VOLT_MAX", "MOT_BAT_VOLT_MIN", "MOT_PWM_MIN", "MOT_PWM_MAX", "MOT_SPIN_MAX",
            "WPNAV_SPEED", "WPNAV_ACCEL", "WPNAV_RADIUS", "FS_EKF_THRESH", "FS_EKF_ACTION",
        ]},
        "datalink_integral": dl_integral,
        "distance_consumption": distance_consumption_summary,
        "motor_yaw_balance": motor_yaw,
        "full_flight_summary": full_flight_summary,
        "vibration_by_imu": vibration_summary(series, flight_start, flight_end),
        "ekf_lane_switches": {
            "count": len(lane_switches),
            "per_minute": len(lane_switches) / ((flight_end - flight_start) / 60.0),
        },
        "datalink_files": file_stats,
        "interventions": interventions,
        "laps": lap_rows,
        "lap_energy": lap_energy_rows,
        "long_legs": leg_rows,
    }
    (OUT_DIR / "analiz_ozeti.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_csv(OUT_DIR / "tur_bazli_karsilastirma.csv", lap_rows)
    write_csv(OUT_DIR / "tur_bazli_tuketim.csv", lap_energy_rows)
    write_csv(OUT_DIR / "pilot_mudahale_olaylari.csv", interventions)
    write_csv(OUT_DIR / "uzun_bacak_yonsel_yuk.csv", leg_rows)
    plot_route(series, laps, interventions, flight_start, flight_end)
    plot_lap_metrics(lap_rows)
    plot_event_timeline(series, datalink, interventions)
    plot_leg_comparison(leg_rows)
    plot_motor_event_details(series, datalink, interventions)

    print(json.dumps({
        "flight": report["long_flight"],
        "lap_count": len(laps),
        "datalink_integral": dl_integral,
        "interventions": interventions,
        "output_dir": str(OUT_DIR),
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
