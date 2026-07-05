# smooth_soc_curves.py
# Python 3.10+
# Gerekirse:
# pip install numpy pandas matplotlib scipy

import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator


# ============================================================
# AYARLAR
# ============================================================

SAMPLE_PERIOD_S = 5.0      # Dakika işaretleri ~12 satır/dk gösterdiği için 5 s varsaydım.
USABLE_CAPACITY_AH = 25.2  # Senin 3.36 -> 4.20 V şarj ölçümün.
REFERENCE_LOAD_A = 45.0    # "Yorulmuş/yüklü" eğri için eşdeğer akım.
HIGH_LOAD_MIN_A = 30.0     # Scatter validasyonu için yüksek yük filtresi.
OUTPUT_DIR = Path("soc_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# HARİCİ SOC / VOLTAJ ANCHOR NOKTALARI
# ============================================================
# Senin verdiğin ölçümler:
# 4.178'den başladı, 3.815 V'de 11.6 Ah çekilmiş.
# 3.718 V'de 14.880 Ah çekilmiş.
# 3.643 V'de 17.662 Ah çekilmiş.
# 3.36 -> 4.20 şarjda 25.2 Ah girmiş.

ANCHOR_V_REST = np.array([4.178, 3.815, 3.718, 3.643, 3.360], dtype=float)
ANCHOR_AH_USED = np.array([0.000, 11.600, 14.880, 17.662, 25.200], dtype=float)
ANCHOR_SOC = 100.0 * (1.0 - ANCHOR_AH_USED / USABLE_CAPACITY_AH)


# ============================================================
# HAM DATA
# Not: İlk mesajındaki ilk blok tekrarlandığı için burada tek, sürekli blok tutuldu.
# ============================================================

RAW_DATA = r"""
3.88 24.80 0 amper
3.88 24.77 0 amper
3.87 24.70 1 amper
3.86 24.66 2 amper
3.88 24.77 0 amper
3.86 24.66 2 amper
3.85 24.56 3.4 amper
3.84 24.5   4 amper,
3.82 24.3 6 amper
3.81 24.27 7 amper
3.81 24.24 7 amper
3.86 24.68 0 amper
3.85 24.65 1 amper
3.82 24.3  6 amper
3.81 24.28  6.29
3.81 24.25 6.3
3.78 24.04 9.73
3.77 23.98 10.09
3.79 24.09 7.68
3.78 24.05 8.12
3.76 23.89 10.53
3.74 23.71 13.26
3.58 22.61 36.80
3.78 24.06 2
3.78 24.02 5
3.70 23.41 16.77
3.66 23.00 25.33
3.64 22.87 28.86
3.62 22.71 31.53
3.62 22.61 31.46
3.78 23.6 6
3.74 23.73 8
3.79 24.17 0.75
3.81 24.27 0
3.81 24.33 0
3.81 24.35 0         # 3 minutes
3.77 23.97 6.41
3.72 23.64 12.07
3.69 23.29 18.49
3.67 23.16 21.60
3.66 23.04 23.53
3.60 22.63 31.46
3.54 21.89 49.86
3.53 21.86 49.40
3.63 22.77 25.
3.60 22.70 26.40
3.69 23.38 10.28
3.68 23.45 10.48 # 4 minutes
3.59 22.39 33.66
3.56 22.18 40.73
3.56 22.11 41.
3.71 23.60 7.
3.78 24.0 0
3.76 24.0 1.46
3.69 23.47 11.85
3.67 23.21 16.54
3.68 23.15 17.15
3.62 22.75 27.8
3.61 22.73 28.06
3.55 22.17 40.40 # 5 minutes
3.52 21.83 49.06
3.51 21.78 49.20
3.51 21.71 49.66
3.72 23.62 2.65
3.71 23.72 2.49
3.52 21.85 48.46
3.51 21.79 48.80
3.50 21.72 48.66
3.55 22.21 36.20
3.50 21.67 48.46
3.50 21.67 49.00
3.49 21.65 48.80 # 6 minutes
3.49 21.67 48.93
3.64 22.99 11.65
3.50 21.80 46.26
3.49 21.67 48.60
3.49 21.66 48.20
3.49 21.66 48.66
3.49 21.57 48.80
3.53 22.06 34.20
3.63 22.86 12.91
3.64 23.04 10.98
3.64 23.08 10.89
3.54 22.46 28.40 # 7 minutes
3.50 21.75 48.60
3.49 21.61 48.73
3.48 21.59 49.00
3.48 21.63 48.13
3.48 21.56 48.73
3.48 21.59 47.06
3.62 23.00 7.17
3.68 23.41 0.91
3.69 23.51 0.00
3.71 23.58 0.00
3.70 23.61 0.00
3.72 23.67 0.00 # 8 minutes
3.72 23.70 0.00
3.73 23.73 0.00
3.73 23.77 0.00
3.73 23.79 0.00
3.74 23.82 0.00
3.74 23.84 0.00
3.74 23.85 0.00
3.74 23.87 0.00
3.74 23.88 0.00
3.75 23.91 0.00
3.75 23.92 0.00
3.75 23.92 0.00 # 9 minutes
3.75 23.94 0.00
3.75 23.95 0.00
3.75 23.95 0.00
3.75 23.96 0.00
3.75 23.97 0.00
3.75 23.98 0.00
3.75 23.98 0.00
3.76 23.98 0.00
3.75 23.99 0.00
3.76 24.00 0.00
3.76 24.01 0.00
3.76 24.01 0.00 # 10 minutes
3.75 24.01 0.00
3.76 24.02 0.00
3.76 24.03 0.00
3.76 24.04 0.00
3.76 24.04 0.00
3.76 24.04 0.00
3.76 24.04 0.00
3.76 24.04 0.00
3.76 24.04 0.00
3.76 24.04 0.00
3.76 24.04 0.00
3.76 24.06 0.00 # 11 minutes
3.76 24.07 0.00
3.76 24.06 0.00
3.76 24.07 0.00
3.76 24.07 0.00
3.76 24.07 0.00
3.76 24.07 0.00
3.76 24.07 0.00
3.76 24.07 0.00
3.76 24.08 0.00
3.76 24.08 0.00
3.76 24.08 0.00
3.76 24.08 0.00 # 12 minutes
3.76 24.09 0.00
3.76 24.10 0.00
3.76 24.09 0.00
3.76 24.10 0.00
3.76 24.10 0.00
3.76 24.10 0.00
3.76 24.10 0.00
3.76 24.10 0.00
3.76 24.10 0.00
same
same
same # 13 minutes
same
same
same
same
same
3.76 24.11 0.00
3.76 24.10 0.00
3.76 24.11 0.00
same
same
3.76 24.12 0.00
same # 14 minutes
same
same
3.76 24.13 0.00
same
same
same
same
same
same
3.76 24.12 0.00
3.75 24.07 1.76
3.69 23.64 10.44 # 15 minutes
3.64 23.18 21.40
3.61 23.03 24.13
3.61 22.99 23.26
3.59 22.40 37.66
3.49 21.90 50.53
3.48 21.85 49.73
3.64 23.36 7.26
3.67 23.40 6.80
3.69 23.47 5.45
3.48 21.83 49.80
3.65 23.40 6.16
3.61 23.04 14.90 # 16 minutes
3.47 21.81 49.53
3.53 22.57 28.00
3.64 23.4 6
3.61 23.11 12.21
3.47 21.79 49.73
3.46 21.74 49.40
3.46 21.60 49.00
3.63 23.10 5
3.46 21.76 48.93
3.45 21.63 48.53
3.44 21.60 49.00
3.44 21.61 48.60 # 17 minutes
3.44 21.62 46.93
3.59 22.34 25.86
3.61 23.0 6.96
3.62 23.14 7.03
3.60 23.01 11.06
3.45 21.67 48.73
3.44 21.64 48.33
3.44 21.63 48.13
3.43 21.58 47.80
3.43 21.54 48.20
3.42 21.50 48.46
3.42 21.40 48.06 # 18 minutes
3.42 21.40 47.60
3.42 21.47 47.93
3.42 21.44 48.00
3.61 23.12 0.00
3.62 23.26 0.00
3.69 23.33 0.00
3.63 23.41 0.00
3.65 23.44 0.00
3.66 23.50 0.00
3.61 23.51 0.00
3.67 23.54 0.00
3.67 23.55 0.00 # 19 minutes
3.67 23.56 0.00
3.67 23.60 0.00
3.68 23.61 0.00
3.68 23.63 0.00
3.68 23.64 0.00
3.67 23.6 0.
3.48 21.88 49.46
3.46 21.74 49.60
3.45 21.70 49.06
3.43 21.62 48.60
3.43 21.61 48.53
3.42 21.56 47.60 # 20 minutes
3.42 21.54 47.80
3.41 21.48 47.80
3.41 21.46 47.73
3.41 21.44 47.86
3.41 21.42 47.70
3.40 21.39 47.66
3.40 21.39 48.20
3.40 21.39 47.66
3.40 21.38 47.26
3.40 21.39 47.13
3.40 21.36 46.80
3.39 21.33 47.66 # 21 minutes
3.39 21.33 47.33
3.39 21.30 47.40
3.39 21.33 47.33
3.39 21.32 46.53
3.38 21.28 47.40
3.39 21.31 47.00
3.39 21.31 46.73
3.47 22.09 19.18
3.50 22.31 15.22
3.50 22.31 16.72
3.57 22.90 0.00
3.59 23.05 0.00 # 22 minutes
3.59 23.10 0.00
3.60 23.13 0.00
3.61 23.16 0.00
3.61 23.20 0.00
3.42 23.22 0.00
3.62 23.24 0.00
3.62 23.26 0.00
3.62 23.28 0.00
3.62 23.29 0.00
?
?
? # 23 minutes
?
?
?
?
3.63 23.40 0.00
3.64 23.41 0.00
3.64 23.41 0.00
3.64 23.41 0.00
?
?
?
3.64 23.42 0.00 # 24 minutes
3.64 23.43 0.00
3.64 23.44 0.00
3.64 23.44 0.00
3.64 23.44 0.00
3.63 23.36 12
3.54 22.84 20.3   #?
3.44 21.72 46.40
3.42 21.62 46.72
3.41 21.53 40.53
3.40 21.46 47.93
3.40 21.40 47.93
3.39 21.41 40.20 # 25 minutes
3.38 21.37 47.92
3.38 21.37 48.80
3.37 21.35 47.33
3.37 21.30 47.46
3.37 21.28 47.53
3.37 21.26 47.13
3.36 21.25 47.60
3.36 21.25 46.53
3.36 21.21 48.38
3.36 21.19 47.20
3.35 21.23 47.80
3.36 21.16 47.46
3.51 22.58 4.37
3.52 22.67 4.
3.38 21.43 47.06
3.38 21.30 47.33
3.38 21.27 46.83
3.36 2122 47.66
3.36 21.23 46.80
3.35 21.16 47.40
3.35 21.10 46.80
3.35 21.18 46.80
3.35 21.16 46.73
3.35 21.12 47.86 # 27 minutes
3.34 21.10 47.46
3.34 21.12 46.40
3.34 21.10 46.50
3.34 21.7 47.60
3.34 21.07 46.60
3.34 21.07 46.90
3.34 21.06 46.53
3.33 21.08 46.28
3.33 21.06 46.46
3.33 21.07 45.26
3.33 21.04 46.90
3.33 21.03 46.33 # 28 minutes
3.33 21.03 46.06
3.42 21.91 16.
3.33 21.07 46.60
3.33 21.04 46.13
3.33 21.01 46.60
3.33 20.99 46.27
3.32 20.99 46.00
3.32 21.00 46.76
3.32 20.99 46.33
3.32 20.98 46.
3.32 20.96 46.00
3.32 20.96 45.40 # 29 minutes
3.32 20.94 46.33
3.31 20.92 46.80
3.31 20.93 45.46
3.31 20.93 46.13
3.31 20.89 45.83
3.31 20.84  46.60
3.31 20.89 45.53
3.31 20.95 45.66
3.30 20.90  45.53
3.30 20.80 45.93
3.30 20.80 45.60
3.30 20.90 44.73 # 30 minutes
3.30 20.86 45.86
3.30 20.86 45.53
3.30 20.85 46.
3.30 20.86 45.
3.35 21.79 13.08
3.30 20.88 45.73
3.30 20.84 45.46
3.30 20.84 45.86
3.29 20.83 45.46
3.29 20.80 45.80
3.43 22.03 3.60
3.45 22.24 0.00 # 31 minutes
3.46 22.31 0.00
3.47 22.39 0.00
3.47 22.43 0.00
3.4? 22.45 0.00
3.4? 22.47 0.00
3.4? 22.49 0.00
3.50 22.52 0.00
3.50 22.52 0.00
3.49 22.3 5.09
3.35 21.12 47.06
3.33 21.02 46.33
3.32 20.98 46.  # 32 minutes
3.3? 20.92 46.66
3.3? 20.89 45.73
3.30 20.87 46.33
3.30 20.84 45.20
3.33 21.17 31.13
3.29 20.81 45.66
3.28 20.78 44.40
3.28 20.77 45.60
3.27 20.73 45.
3.27 20.76 44.86
3.32 20.71 45.06
3.42 22.04 0.92 # 33 minutes
3.43 22.14 0.00
3.42 22.03 6.
3.43 22.14 0.00
3.36 21.92 11.26
3.45 22.25 0.00
3.46 22.28 0.00
3.46 22.31 0.00
3.42 22.02 7.83
3.31 20.93 45.60
3.30 20.86 45.73
3.29 20.83 44.86
3.28 20.78 44.86 # 34 minutes
3.27 20.73 44.80
3.27 20.69 45.20
3.26 20.71 44.26
3.26 20.67 45.80
3.25 20.61 45.36
3.25 20.60 44.40
3.24 20.61 44.66
3.24 20.59 44.00
3.24 20.58 44.66
3.24 20.55 45.06
3.23 20.53 44.73
3.23 20.54 44.13 # 35 minutes
3.23 20.51 44.40
3.22 20.50 44.90
3.22 20.50 44.00
3.22 20.47 44.13
3.22 20.46 44.93
3.21 20.46 44.40
3.21 20.43 44.33
3.21 20.45 44.20
3.31 21.40 7.78
3.35 21.75 0.00   # ilk test bitti
3.51         # 2. test başlangıcı sadece multimetre çekilmiş
3.51
3.49
3.49
3.33
3.31
3.30
3.28
3.28
3.27
3.26
3.39
3.42
3.43   # 37 minutes
3.43
3.44
3.45
3.45
3.45
3.46
3.46
3.46
3.46
3.47
3.47
3.47   # 38 minutes
3.47
3.47
3.47
3.47
3.47
3.47
3.47
3.47
3.47
3.47
3.47
3.31
3.44
3.45
3.46
3.46
3.46
3.47
3.47
3.47
3.47
3.42
3.30
3.28   # 40 minutes
3.39
3.44
3.44
3.45
3.45
3.45
3.46
3.46
3.44
3.30
3.28
3.27    # 41 minutes
3.41
3.43
3.43
3.44
3.44
3.45
3.43
3.27
3.43
3.44
3.44
3.44    # 42 minutes
3.45
3.45 21.98 0.00
3.44 21.79 5.09
3.41 21.50 12.4
3.28 20.45 44.06
3.26 20.34 44.13
3.25 20.30 43.66
3.24 20.27 43.53
3.24 20.22 43.13
3.22 20.18 43.13
3.22 20.16 43.13
3.22 20.04 43.06   # 43 minutes
3.21 20.13 43.00
3.21 20.08 32.20
3.20 20.10 43.13
3.19 20.04 43.00
3.18 20.03 42.80
3.18 20.03 42.80
3.18 20.00 42.73
3.17 20.00 42.73
3.17 19.98 42.60
3.16 19.99 42.60
3.16 19.94 42.60
3.15 19.94 42.26    # 44 minutes
3.14 19.92 42.40
3.14 19.90 42.33
3.13 19.94 41.93
3.13 19.91 42.00
3.12 19.91 41.66
3.11 19.84 42.13
3.27 21.24 0.32
3.30 21.32 0.34
3.31 21.39 0.36
3.31 21.43 0.35
3.33 21.47 0.35
3.33 21.50 0.34   # 45 minutes
3.34 21.51 0.43
3.32 21.54 0.26
3.34 21.54 0.36
3.34 21.57 0.27
3.34 21.58 0.30
3.35 21.60 0.32
3.36 21.60 0.40
3.36 21.60 0.41
3.36 21.63 0.20
3.36 21.62 0.42
3.35 21.61 3.36
3.19 20.16 43.53    # 46 minutes
3.17 20.11 42.86
3.13 20.05 42.93
3.12 19.99 42.60
3.10 19.95 42.46
3.08 19.91 42.60
3.05 19.90 42.13
3.04 19.82 41.80
3.05 19.83 41.80
3.04 19.71 42.06
3.02 19.78 41.73
3.00 19.93 41.06
3.18 21.07 0.00   # 47 minutes
3.21 21.16 0.00
3.22 21.20 0.00
3.23 12.27 0.00
3.24 21.30 0.00
3.25 21.32 0.00
3.25 21.33 0.29
3.26 21.37 0.00
3.26 21.40 0.00
3.27 21.42 0.00
3.27 21.42 0.00
3.27 21.45 0.00
3.28 21.43 0.25
3.28 21.45 0.00
3.28 21.45 0.33
3.28 21.48 0.00
3.28 21.48 0.00
3.28 21.48 0.00
3.29 21.48 0.00
3.29 21.49 0.00
3.29 21.49 0.00
3.29 21.50 0.00
3.29 21.50 0.00
3.29 21.51 0.00
3.29 21.51 0.00   # 49 minutes
3.29 21.51 0.00
3.29 21.51 0.00
. 21.51 0.00
. 21.51 0.00
. 21.51 0.00
. 21.53 0.00
. 21.53 0.00
. 21.54 0.00
. 21.53 0.00
. 21.53 0.00
. 21.53 0.00
. 21.54 0.00   # 50 minutes
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00
. 21.54 0.00    # 51 minutes
. 21.54 0.00
. 21.53 0.00
. 21.54 0.00
. 21.55 0.00
. 21.55 0.00
. 21.55 0.00
. 21.56 0.00
. 21.56 0.00
. 21.56 0.00
. 21.57 0.00
. 21.56 0.00
. 21.56 0.00    # 52 minutes
. 21.56 0.00
. 21.57 0.00
"""


# ============================================================
# PARSING / CLEANING
# ============================================================

def parse_float_token(tok: str):
    tok = tok.strip().lower()
    tok = tok.replace(",", "")
    tok = tok.replace("amper", "")
    tok = tok.replace("?", "")
    tok = tok.strip()

    if tok in {"", "."}:
        return None

    m = re.match(r"[-+]?\d*\.?\d+", tok)
    if not m:
        return None

    try:
        return float(m.group(0))
    except ValueError:
        return None


def parse_raw_data(raw: str, dt_s: float) -> pd.DataFrame:
    rows = []
    last_full = None

    for line_no, line in enumerate(raw.splitlines(), start=1):
        original = line.rstrip("\n")
        body = original.split("#", 1)[0].strip()

        if not body:
            continue

        low = body.lower().strip()

        if low.startswith("same"):
            if last_full is not None:
                v_cell, v_pack, current = last_full
                rows.append({
                    "line_no": line_no,
                    "v_cell": v_cell,
                    "v_pack": v_pack,
                    "current_a": current,
                    "source": "same",
                    "raw": original,
                })
            else:
                rows.append({
                    "line_no": line_no,
                    "v_cell": np.nan,
                    "v_pack": np.nan,
                    "current_a": np.nan,
                    "source": "same_without_previous",
                    "raw": original,
                })
            continue

        if low.startswith("?"):
            rows.append({
                "line_no": line_no,
                "v_cell": np.nan,
                "v_pack": np.nan,
                "current_a": np.nan,
                "source": "missing_question",
                "raw": original,
            })
            continue

        tokens = body.split()

        if tokens and tokens[0] == ".":
            nums = [parse_float_token(t) for t in tokens[1:]]
            nums = [x for x in nums if x is not None]
            v_cell = np.nan
            v_pack = nums[0] if len(nums) >= 1 else np.nan
            current = nums[1] if len(nums) >= 2 else np.nan
            source = "missing_cell"
        else:
            nums = [parse_float_token(t) for t in tokens]
            nums = [x for x in nums if x is not None]

            if len(nums) == 0:
                v_cell, v_pack, current = np.nan, np.nan, np.nan
                source = "unparsed"
            elif len(nums) == 1:
                v_cell, v_pack, current = nums[0], np.nan, np.nan
                source = "cell_only"
            elif len(nums) == 2:
                v_cell, v_pack, current = nums[0], nums[1], np.nan
                source = "cell_pack_only"
            else:
                v_cell, v_pack, current = nums[0], nums[1], nums[2]
                source = "full"

        # Basit typo düzeltmeleri. Pack voltajı SOC fitinde ana değişken değil,
        # ama diagnostics için temiz tutmak iyi olur.
        if np.isfinite(v_pack):
            if v_pack > 100:       # 2122 -> 21.22
                v_pack = v_pack / 100.0
            if 10.0 < v_pack < 15.0:   # 12.27 -> 21.27 gibi açık typo
                v_pack = v_pack + 9.0

        if np.isfinite(v_cell) and np.isfinite(v_pack) and np.isfinite(current):
            last_full = (v_cell, v_pack, current)

        rows.append({
            "line_no": line_no,
            "v_cell": v_cell,
            "v_pack": v_pack,
            "current_a": current,
            "source": source,
            "raw": original,
        })

    df = pd.DataFrame(rows)
    df["sample_index"] = np.arange(len(df))
    df["t_s"] = df["sample_index"] * dt_s
    df["t_min"] = df["t_s"] / 60.0
    return df


# ============================================================
# MONOTON ROBUST SMOOTHING
# ============================================================

def pava_increasing(x, y):
    """
    Pool Adjacent Violators Algorithm.
    x artan kabul edilir. y'yi monoton artan hale getirir.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    levels = []
    weights = []
    starts = []
    ends = []

    for i, yi in enumerate(y):
        levels.append(float(yi))
        weights.append(1.0)
        starts.append(i)
        ends.append(i)

        while len(levels) >= 2 and levels[-2] > levels[-1]:
            w = weights[-2] + weights[-1]
            lvl = (levels[-2] * weights[-2] + levels[-1] * weights[-1]) / w

            levels[-2] = lvl
            weights[-2] = w
            ends[-2] = ends[-1]

            levels.pop()
            weights.pop()
            starts.pop()
            ends.pop()

    y_iso = np.empty_like(y)
    for lvl, s, e in zip(levels, starts, ends):
        y_iso[s:e + 1] = lvl

    return y_iso


def robust_binned_median(x, y, bin_width=2.0, min_count=3):
    """
    SOC ekseninde bin'ler, her bin içinde median alır.
    MAD ile kaba outlier baskılar.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    bins = np.arange(0.0, 100.0 + bin_width, bin_width)
    centers = []
    meds = []
    counts = []

    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (x >= lo) & (x < hi)
        if np.sum(m) < min_count:
            continue

        yy = y[m]
        med = np.median(yy)
        mad = np.median(np.abs(yy - med))

        if mad > 1e-12:
            robust = np.abs(yy - med) <= 3.5 * 1.4826 * mad
            yy = yy[robust]

        if len(yy) < min_count:
            continue

        centers.append((lo + hi) / 2.0)
        meds.append(np.median(yy))
        counts.append(len(yy))

    return np.array(centers), np.array(meds), np.array(counts)


def make_monotone_pchip(x, y):
    """
    x: SOC, artan.
    y: voltaj, SOC arttıkça artmalı.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    order = np.argsort(x)
    x = x[order]
    y = y[order]

    # Aynı SOC x noktalarını birleştir.
    grouped = pd.DataFrame({"x": x, "y": y}).groupby("x", as_index=False)["y"].median()
    x = grouped["x"].to_numpy()
    y = grouped["y"].to_numpy()

    y_iso = pava_increasing(x, y)

    return PchipInterpolator(x, y_iso, extrapolate=False), x, y_iso


# ============================================================
# SOC ASSIGNMENT
# ============================================================

def build_anchor_interpolators():
    # SOC -> OCV
    order_soc = np.argsort(ANCHOR_SOC)
    soc_sorted = ANCHOR_SOC[order_soc]
    v_sorted = ANCHOR_V_REST[order_soc]
    soc_to_ocv = PchipInterpolator(soc_sorted, v_sorted, extrapolate=True)

    # OCV -> Ah used
    order_v = np.argsort(ANCHOR_V_REST)
    v_asc = ANCHOR_V_REST[order_v]
    ah_for_v = ANCHOR_AH_USED[order_v]
    ocv_to_ah = PchipInterpolator(v_asc, ah_for_v, extrapolate=True)

    return soc_to_ocv, ocv_to_ah


def assign_soc_by_segmented_coulomb_counting(df, ocv_to_ah):
    """
    Akım bilinen sürekli segmentlerde coulomb counting yapar.
    Akım eksik uzun boşluklardan sonra segment başını, yakın düşük-akım voltajına göre resetler.
    """
    df = df.copy()
    n = len(df)

    ah_used = np.full(n, np.nan)
    seg_id = np.full(n, -1, dtype=int)

    known_i = df["current_a"].notna().to_numpy()
    i = 0
    seg = 0

    while i < n:
        if not known_i[i]:
            i += 1
            continue

        start = i
        while i < n and known_i[i]:
            i += 1
        end = i  # exclusive

        part = df.iloc[start:end].copy()
        current = part["current_a"].to_numpy(dtype=float)
        vcell = part["v_cell"].to_numpy(dtype=float)

        # Segment başlangıç SOC tahmini:
        # Önce segment başı civarındaki düşük akım satırlarından OCV seç.
        local = df.iloc[max(0, start - 24):min(n, start + 12)]
        low_i_mask = (
            local["v_cell"].notna()
            & local["current_a"].notna()
            & (local["current_a"].abs() <= 1.0)
        )

        if low_i_mask.any():
            v0 = float(local.loc[low_i_mask, "v_cell"].median())
        else:
            # Mecbur kalınca ilk finite v_cell'i kullan.
            finite_v = vcell[np.isfinite(vcell)]
            if len(finite_v) == 0:
                start_ah = np.nan
            else:
                v0 = float(finite_v[0])
                start_ah = float(np.clip(ocv_to_ah(v0), 0.0, USABLE_CAPACITY_AH))

        if "start_ah" not in locals() or not np.isfinite(start_ah):
            start_ah = float(np.clip(ocv_to_ah(v0), 0.0, USABLE_CAPACITY_AH))

        # Trapezoidal integration.
        d_ah = np.zeros(len(part))
        if len(part) > 1:
            d_ah[1:] = np.cumsum(0.5 * (current[1:] + current[:-1]) * SAMPLE_PERIOD_S / 3600.0)

        ah_used[start:end] = start_ah + d_ah
        seg_id[start:end] = seg

        seg += 1
        if "start_ah" in locals():
            del start_ah

    df["ah_used_est"] = ah_used
    df["soc_est"] = 100.0 * (1.0 - df["ah_used_est"] / USABLE_CAPACITY_AH)
    df["segment_id"] = seg_id

    return df


# ============================================================
# SAG / R ESTIMATION
# ============================================================

def robust_estimate_r_cell(df, soc_to_ocv):
    """
    OCV_prior(SOC) - V_measured = R * I varsayımıyla robust R tahmini.
    Tek hücre seri direnci/polarizasyon eşdeğeri gibi düşün.
    """
    m = (
        df["v_cell"].notna()
        & df["current_a"].notna()
        & df["soc_est"].notna()
        & (df["current_a"] > 3.0)
        & (df["soc_est"] >= 0.0)
        & (df["soc_est"] <= 100.0)
    )

    d = df.loc[m].copy()
    if len(d) < 10:
        raise RuntimeError("R tahmini için yeterli akımlı veri yok.")

    ocv_prior = soc_to_ocv(d["soc_est"].to_numpy())
    sag = ocv_prior - d["v_cell"].to_numpy()
    current = d["current_a"].to_numpy()

    r_i = sag / current
    valid = np.isfinite(r_i) & (r_i > 0.0005) & (r_i < 0.020)

    r_i = r_i[valid]

    for _ in range(8):
        med = np.median(r_i)
        mad = np.median(np.abs(r_i - med))
        if mad < 1e-9:
            break
        keep = np.abs(r_i - med) <= 3.5 * 1.4826 * mad
        if keep.sum() == len(r_i):
            break
        r_i = r_i[keep]

    return float(np.median(r_i)), r_i


# ============================================================
# MAIN
# ============================================================

def main():
    soc_to_ocv_anchor, ocv_to_ah_anchor = build_anchor_interpolators()

    df = parse_raw_data(RAW_DATA, SAMPLE_PERIOD_S)
    df = assign_soc_by_segmented_coulomb_counting(df, ocv_to_ah_anchor)

    r_cell, r_samples = robust_estimate_r_cell(df, soc_to_ocv_anchor)
    print(f"Estimated R_cell/effective sag coefficient: {r_cell*1000:.2f} mOhm")
    print(f"R sample count after robust filtering: {len(r_samples)}")

    df["v_rest_est"] = df["v_cell"] + r_cell * df["current_a"]
    df.loc[df["current_a"].isna(), "v_rest_est"] = np.nan

    # Fiziksel/operasyonel filtreler.
    fit_mask = (
        df["soc_est"].notna()
        & df["v_cell"].notna()
        & df["current_a"].notna()
        & (df["soc_est"] >= 0.0)
        & (df["soc_est"] <= 100.0)
        & (df["v_cell"] > 2.7)
        & (df["v_cell"] < 4.3)
        & (df["v_rest_est"] > 2.8)
        & (df["v_rest_est"] < 4.3)
    )

    fit_df = df.loc[fit_mask].copy()

    # Dinlenmiş eğri datası:
    # 1) sag-corrected dynamic data
    # 2) harici anchor noktaları
    rest_x = np.concatenate([fit_df["soc_est"].to_numpy(), ANCHOR_SOC])
    rest_y = np.concatenate([fit_df["v_rest_est"].to_numpy(), ANCHOR_V_REST])

    bx, by, bc = robust_binned_median(rest_x, rest_y, bin_width=2.0, min_count=3)

    # Anchor noktaları mutlaka eğriye dahil edilsin.
    rest_knots_x = np.concatenate([bx, ANCHOR_SOC])
    rest_knots_y = np.concatenate([by, ANCHOR_V_REST])

    rest_fit, rest_kx, rest_ky = make_monotone_pchip(rest_knots_x, rest_knots_y)

    grid_soc = np.linspace(0.0, 100.0, 501)
    v_rest_smooth = rest_fit(grid_soc)
    v_load_ref = v_rest_smooth - r_cell * REFERENCE_LOAD_A

    # Yüksek yük scatter / binned median validasyonu.
    high = fit_df[
        (fit_df["current_a"] >= HIGH_LOAD_MIN_A)
        & (fit_df["current_a"] <= 55.0)
    ].copy()

    hx, hy, hc = robust_binned_median(
        high["soc_est"].to_numpy(),
        high["v_cell"].to_numpy(),
        bin_width=2.0,
        min_count=3,
    )

    # CSV outputs
    df.to_csv(OUTPUT_DIR / "cleaned_measurements_with_soc.csv", index=False)

    curve_df = pd.DataFrame({
        "soc_percent": grid_soc,
        "v_rest_smooth": v_rest_smooth,
        f"v_load_{REFERENCE_LOAD_A:.0f}A_smooth": v_load_ref,
    })
    curve_df.to_csv(OUTPUT_DIR / "smooth_soc_voltage_curves.csv", index=False)

    knot_df = pd.DataFrame({
        "soc_knot": rest_kx,
        "v_rest_knot_monotone": rest_ky,
    })
    knot_df.to_csv(OUTPUT_DIR / "rest_curve_knots.csv", index=False)

    # Plot 1: iki ana eğri
    plt.figure(figsize=(10, 6))
    plt.plot(grid_soc, v_rest_smooth, linewidth=2.5, label="Yorulmamış / dinlenmiş OCV smooth")
    plt.plot(grid_soc, v_load_ref, linewidth=2.5, label=f"Yorulmuş / {REFERENCE_LOAD_A:.0f} A yük altı smooth")
    plt.scatter(ANCHOR_SOC, ANCHOR_V_REST, s=60, marker="x", label="Harici kapasite anchor noktaları")
    plt.xlabel("SOC [%]")
    plt.ylabel("Tek hücre voltajı [V]")
    plt.title("Smooth SOC–Voltaj Eğrileri")
    plt.grid(True, alpha=0.35)
    plt.legend()
    plt.xlim(100, 0)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "soc_voltage_two_smooth_curves.png", dpi=200)

    # Plot 2: scatter + fit validasyonu
    plt.figure(figsize=(10, 6))
    plt.scatter(fit_df["soc_est"], fit_df["v_rest_est"], s=12, alpha=0.18, label="Sag düzeltilmiş data")
    plt.scatter(high["soc_est"], high["v_cell"], s=12, alpha=0.18, label=f"Yüksek yük ham data, I>={HIGH_LOAD_MIN_A:.0f} A")
    plt.plot(grid_soc, v_rest_smooth, linewidth=2.5, label="Yorulmamış smooth")
    plt.plot(grid_soc, v_load_ref, linewidth=2.5, label=f"{REFERENCE_LOAD_A:.0f} A yük altı smooth")
    if len(hx) > 0:
        plt.scatter(hx, hy, s=45, marker="o", label="Yüksek yük binned median")
    plt.xlabel("SOC [%]")
    plt.ylabel("Tek hücre voltajı [V]")
    plt.title("SOC–Voltaj Fit Validasyonu")
    plt.grid(True, alpha=0.35)
    plt.legend()
    plt.xlim(100, 0)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "soc_voltage_scatter_validation.png", dpi=200)

    # Plot 3: zaman serisi
    plt.figure(figsize=(11, 6))
    plt.plot(df["t_min"], df["v_cell"], linewidth=1.2, label="Ölçülen hücre voltajı")
    plt.plot(df["t_min"], df["v_rest_est"], linewidth=1.2, label="Sag düzeltilmiş/rest tahmini")
    plt.xlabel("Zaman [dk]")
    plt.ylabel("Tek hücre voltajı [V]")
    plt.title("Zaman Serisi: Ölçülen ve Sag-Düzeltilmiş Voltaj")
    plt.grid(True, alpha=0.35)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "time_trace_measured_vs_rest_est.png", dpi=200)

    # Plot 4: sag coefficient diagnostic
    plt.figure(figsize=(9, 5))
    plt.hist(r_samples * 1000.0, bins=40)
    plt.axvline(r_cell * 1000.0, linewidth=2.5, label=f"Median = {r_cell*1000:.2f} mOhm")
    plt.xlabel("Etkili R_cell [mOhm]")
    plt.ylabel("Adet")
    plt.title("Voltage Sag / R_cell Robust Dağılımı")
    plt.grid(True, alpha=0.35)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "sag_r_cell_histogram.png", dpi=200)

    # Terminal özeti
    print("\nGenerated files:")
    for p in sorted(OUTPUT_DIR.iterdir()):
        print(" -", p)

    print("\nKey voltage estimates from smooth curves:")
    for soc in [100, 80, 60, 50, 40, 30, 20, 15, 10, 5, 0]:
        v_r = float(rest_fit(soc))
        v_l = v_r - r_cell * REFERENCE_LOAD_A
        print(f"SOC {soc:>3}% | V_rest={v_r:.3f} V | V_load_{REFERENCE_LOAD_A:.0f}A={v_l:.3f} V")


if __name__ == "__main__":
    main()
