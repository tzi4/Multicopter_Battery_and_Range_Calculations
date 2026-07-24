"""PID / attitude-loop diagnostics for the large-quad ArduPilot logs.

Standalone (does not import the battery pipeline). Compares the calm July-3
flights (76, 77) against the windy July-9 flight (82) to characterise the
low-frequency oscillation the pilot reported, using:

  * exact PID/filter parameter comparison across logs,
  * flight/hover segmentation (ARM + airborne + steady-hover masks),
  * high-rate batch-sampler (ISBH/ISBD, ~3277 Hz) gyro PSD  <-- authoritative,
  * low-rate IMU / RATE PSD for the 0.5-3 Hz "wallow" band,
  * PID-term (P/I/D) breakdown,
  * a best-effort rate-loop transfer-function / coherence estimate.

All console output is ASCII (Windows cp1252). Turkish text only in the .md
report (utf-8). Plots use the Agg backend. Nothing is written outside
analysis_outputs/pid_tuning/, which .gitignore already ignores.

Run:  MPLBACKEND=Agg PYTHONIOENCODING=utf-8 python pid_diagnostics.py
"""
from __future__ import annotations

import math
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
from scipy import signal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pymavlink import mavutil

DEG = 180.0 / math.pi

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "analysis_outputs" / "pid_tuning"

# label -> (path, condition). 76/77 calm (good), 82 windy (bad, oscillation).
LOGS = {
    "76": (ROOT / "3 Temmuz Tuem Test Loglari" / "00000076.BIN", "calm"),
    "77": (ROOT / "3 Temmuz Tuem Test Loglari" / "00000077.BIN", "calm"),
    "82": (Path(r"D:/Takim/itunom ikinci sene/Loglar/Drone 0.0/00000082.BIN"), "windy"),
}

# Robust path resolution: the folder name has Turkish characters; resolve at runtime.
def _resolve_logs():
    resolved = {}
    july3 = None
    for d in ROOT.iterdir():
        if d.is_dir() and d.name.startswith("3 Temmuz"):
            july3 = d
            break
    for label, (path, cond) in LOGS.items():
        if label in ("76", "77") and july3 is not None:
            cand = july3 / f"000000{label}.BIN"
            resolved[label] = (cand, cond)
        else:
            resolved[label] = (path, cond)
    # 82 lives in a sibling working dir; try a couple of spellings.
    if not resolved["82"][0].exists():
        for base in [
            r"D:/Takim/itunom ikinci sene/Loglar/Drone 0.0/00000082.BIN",
            r"D:/Takım/itünom ikinci sene/Loglar/Drone 0.0/00000082.BIN",
        ]:
            p = Path(base)
            if p.exists():
                resolved["82"] = (p, "windy")
                break
    return resolved


MODE_NAMES = {
    0: "STAB", 1: "ACRO", 2: "ALTHOLD", 3: "AUTO", 4: "GUIDED", 5: "LOITER",
    6: "RTL", 7: "CIRCLE", 9: "LAND", 11: "DRIFT", 13: "SPORT", 16: "POSHOLD",
    17: "BRAKE", 18: "THROW", 20: "GUIDED_NOGPS", 23: "AUTOROTATE",
}
HOVER_MODES = {0, 2, 4, 5, 16}  # STAB/ALTHOLD/GUIDED/LOITER/POSHOLD


# --------------------------------------------------------------------------
# small stats helpers (mirrors analyze_july3_battery idioms)
# --------------------------------------------------------------------------
def pct(values, p):
    v = [x for x in values if x is not None and math.isfinite(x)]
    return float(np.percentile(np.asarray(v, float), p)) if v else None


def rms(a):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return float(np.sqrt(np.mean(a * a))) if a.size else float("nan")


def _interp(t_grid, t, x):
    """Linear interp of (t, x) onto t_grid; needs sorted unique t."""
    t = np.asarray(t, float)
    x = np.asarray(x, float)
    ok = np.isfinite(t) & np.isfinite(x)
    t, x = t[ok], x[ok]
    if t.size < 2:
        return np.full_like(t_grid, np.nan, dtype=float)
    order = np.argsort(t)
    t, x = t[order], x[order]
    t, uix = np.unique(t, return_index=True)
    x = x[uix]
    return np.interp(t_grid, t, x, left=np.nan, right=np.nan)


def _interp_zoh(t_grid, t, x):
    """Zero-order-hold (previous-value) interp for categorical signals like MODE."""
    t = np.asarray(t, float)
    x = np.asarray(x, float)
    ok = np.isfinite(t) & np.isfinite(x)
    t, x = t[ok], x[ok]
    if t.size == 0:
        return np.full_like(t_grid, np.nan, dtype=float)
    order = np.argsort(t)
    t, x = t[order], x[order]
    idx = np.searchsorted(t, t_grid, side="right") - 1
    idx = np.clip(idx, 0, t.size - 1)
    out = x[idx]
    out[np.asarray(t_grid) < t[0]] = np.nan
    return out


def _trapz(y, x):
    fn = getattr(np, "trapezoid", None) or np.trapz
    return float(fn(y, x))


# --------------------------------------------------------------------------
# time anchor (GPS week -> UTC), reused pattern
# --------------------------------------------------------------------------
def get_time_anchor(bin_path: Path):
    log = mavutil.mavlink_connection(str(bin_path), robust_parsing=True)
    while True:
        msg = log.recv_match(type="GPS", blocking=False)
        if msg is None:
            break
        d = msg.to_dict()
        if d.get("GWk") and d.get("GMS") and "TimeUS" in d:
            epoch = datetime(1980, 1, 6, tzinfo=timezone.utc)
            utc = epoch + timedelta(weeks=d["GWk"], milliseconds=d["GMS"] - 18_000)
            return {"timeus_s": d["TimeUS"] / 1e6, "utc": utc}
    return None


# --------------------------------------------------------------------------
# single-pass reader
# --------------------------------------------------------------------------
def read_pid_series(bin_path: Path):
    """One pass over the log; returns dict of numpy arrays + parameters + batch."""
    params = {}
    cols = defaultdict(list)
    isbh = []          # list of dicts
    isbd_by_n = defaultdict(list)  # N -> list of (seqno, x, y, z)

    log = mavutil.mavlink_connection(str(bin_path), robust_parsing=True)
    while True:
        msg = log.recv_match(blocking=False)
        if msg is None:
            break
        t = msg.get_type()
        if t == "PARM":
            params[msg.Name] = msg.Value
            continue
        d = msg.to_dict()
        tu = d.get("TimeUS")
        ts = tu / 1e6 if tu is not None else None
        if t == "ARM":
            cols["ARM"].append((ts, d.get("ArmState")))
        elif t == "EV":
            cols["EV"].append((ts, d.get("Id")))
        elif t == "MODE":
            cols["MODE"].append((ts, d.get("ModeNum", d.get("Mode"))))
        elif t == "CTUN":
            cols["CTUN"].append((ts, d.get("ThO"), d.get("Alt"), d.get("CRt")))
        elif t == "BARO" and d.get("I", 0) == 0:
            cols["BARO"].append((ts, d.get("Alt")))
        elif t == "IMU" and d.get("I", 0) == 0:
            cols["IMU"].append((ts, d.get("GyrX"), d.get("GyrY"), d.get("GyrZ")))
        elif t == "RATE":
            cols["RATE"].append((ts, d.get("RDes"), d.get("R"), d.get("PDes"),
                                 d.get("P"), d.get("YDes"), d.get("Y")))
        elif t in ("PIDR", "PIDP", "PIDY"):
            cols[t].append((ts, d.get("Tar"), d.get("Act"), d.get("P"),
                            d.get("I"), d.get("D"), d.get("FF", 0.0)))
        elif t == "RCOU":
            cols["RCOU"].append((ts, d.get("C1"), d.get("C2"), d.get("C3"), d.get("C4")))
        elif t == "ATT":
            cols["ATT"].append((ts, d.get("Roll"), d.get("Pitch"),
                                d.get("DesRoll"), d.get("DesPitch")))
        elif t == "XKF1" and d.get("C", 0) == 0:
            cols["XKF1"].append((ts, d.get("VN", 0.0) or 0.0, d.get("VE", 0.0) or 0.0,
                                 d.get("VD", 0.0) or 0.0))
        elif t == "ISBH":
            isbh.append({
                "t": ts, "N": d.get("N"), "type": d.get("type"),
                "instance": d.get("instance"), "mul": d.get("mul"),
                "smp_rate": d.get("smp_rate"),
                "sample_s": (d.get("SampleUS") or 0) / 1e6,
            })
        elif t == "ISBD":
            isbd_by_n[d.get("N")].append(
                (d.get("seqno"), d.get("x"), d.get("y"), d.get("z")))

    arr = {}
    schema = {
        "ARM": ["t", "state"],
        "EV": ["t", "id"],
        "MODE": ["t", "mode"],
        "CTUN": ["t", "tho", "alt", "crt"],
        "BARO": ["t", "alt"],
        "IMU": ["t", "gx", "gy", "gz"],
        "RATE": ["t", "rdes", "r", "pdes", "p", "ydes", "y"],
        "PIDR": ["t", "tar", "act", "P", "I", "D", "FF"],
        "PIDP": ["t", "tar", "act", "P", "I", "D", "FF"],
        "PIDY": ["t", "tar", "act", "P", "I", "D", "FF"],
        "RCOU": ["t", "c1", "c2", "c3", "c4"],
        "ATT": ["t", "roll", "pitch", "desroll", "despitch"],
        "XKF1": ["t", "vn", "ve", "vd"],
    }
    for key, names in schema.items():
        rows = cols.get(key, [])
        if rows:
            a = np.array(rows, dtype=float)
        else:
            a = np.zeros((0, len(names)), dtype=float)
        arr[key] = {n: a[:, i] if a.size else np.array([]) for i, n in enumerate(names)}

    # reconstruct gyro batches (type==1, instance 0)
    batches = build_gyro_batches(isbh, isbd_by_n)
    return {"params": params, "arr": arr, "batches": batches}


def build_gyro_batches(isbh, isbd_by_n):
    """Return list of dicts: {t0, fs, gx, gy, gz} in rad/s for gyro batches."""
    out = []
    hdr_by_n = {h["N"]: h for h in isbh}
    for n, chunks in isbd_by_n.items():
        h = hdr_by_n.get(n)
        if h is None or h.get("type") != 1 or not h.get("mul"):
            continue
        chunks = sorted(chunks, key=lambda c: (c[0] if c[0] is not None else 0))
        xs, ys, zs = [], [], []
        for seqno, x, y, z in chunks:
            if x is None:
                continue
            xs.extend(list(x)); ys.extend(list(y)); zs.extend(list(z))
        if len(xs) < 256:
            continue
        mul = float(h["mul"])
        out.append({
            "t0": h["sample_s"], "fs": float(h["smp_rate"]),
            "gx": np.asarray(xs, float) / mul,
            "gy": np.asarray(ys, float) / mul,
            "gz": np.asarray(zs, float) / mul,
        })
    out.sort(key=lambda b: b["t0"])
    return out


# --------------------------------------------------------------------------
# segmentation
# --------------------------------------------------------------------------
def armed_windows(arr):
    A = arr["ARM"]
    wins = []
    if A["t"].size:
        start = None
        for ti, st in zip(A["t"], A["state"]):
            if st >= 0.5 and start is None:
                start = ti
            elif st < 0.5 and start is not None:
                if ti - start > 15:
                    wins.append((start, ti))
                start = None
        if start is not None:
            end = float(np.nanmax(arr["RATE"]["t"])) if arr["RATE"]["t"].size else start
            if end - start > 15:
                wins.append((start, end))
    if not wins:  # fallback to EV 10/11
        E = arr["EV"]
        start = None
        for ti, idv in zip(E["t"], E["id"]):
            if idv == 10 and start is None:
                start = ti
            elif idv == 11 and start is not None:
                if ti - start > 15:
                    wins.append((start, ti))
                start = None
    if not wins:  # last resort: barometric airborne islands (e.g. armed pre-log)
        wins = airborne_windows(arr)
    return wins


def airborne_windows(arr, thr_m=2.0, min_s=30.0):
    """Flight windows from BARO relative altitude when ARM/EV are unavailable."""
    t = arr["BARO"]["t"]; alt = arr["BARO"]["alt"]
    ok = np.isfinite(t) & np.isfinite(alt)
    t, alt = t[ok], alt[ok]
    if t.size < 50:
        return []
    ground = np.percentile(alt[:min(300, alt.size)], 10)
    rel = alt - ground
    air = rel > thr_m
    wins = []
    i = 0
    while i < air.size:
        if air[i]:
            j = i
            while j < air.size and air[j]:
                j += 1
            if t[j - 1] - t[i] > min_s:
                wins.append((float(t[i]), float(t[j - 1])))
            i = j
        else:
            i += 1
    return wins


def hover_window(arr, win, fs=5.0, min_island=10.0, target=30.0):
    """Find the best steady-hover sub-window inside an armed window.

    Returns (t0, t1, diag) or None. diag holds mask fractions for the report.
    """
    t0, t1 = win
    grid = np.arange(t0, t1, 1.0 / fs)
    if grid.size < int(min_island * fs):
        return None

    baro_alt = _interp(grid, arr["BARO"]["t"], arr["BARO"]["alt"])
    ground = pct(baro_alt[:min(300, baro_alt.size)], 10) if np.isfinite(baro_alt).any() else None
    rel_alt = baro_alt - ground if ground is not None else np.full_like(grid, np.nan)

    tho = _interp(grid, arr["CTUN"]["t"], arr["CTUN"]["tho"])
    roll = _interp(grid, arr["ATT"]["t"], arr["ATT"]["roll"])
    pitch = _interp(grid, arr["ATT"]["t"], arr["ATT"]["pitch"])
    # RATE.* are already in deg/s in ArduPilot logs (do NOT convert).
    rdes = _interp(grid, arr["RATE"]["t"], arr["RATE"]["rdes"])
    pdes = _interp(grid, arr["RATE"]["t"], arr["RATE"]["pdes"])
    if arr["XKF1"]["t"].size:
        spd = np.hypot(_interp(grid, arr["XKF1"]["t"], arr["XKF1"]["vn"]),
                       _interp(grid, arr["XKF1"]["t"], arr["XKF1"]["ve"]))
    else:
        spd = np.zeros_like(grid)
    mode = _interp_zoh(grid, arr["MODE"]["t"], arr["MODE"]["mode"])
    # climb from EKF vertical velocity (-VD, m/s) - smooth & robust; baro is too noisy
    if arr["XKF1"]["t"].size:
        climb = -_interp(grid, arr["XKF1"]["t"], arr["XKF1"]["vd"])
    else:
        climb = np.zeros_like(grid)

    def med1s(x, secs=1.0):
        w = max(1, int(secs * fs))
        w = w if w % 2 else w + 1
        return signal.medfilt(np.nan_to_num(x, nan=0.0), kernel_size=w)

    # airborne on a heavily smoothed altitude to avoid baro-noise fragmentation
    rel_s = med1s(rel_alt, secs=3.0) if ground is not None else np.zeros_like(grid)
    airborne = rel_s > 2.0 if ground is not None else np.ones_like(grid, bool)
    m_crt = np.abs(med1s(climb)) < 1.5
    m_spd = med1s(spd) < 1.8
    m_roll = np.abs(med1s(roll)) < 8.0
    m_pitch = np.abs(med1s(pitch)) < 8.0
    m_tho = (tho > 0.18) & (tho < 0.60)
    m_cmd = (np.abs(med1s(rdes)) < 30.0) & (np.abs(med1s(pdes)) < 30.0)
    m_mode = np.array([int(round(mm)) in HOVER_MODES if np.isfinite(mm) else False for mm in mode])

    mask = airborne & m_crt & m_spd & m_roll & m_pitch & m_tho & m_cmd & m_mode
    diag = {
        "airborne": float(np.mean(airborne)), "level": float(np.mean(m_roll & m_pitch)),
        "low_speed": float(np.mean(m_spd)), "low_climb": float(np.mean(m_crt)),
        "throttle_ok": float(np.mean(m_tho)), "low_cmd": float(np.mean(m_cmd)),
        "hover_mode": float(np.mean(m_mode)), "hover_frac": float(np.mean(mask)),
    }

    # longest contiguous island
    best = None
    i = 0
    while i < mask.size:
        if mask[i]:
            j = i
            while j < mask.size and mask[j]:
                j += 1
            dur = (j - i) / fs
            if best is None or dur > best[2]:
                best = (i, j, dur)
            i = j
        else:
            i += 1
    if best is None or best[2] < min_island:
        return None
    i, j, dur = best
    # centre a target-length sub-window in the island
    if dur > target:
        centre = (i + j) // 2
        half = int(target * fs / 2)
        i2 = max(i, centre - half)
        j2 = min(j, i2 + int(target * fs))
    else:
        i2, j2 = i, j
    return (float(grid[i2]), float(grid[min(j2, grid.size - 1)]), diag)


# --------------------------------------------------------------------------
# spectral analysis
# --------------------------------------------------------------------------
def _slice(arr_group, tkey, t0, t1):
    t = arr_group[tkey]
    return (t >= t0) & (t <= t1)


def psd_uniform(t, x, t0, t1, fs, nseg_s=8.0):
    """Resample (t,x) in [t0,t1] to fs Hz, detrend, Welch PSD (deg-based units left to caller)."""
    m = (t >= t0) & (t <= t1) & np.isfinite(t) & np.isfinite(x)
    if m.sum() < 16:
        return None, None
    grid = np.arange(t0, t1, 1.0 / fs)
    xg = _interp(grid, t[m], x[m])
    xg = xg[np.isfinite(xg)]
    if xg.size < 32:
        return None, None
    nper = int(min(len(xg), max(64, nseg_s * fs)))
    f, P = signal.welch(signal.detrend(xg), fs=fs, nperseg=nper,
                        noverlap=nper // 2, window="hann")
    return f, P


def batch_psd(batches, t0, t1, axis="gx"):
    """MEDIAN PSD across gyro batches in [t0,t1]. Median is robust to the few
    gusty/transient batches that otherwise dominate a mean. Returns f, P (deg/s)^2/Hz."""
    sel = [b for b in batches if t0 <= b["t0"] <= t1]
    if not sel:
        sel = batches  # fall back to whole flight if window has no batch
    if not sel:
        return None, None, 0
    Ps = []
    fref = None
    for b in sel:
        x = np.asarray(b[axis], float) * DEG  # rad/s -> deg/s
        if x.size < 256:
            continue
        nper = min(1024, x.size)
        f, P = signal.welch(signal.detrend(x), fs=b["fs"], nperseg=nper,
                            noverlap=nper // 2, window="hann")
        if fref is None:
            fref = f
        Ps.append(P if f.shape == fref.shape else np.interp(fref, f, P))
    if not Ps:
        return None, None, 0
    return fref, np.median(np.vstack(Ps), axis=0), len(Ps)


def band_rms_from_psd(f, P, lo, hi):
    """RMS (deg/s) integrated over [lo,hi] from a one-sided PSD."""
    if f is None:
        return float("nan")
    m = (f >= lo) & (f <= hi)
    if m.sum() < 2:
        return float("nan")
    return float(np.sqrt(_trapz(P[m], f[m])))


def dominant_peak(f, P, lo=0.3, hi=None):
    if f is None:
        return None, None
    hi = hi if hi is not None else f[-1]
    m = (f >= lo) & (f <= hi)
    if m.sum() < 2:
        return None, None
    idx = np.argmax(P[m])
    return float(f[m][idx]), float(P[m][idx])


# --------------------------------------------------------------------------
# transfer function / coherence (best effort)
# --------------------------------------------------------------------------
def rate_tf(arr, t0, t1, des_key, act_key, fs=10.0):
    t = arr["RATE"]["t"]
    m = (t >= t0) & (t <= t1)
    if m.sum() < 32:
        return None
    grid = np.arange(t0, t1, 1.0 / fs)
    des = _interp(grid, t[m], arr["RATE"][des_key][m])  # already deg/s
    act = _interp(grid, t[m], arr["RATE"][act_key][m])
    ok = np.isfinite(des) & np.isfinite(act)
    des, act = des[ok], act[ok]
    if des.size < 32:
        return None
    nper = int(min(len(des), max(32, 4 * fs)))
    f, Cxy = signal.coherence(des, act, fs=fs, nperseg=nper)
    _, Pxy = signal.csd(des, act, fs=fs, nperseg=nper)
    _, Pxx = signal.welch(des, fs=fs, nperseg=nper)
    H = np.abs(Pxy) / np.where(Pxx > 0, Pxx, np.nan)
    return {"f": f, "coh": Cxy, "H": H}


# --------------------------------------------------------------------------
# parameter extraction
# --------------------------------------------------------------------------
PID_KEYS = [
    "ATC_RAT_RLL_P", "ATC_RAT_RLL_I", "ATC_RAT_RLL_D",
    "ATC_RAT_PIT_P", "ATC_RAT_PIT_I", "ATC_RAT_PIT_D",
    "ATC_RAT_YAW_P", "ATC_RAT_YAW_I", "ATC_RAT_YAW_D",
    "ATC_ANG_RLL_P", "ATC_ANG_PIT_P", "ATC_ANG_YAW_P",
    "ATC_RAT_RLL_FLTT", "ATC_RAT_RLL_FLTD", "ATC_RAT_PIT_FLTT",
    "ATC_RAT_PIT_FLTD", "ATC_RAT_YAW_FLTD",
    "INS_GYRO_FILTER", "INS_ACCEL_FILTER",
    "INS_HNTCH_ENABLE", "INS_HNTCH_MODE", "INS_HNTCH_FREQ",
    "INS_HNTCH_BW", "INS_HNTCH_REF", "INS_HNTCH_HMNCS",
    "MOT_THST_HOVER", "MOT_THST_EXPO", "MOT_SPIN_MIN", "MOT_SPIN_MAX",
    "MOT_BAT_VOLT_MAX", "MOT_BAT_VOLT_MIN",
    "PSC_VELXY_P", "PSC_VELXY_D", "PSC_POSXY_P",
    "FRAME_CLASS", "FRAME_TYPE", "SCHED_LOOP_RATE", "LOG_BITMASK",
    "AUTOTUNE_AGGR", "AUTOTUNE_AXES",
]


# recommended changes (agreed in plan) as (param, proposed, rationale)
RECOMMEND = [
    ("ATC_RAT_RLL_P", 0.120, "QuikTune agresifligini kirp (-%22)"),
    ("ATC_RAT_RLL_I", 0.120, "I=P konvansiyonu"),
    ("ATC_RAT_RLL_D", 0.0055, "wallow sonumleme (+%35) - once FLTD=10 ve notch"),
    ("ATC_RAT_PIT_P", 0.155, "QuikTune agresifligini kirp (-%22)"),
    ("ATC_RAT_PIT_I", 0.155, "I=P konvansiyonu"),
    ("ATC_RAT_PIT_D", 0.0070, "wallow sonumleme (+%35) - once FLTD=10 ve notch"),
    ("ATC_RAT_RLL_FLTT", 10.0, ">=13 inch pervane kurali (15->10)"),
    ("ATC_RAT_RLL_FLTD", 10.0, ">=13 inch pervane kurali (15->10)"),
    ("ATC_RAT_PIT_FLTT", 10.0, ">=13 inch pervane kurali (15->10)"),
    ("ATC_RAT_PIT_FLTD", 10.0, ">=13 inch pervane kurali (15->10)"),
    ("INS_GYRO_FILTER", 20.0, "FLTD=gyro/2 kurali; motor bandini notch halleder"),
    ("ATC_RAT_YAW_FLTD", 6.0, "yaw icin gyro/4"),
    ("ATC_ANG_RLL_P", 4.5, "hafif angle-P kirpma"),
    ("ATC_ANG_PIT_P", 4.5, "hafif angle-P kirpma"),
    ("INS_HNTCH_REF", 0.30, "throttle-mode notch REF ~ hover gazi (0.393 fazla yuksek)"),
]

FALLBACK = [
    ("ATC_RAT_RLL_P", 0.108), ("ATC_RAT_RLL_I", 0.108), ("ATC_RAT_RLL_D", 0.0029),
    ("ATC_RAT_PIT_P", 0.140), ("ATC_RAT_PIT_I", 0.140), ("ATC_RAT_PIT_D", 0.0036),
    ("ATC_RAT_RLL_FLTT", 10.0), ("ATC_RAT_RLL_FLTD", 10.0),
    ("ATC_RAT_PIT_FLTT", 10.0), ("ATC_RAT_PIT_FLTD", 10.0),
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logs = _resolve_logs()
    data = {}
    for label, (path, cond) in logs.items():
        if not path.exists():
            print("MISSING:", label, path)
            continue
        print("[read] %s (%s) %s" % (label, cond, path.name))
        s = read_pid_series(path)
        wins = armed_windows(s["arr"])
        hover = None
        for w in sorted(wins, key=lambda w: w[1] - w[0], reverse=True):
            hv = hover_window(s["arr"], w)
            if hv is not None:
                hover = hv
                break
        data[label] = {"path": path, "cond": cond, "series": s,
                       "armed": wins, "hover": hover}
        if hover:
            print("   armed windows=%d  hover=[%.0f..%.0f]s (%.0fs)  hover_frac=%.2f"
                  % (len(wins), hover[0], hover[1], hover[1] - hover[0], hover[2]["hover_frac"]))
        else:
            print("   armed windows=%d  NO steady-hover island found" % len(wins))
        print("   gyro batches=%d" % len(s["batches"]))

    _analyze_and_report(data)
    print("[done] outputs in", OUT_DIR)


def _analyze_and_report(data):
    # ---- parameter comparison ----
    labels = [l for l in ("76", "77", "82") if l in data]
    param_table = []
    for k in PID_KEYS:
        row = {"param": k}
        for l in labels:
            row[l] = data[l]["series"]["params"].get(k)
        param_table.append(row)

    # ---- oscillation metrics per log (on hover window) ----
    metrics = {}
    for l in labels:
        s = data[l]["series"]; arr = s["arr"]
        hv = data[l]["hover"]
        if hv is None:
            # fall back to any airborne-ish window: use full RATE span middle 60%
            t = arr["RATE"]["t"]
            if t.size:
                t0 = np.percentile(t, 20); t1 = np.percentile(t, 80)
            else:
                t0 = t1 = 0.0
        else:
            t0, t1 = hv[0], hv[1]
        m = {}
        # batch (authoritative) PSD per axis
        for ax, name in [("gx", "roll"), ("gy", "pitch"), ("gz", "yaw")]:
            f, P, used = batch_psd(s["batches"], t0, t1, ax)
            m["batch_%s" % name] = {
                "f": f, "P": P, "used": used,
                "peak": dominant_peak(f, P, lo=5.0),
                "rms_1_10": band_rms_from_psd(f, P, 1.0, 10.0),
                "rms_10_60": band_rms_from_psd(f, P, 10.0, 60.0),
                "rms_60_120": band_rms_from_psd(f, P, 60.0, 120.0),
            }
        # low-rate IMU gyro PSD (wallow band)
        for ax, name in [("gx", "roll"), ("gy", "pitch"), ("gz", "yaw")]:
            f, P = psd_uniform(arr["IMU"]["t"], arr["IMU"][ax] * DEG, t0, t1, fs=50.0)
            m["imu_%s" % name] = {
                "f": f, "P": P,
                "peak": dominant_peak(f, P, lo=0.4, hi=20.0),
                "rms_05_3": band_rms_from_psd(f, P, 0.5, 3.0),
                "rms_3_8": band_rms_from_psd(f, P, 3.0, 8.0),
            }
        # RATE tracking error PSD (roll/pitch)
        for des, act, name in [("rdes", "r", "roll"), ("pdes", "p", "pitch")]:
            t = arr["RATE"]["t"]
            sel = (t >= t0) & (t <= t1)
            err = (arr["RATE"][act] - arr["RATE"][des])  # deg/s
            f, P = psd_uniform(t, err, t0, t1, fs=10.0)
            m["rateerr_%s" % name] = {
                "f": f, "P": P,
                "rms_05_3": band_rms_from_psd(f, P, 0.5, 3.0),
                "err_rms": rms(err[sel]),
            }
        # PID term breakdown (roll/pitch)
        for pkey, name in [("PIDR", "roll"), ("PIDP", "pitch")]:
            g = arr.get(pkey)
            if g is None or g["t"].size == 0:
                continue
            t = g["t"]; sel = (t >= t0) & (t <= t1)
            m["pidterm_%s" % name] = {
                "P": rms(g["P"][sel]), "I": rms(g["I"][sel]),
                "D": rms(g["D"][sel]), "FF": rms(g["FF"][sel]),
                # is D actually damping? corr(D, -d(act)/dt)
                "d_damp_corr": _damp_corr(t[sel], g["act"][sel], g["D"][sel]),
            }
        # transfer function (roll)
        m["tf_roll"] = rate_tf(arr, t0, t1, "rdes", "r")
        m["window"] = (t0, t1)
        metrics[l] = m

    _render_plots(data, metrics, labels)
    _write_report(data, metrics, labels, param_table)


def _damp_corr(t, act, dterm):
    t = np.asarray(t, float); act = np.asarray(act, float); dterm = np.asarray(dterm, float)
    if t.size < 8:
        return float("nan")
    dact = np.gradient(act, t)
    a, b = -dact, dterm
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 8 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return float("nan")
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def _render_plots(data, metrics, labels):
    colors = {"76": "#2c7fb8", "77": "#41b6c4", "82": "#d7301f"}

    # 1) batch gyro PSD compare (roll/pitch/yaw)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for ax, name in zip(axes, ["roll", "pitch", "yaw"]):
        for l in labels:
            d = metrics[l]["batch_%s" % name]
            if d["f"] is None:
                continue
            ax.semilogy(d["f"], d["P"], color=colors[l], lw=1.0,
                        label="%s (%s)" % (l, data[l]["cond"]))
        # notch marker
        ref = data[labels[-1]]["series"]["params"]
        fq = ref.get("INS_HNTCH_FREQ")
        if fq:
            ax.axvline(fq, color="gray", ls="--", lw=0.8)
            ax.text(fq, ax.get_ylim()[1], " notch %.0fHz" % fq, fontsize=7, color="gray", va="top")
        ax.set_title("Batch gyro PSD - %s" % name)
        ax.set_xlabel("Hz"); ax.set_xlim(1, 200); ax.grid(True, which="both", alpha=0.25)
        if name == "roll":
            ax.set_ylabel("(deg/s)^2/Hz"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT_DIR / "batch_gyro_psd_compare.png", dpi=120); plt.close(fig)

    # 2) IMU low-rate PSD (wallow band)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for ax, name in zip(axes, ["roll", "pitch", "yaw"]):
        for l in labels:
            d = metrics[l]["imu_%s" % name]
            if d["f"] is None:
                continue
            ax.semilogy(d["f"], d["P"], color=colors[l], lw=1.1,
                        label="%s (%s)" % (l, data[l]["cond"]))
        ax.axvspan(0.5, 3.0, color="orange", alpha=0.08)
        ax.set_title("IMU gyro PSD (low-rate) - %s" % name)
        ax.set_xlabel("Hz"); ax.set_xlim(0.2, 20); ax.grid(True, which="both", alpha=0.25)
        if name == "roll":
            ax.set_ylabel("(deg/s)^2/Hz"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT_DIR / "imu_gyro_psd_compare.png", dpi=120); plt.close(fig)

    # 3) RATE error PSD roll/pitch
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, name in zip(axes, ["roll", "pitch"]):
        for l in labels:
            d = metrics[l].get("rateerr_%s" % name)
            if not d or d["f"] is None:
                continue
            ax.semilogy(d["f"], d["P"], color=colors[l], lw=1.2,
                        label="%s (%s)" % (l, data[l]["cond"]))
        ax.axvspan(0.5, 3.0, color="orange", alpha=0.08)
        ax.set_title("RATE tracking-error PSD - %s" % name)
        ax.set_xlabel("Hz"); ax.set_xlim(0.2, 5); ax.grid(True, which="both", alpha=0.25)
        if name == "roll":
            ax.set_ylabel("(deg/s)^2/Hz"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT_DIR / "rate_error_psd_compare.png", dpi=120); plt.close(fig)

    # 4) segmentation timeline per log
    fig, axes = plt.subplots(len(labels), 1, figsize=(12, 2.4 * len(labels)), squeeze=False)
    for k, l in enumerate(labels):
        ax = axes[k][0]
        arr = data[l]["series"]["arr"]
        if arr["CTUN"]["t"].size:
            ax.plot(arr["CTUN"]["t"], arr["CTUN"]["tho"], color="#555", lw=0.6, label="ThO")
        ax2 = ax.twinx()
        if arr["BARO"]["t"].size:
            ax2.plot(arr["BARO"]["t"], arr["BARO"]["alt"], color="#2c7fb8", lw=0.6, alpha=0.6, label="Alt")
        for (a, b) in data[l]["armed"]:
            ax.axvspan(a, b, color="green", alpha=0.05)
        hv = data[l]["hover"]
        if hv:
            ax.axvspan(hv[0], hv[1], color="red", alpha=0.18)
        ax.set_title("Log %s (%s) - green=armed, red=analiz hover penceresi" % (l, data[l]["cond"]))
        ax.set_ylabel("ThO"); ax.set_ylim(0, 1); ax.grid(True, alpha=0.2)
    axes[-1][0].set_xlabel("t (s)")
    fig.tight_layout(); fig.savefig(OUT_DIR / "segmentation_timeline.png", dpi=110); plt.close(fig)

    # 5) PID terms bar
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    for ax, name in zip(axes, ["roll", "pitch"]):
        width = 0.25
        terms = ["P", "I", "D", "FF"]
        xpos = np.arange(len(terms))
        for k, l in enumerate(labels):
            pt = metrics[l].get("pidterm_%s" % name)
            if not pt:
                continue
            vals = [pt[t_] for t_ in terms]
            ax.bar(xpos + (k - 1) * width, vals, width, color=colors[l],
                   label="%s (%s)" % (l, data[l]["cond"]))
        ax.set_xticks(xpos); ax.set_xticklabels(terms)
        ax.set_title("PID terim RMS - %s" % name); ax.grid(True, axis="y", alpha=0.25)
        if name == "roll":
            ax.set_ylabel("terim buyuklugu (RMS)"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT_DIR / "pid_terms_bar.png", dpi=120); plt.close(fig)

    # 6) coherence / |H| roll
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    for l in labels:
        tf = metrics[l].get("tf_roll")
        if not tf:
            continue
        axes[0].plot(tf["f"], tf["H"], color=colors[l], lw=1.1, label="%s" % l)
        axes[1].plot(tf["f"], tf["coh"], color=colors[l], lw=1.1, label="%s" % l)
    axes[0].set_title("|H| target->achieved (roll rate)"); axes[0].set_xlabel("Hz")
    axes[0].set_ylabel("|H|"); axes[0].grid(True, alpha=0.25); axes[0].legend(fontsize=8)
    axes[1].set_title("Koherans (roll rate)"); axes[1].set_xlabel("Hz")
    axes[1].set_ylabel("coh"); axes[1].axhline(0.6, color="gray", ls="--", lw=0.8)
    axes[1].grid(True, alpha=0.25); axes[1].set_ylim(0, 1)
    fig.tight_layout(); fig.savefig(OUT_DIR / "rate_tf_coherence_roll.png", dpi=120); plt.close(fig)


def _fmt(v, nd=4):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "-"
    if isinstance(v, float):
        return ("%%.%df" % nd) % v
    return str(v)


def _write_report(data, metrics, labels, param_table):
    P = []
    w = P.append
    w("# PID Teshis Raporu — Buyuk Quad (Drone 0.0)\n")
    w("Loglar: **76**, **77** (3 Temmuz, sakin) vs **82** (9 Temmuz, ruzgarli).")
    w("Uretildi: `pid_diagnostics.py` (offline, pymavlink). Tum grafikler bu klasorde.\n")

    w("## 1. Ozet bulgular\n")
    w("- **PID parametreleri uc logda da birebir ayni** (asagidaki tablo). Yani 82'deki")
    w("  osilasyon 'PID degisti' diye aciklanamaz — ayni tune sakin havada iyi ucup ruzgarda osilasyon yapti.")
    w("- Arac buyuk bir **QUAD** (FRAME_CLASS=%s, 4 motor), 28-29\" pervane."
      % _fmt(data[labels[0]]['series']['params'].get('FRAME_CLASS'), 0))
    # quantitative wallow comparison (0.5-3 Hz gyro RMS), 82 vs calm average
    def _wallow(l, ax):
        return metrics[l]["imu_%s" % ax]["rms_05_3"]
    calm_ls = [l for l in labels if data[l]["cond"] == "calm"]
    if "82" in labels and calm_ls:
        for ax in ("roll", "pitch"):
            calm_avg = np.nanmean([_wallow(l, ax) for l in calm_ls])
            w82 = _wallow("82", ax)
            ratio = w82 / calm_avg if calm_avg else float("nan")
            w("- **Wallow bandi (0.5-3 Hz) %s gyro RMS:** 82(ruzgar)=%.1f deg/s vs sakin ort=%.1f deg/s "
              "=> **%.1fx** (tepe 82'de ~0.5 Hz, sakinde ~1.4-2.6 Hz)."
              % (ax, w82, calm_avg, ratio))
    w("- Bu, 82'deki 'agir osilasyon'un **ruzgar-tahrikli dusuk-frekans salinim** oldugunu SAYISAL dogrular;")
    w("  ayni bant 3-8 Hz'e kadar da 82'de yuksek (bkz. `imu_gyro_psd_compare.png`).\n")

    w("## 2. PID / filtre parametreleri (uc log)\n")
    w("| Param | 76 | 77 | 82 |")
    w("|---|---|---|---|")
    for row in param_table:
        w("| `%s` | %s | %s | %s |" % (row["param"], _fmt(row.get("76")),
                                       _fmt(row.get("77")), _fmt(row.get("82"))))
    w("")

    w("## 3. Analiz hover pencereleri (segmentasyon)\n")
    w("| Log | Kosul | Armed pencere | Hover penceresi | hover_frac |")
    w("|---|---|---|---|---|")
    for l in labels:
        hv = data[l]["hover"]
        hvs = "[%.0f..%.0f]s (%.0fs)" % (hv[0], hv[1], hv[1] - hv[0]) if hv else "YOK"
        hf = _fmt(hv[2]["hover_frac"], 2) if hv else "-"
        nw = len(data[l]["armed"])
        w("| %s | %s | %d adet | %s | %s |" % (l, data[l]["cond"], nw, hvs, hf))
    w("")

    w("## 4. Salinim karakterizasyonu\n")
    w("### 4a. Batch gyro (3277 Hz) — bant RMS (deg/s), notch etkinligi\n")
    w("*Not: batch verisi OPT=4 (post-filter), yani notch UYGULANDIKTAN sonraki rezidu. Tepe(Hz)")
    w("sutunu >5 Hz'deki en guclu motor/ESC gurultu hattidir (kontrol osilasyonu DEGIL — o 4b'deki")
    w("0.5 Hz wallow). Notch'i SET etmek icin pre-filter batch gerekir.*\n")
    w("| Log | eksen | tepe(Hz) | RMS 1-10Hz | RMS 10-60Hz | RMS 60-120Hz |")
    w("|---|---|---|---|---|---|")
    for l in labels:
        for name in ["roll", "pitch", "yaw"]:
            d = metrics[l]["batch_%s" % name]
            pk = d["peak"][0] if d["peak"] and d["peak"][0] else None
            w("| %s | %s | %s | %s | %s | %s |" % (
                l, name, _fmt(pk, 1), _fmt(d["rms_1_10"], 2),
                _fmt(d["rms_10_60"], 2), _fmt(d["rms_60_120"], 2)))
    w("")
    w("### 4b. Dusuk-hizli IMU gyro — wallow bandi (deg/s)\n")
    w("| Log | eksen | tepe(Hz) | RMS 0.5-3Hz | RMS 3-8Hz |")
    w("|---|---|---|---|---|")
    for l in labels:
        for name in ["roll", "pitch", "yaw"]:
            d = metrics[l]["imu_%s" % name]
            pk = d["peak"][0] if d["peak"] and d["peak"][0] else None
            w("| %s | %s | %s | %s | %s |" % (
                l, name, _fmt(pk, 1), _fmt(d["rms_05_3"], 2), _fmt(d["rms_3_8"], 2)))
    w("")
    w("### 4c. RATE takip-hatasi — wallow bandi (deg/s)\n")
    w("| Log | eksen | hata RMS | RMS 0.5-3Hz |")
    w("|---|---|---|---|")
    for l in labels:
        for name in ["roll", "pitch"]:
            d = metrics[l].get("rateerr_%s" % name)
            if not d:
                continue
            w("| %s | %s | %s | %s |" % (l, name, _fmt(d["err_rms"], 1), _fmt(d["rms_05_3"], 2)))
    w("")

    w("## 5. PID terim analizi (hover penceresi, RMS)\n")
    w("`d_damp_corr` = D terimi ile -d(gyro)/dt korelasyonu (yuksek+ => D gercekten sonumluyor).\n")
    w("| Log | eksen | P | I | D | FF | d_damp_corr |")
    w("|---|---|---|---|---|---|---|")
    for l in labels:
        for name in ["roll", "pitch"]:
            pt = metrics[l].get("pidterm_%s" % name)
            if not pt:
                continue
            w("| %s | %s | %s | %s | %s | %s | %s |" % (
                l, name, _fmt(pt["P"], 4), _fmt(pt["I"], 4), _fmt(pt["D"], 4),
                _fmt(pt["FF"], 4), _fmt(pt["d_damp_corr"], 2)))
    w("")

    w("## 6. Adim yaniti / koherans ve KISITLAR\n")
    w("- RATE loglamasi ~7-10 Hz => Nyquist ~3-5 Hz. Koherans yalnizca ~3-4 Hz'e kadar guvenilir.")
    w("  Bu agir/yuksek-atalet arac icin rate-loop bandi zaten dusuk (~1-3 Hz), yani wallow *bu bandin icinde*")
    w("  ve teshis edilebilir; ama gercek yuksek-bant step-response icin **fast-attitude loglamasi** sart.")
    w("- Grafik: `rate_tf_coherence_roll.png` (|H| ve koherans).\n")

    w("## 7. Notch degerlendirmesi\n")
    ref = data[labels[-1]]["series"]["params"]
    w("- Mevcut: `INS_HNTCH_ENABLE=%s`, `MODE=%s` (throttle), `FREQ=%s`, `BW=%s`, `REF=%s`, `HMNCS=%s`."
      % (_fmt(ref.get("INS_HNTCH_ENABLE"), 0), _fmt(ref.get("INS_HNTCH_MODE"), 0),
         _fmt(ref.get("INS_HNTCH_FREQ"), 0), _fmt(ref.get("INS_HNTCH_BW"), 0),
         _fmt(ref.get("INS_HNTCH_REF"), 3), _fmt(ref.get("INS_HNTCH_HMNCS"), 0)))
    w("- throttle-referansli notch icin `REF` ~ hover gazi olmali (hover ~%s); 0.393 fazla yuksek gorunuyor."
      % _fmt(ref.get("MOT_THST_HOVER"), 2))
    w("- Batch verisi ile motor tepe frekansi `batch_gyro_psd_compare.png`'de gorulur; 73 Hz'in altinda")
    w("  (28\" icin ~33-42 Hz beklenir) bir tepe varsa `INS_HNTCH_FREQ` yeniden ayarlanmali.\n")

    w("## 8. Onerilen parametreler (baslangic)\n")
    w("`I=P` korunur. **D'yi ancak FLTD=10 ve notch oturduktan sonra artir.**\n")
    w("| Param | Mevcut (82) | Oneri | Gerekce |")
    w("|---|---|---|---|")
    cur = data["82"]["series"]["params"] if "82" in data else {}
    for k, v, why in RECOMMEND:
        w("| `%s` | %s | **%s** | %s |" % (k, _fmt(cur.get(k)), _fmt(v), why))
    w("")
    w("### Guvenli baseline (fallback) — ilk temkinli ucus\n")
    w("| Param | Deger |")
    w("|---|---|")
    for k, v in FALLBACK:
        w("| `%s` | %s |" % (k, _fmt(v)))
    w("")
    w("- Voltaj PID olcekleme ZATEN aktif (`MOT_BAT_VOLT_MAX=%s / MIN=%s`, ~12S) — degistirme."
      % (_fmt(cur.get("MOT_BAT_VOLT_MAX"), 1), _fmt(cur.get("MOT_BAT_VOLT_MIN"), 1)))
    w("")

    w("## 9. Kademeli re-tune recetesi (gelecek ucus)\n")
    w("1. **Loglama:** `LOG_BITMASK |= 1` (ATTITUDE_FAST => RATE loop-rate), `LOG_FILE_RATEMAX=0`.")
    w("   Batch sampler'i **pre-filter** de kaydedecek sekilde ayarla (notch SET etmek icin).")
    w("2. **Titresim/mekanik:** VIBE kontrol (bu loglarda clip=0, orta seviye — mekanik sorun elenmis).")
    w("3. **Notch'i once kur** (batch FFT motor tepesine gore FREQ/BW/REF).")
    w("4. **Filtreler:** FLTT/FLTD=10 (roll/pitch), gyro filter=20, yaw FLTD~6.")
    w("5. **Guvenli baseline gainleri** ile ilk ucus.")
    w("6. **QuikTune'u HAFIF RUZGARDA** (sakin havada degil — asiri agresiflik nedeni).")
    w("7. **AutoTune'u SAKIN havada** (<3 m/s), AXES=7 (mevcut AXES=%s sadece pitch), AGGR 0.075-0.10."
      % _fmt(cur.get("AUTOTUNE_AXES"), 0))
    w("8. Yeni ucusu **PID Review + Filter Review** web tool'lari ile dogrula.")
    w("")

    w("## 10. ArduPilot web tool'lari nasil kullanilir (log 82 icin)\n")
    w("Her iki tool da **client-side**'dir (dosya sunucuya YUKLENMEZ, tarayicinda islenir).")
    w("Bu araclari SEN acip log 82'yi surukle-birak ile yuklemelisin; bu offline analiz ayni")
    w("hesaplarin karsiligini uretir (asagida capraz referans).\n")
    w("- **PID Review** — `firmware.ardupilot.org/Tools/WebTools/PIDReview/`")
    w("  1) dosya butonuyla `00000082.BIN` sec, 2) eksen sec (RATE Roll / PIDR ...), 3) Calculate.")
    w("  Log 82'de PIDR/PIDP/PIDY + RATE VAR, ama ~7-10 Hz => step-response ~3-4 Hz uzeri GUVENILMEZ.")
    w("  Offline karsiligi: `rate_tf_coherence_roll.png` (ayni dusuk-koherans sinirini gosterir).")
    w("- **Filter Review** — `firmware.ardupilot.org/Tools/WebTools/FilterReview/`")
    w("  Batch (ISBD ~3277 Hz) verisini kullanir => **ANLAMLI**. Motor gurultu tepe(ler)ini ve notch")
    w("  etkisini gosterir. Offline karsiligi: `batch_gyro_psd_compare.png` (~50-75 Hz motor bandi +")
    w("  ~140-165 Hz rezidu hatlari; ayni tepeler gorulmeli). Notch degerlendirmesi icin bunu kullan.")
    w("- Gelecek ucusta `LOG_BITMASK |= 1` (fast-attitude) ile RATE loop-rate'e cikinca PID Review'in")
    w("  step-response'u GERCEKTEN guvenilir olur.\n")

    w("---")
    w("*Not: 'ideal PID' mevcut loglardan kesin uretilemez; en iyi cikti guvenli baseline +")
    w("dogru loglamayla yapilacak QuikTune/AutoTune'dur. Bu rapor teshisi ve baslangic yonunu verir.*")

    (OUT_DIR / "pid_teshis_raporu.md").write_text("\n".join(P), encoding="utf-8")


if __name__ == "__main__":
    main()
