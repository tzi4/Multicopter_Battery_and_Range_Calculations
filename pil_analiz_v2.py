#!/usr/bin/env python3
"""
Li-ion Solid State Pil SOC Analizi v2
=====================================
6S 27000 mAh Li-ion Solid State Batarya Karakterizasyonu

İyileştirmeler (v1'e göre):
  • Voltaja bağlı iç direnç R(V) — transition-based estimation
  • Sürekli coulomb counting (segment kırılması yok)
  • Basamak artefaktı olmayan pürüzsüz SOC eğrileri
  • Lineerlik analizi — hangi bölge lineer kabul edilebilir
  • Pratik uçuş planlama tablosu
  • Multimetre-only veriler de dahil

Kullanım:
    python3 pil_analiz_v2.py
"""

import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 200,
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
})

# Türkçe karakter desteği (varsa)
try:
    plt.rcParams["font.family"] = "DejaVu Sans"
except Exception:
    pass


# ============================================================
# CONFIGURATION
# ============================================================

SAMPLE_PERIOD_S = 5.0         # Her satır arası 5 saniye (kullanıcı onayladı)
USABLE_CAPACITY_AH = 25.2    # 3.36V → 4.20V şarjda ölçülen kapasite
NOMINAL_CAPACITY_AH = 27.0   # Nominal cell kapasitesi
REFERENCE_LOAD_A = 45.0      # Referans yük akımı (yüklü eğri için)
NUM_CELLS = 6                # 6S konfigürasyonu

OUTPUT_DIR = Path("soc_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---- Transition detection tuning ----
MIN_DELTA_I_FOR_TRANSITION = 8.0   # Minimum |ΔI| bir transition olarak sayılması için (A)
R_VALID_MIN = 0.0005               # Minimum geçerli R (Ω) — 0.5 mΩ
R_VALID_MAX = 0.025                # Maksimum geçerli R (Ω) — 25 mΩ

# ---- Linearity analysis ----
LINEARITY_WINDOW_PCT = 12.0  # Kayan pencere genişliği (SOC % cinsinden)
LINEARITY_R2_THRESHOLD = 0.990


# ============================================================
# ANCHOR NOKTALAR — düşük C-rate deşarj testinden
# ============================================================
# 4.178V'den başladı, 3.815V'de 11.6 Ah çekilmiş (şarj aleti ile deşarj).
# 3.718V'de 14.880 Ah, 3.643V'de 17.662 Ah, tam deşarj 25.2 Ah (3.36V).

ANCHOR_V_REST = np.array([4.178, 3.815, 3.718, 3.643, 3.360])
ANCHOR_AH_USED = np.array([0.000, 11.600, 14.880, 17.662, 25.200])
ANCHOR_SOC = 100.0 * (1.0 - ANCHOR_AH_USED / USABLE_CAPACITY_AH)


# ============================================================
# RAW DATA — Orijinal dosyadan import
# ============================================================

from pil_bitirme_testi import RAW_DATA


# ============================================================
# PARSING — İyileştirilmiş
# ============================================================

# Bilinen typo düzeltmeleri: (satır_no, alan, düzeltilmiş_değer)
# Satır numaraları RAW_DATA string içindeki satırlara göre (1-indexed).
KNOWN_TYPOS = {
    # Satır 315 (raw dosyadaki): 3.42 23.22 0.00 → v_cell 3.62 olmalı
    # (etraftaki tüm 0A satırları 3.59–3.62 aralığında)
}
# Not: Satır numarası raw string'de değişebilir, parse sırasında düzelteceğiz.


def parse_float_token(tok: str):
    """Bir string token'ı float'a çevir. Hatalıysa None döndür."""
    tok = tok.strip().lower()
    tok = tok.replace(",", "")
    tok = tok.replace("amper", "")

    # '?' → belirsiz digit, ortaya yakın tahmin yap
    if "?" in tok:
        cleaned = tok.replace("?", "")
        cleaned = cleaned.strip()
        if cleaned in {"", "."}:
            return None
        m = re.match(r"[-+]?\d*\.?\d+", cleaned)
        if m:
            base = float(m.group(0))
            # Kaç digit eksik? '3.4?' → 1 digit, '3.4' + 5 → 3.45
            # Belirsiz son digit'i 5 olarak tahmin et (ortaya yakın)
            text = m.group(0)
            if "." in text:
                decimal_places = len(text.split(".")[1])
                return base + 5 * 10 ** (-(decimal_places + 1))
            else:
                return base + 5  # tamsayı durumu, pek olası değil
        return None

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
    """
    Ham veri stringini parse et.

    Her satır: v_cell v_pack current [amper]
    Özel satırlar: 'same', '?', '.' ile başlayan satırlar.
    """
    rows = []
    last_full = None

    for line_no, line in enumerate(raw.splitlines(), start=1):
        original = line.rstrip("\n")
        body = original.split("#", 1)[0].strip()

        if not body:
            continue

        low = body.lower().strip()

        # 'same' satırları — önceki değerleri tekrarla
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
                    "v_cell": np.nan, "v_pack": np.nan,
                    "current_a": np.nan,
                    "source": "same_no_prev", "raw": original,
                })
            continue

        # '?' satırları — eksik ölçüm
        if low.startswith("?"):
            rows.append({
                "line_no": line_no,
                "v_cell": np.nan, "v_pack": np.nan,
                "current_a": np.nan,
                "source": "missing", "raw": original,
            })
            continue

        tokens = body.split()

        # '.' ile başlayan satırlar — v_cell eksik
        if tokens and tokens[0] == ".":
            nums = [parse_float_token(t) for t in tokens[1:]]
            nums = [x for x in nums if x is not None]
            v_cell = np.nan
            v_pack = nums[0] if len(nums) >= 1 else np.nan
            current = nums[1] if len(nums) >= 2 else np.nan
            source = "missing_cell"
        else:
            # POSİSYON-TABANLI parsing: her token'ın konumunu koru
            parsed = [parse_float_token(t) for t in tokens]
            # None'ları da say, pozisyonlarda kayma olmasın
            if len(parsed) == 0:
                v_cell, v_pack, current = np.nan, np.nan, np.nan
                source = "unparsed"
            elif len(parsed) == 1:
                v_cell = parsed[0] if parsed[0] is not None else np.nan
                v_pack, current = np.nan, np.nan
                source = "cell_only"
            elif len(parsed) == 2:
                v_cell = parsed[0] if parsed[0] is not None else np.nan
                v_pack = parsed[1] if parsed[1] is not None else np.nan
                current = np.nan
                source = "cell_pack_only"
            else:
                v_cell = parsed[0] if parsed[0] is not None else np.nan
                v_pack = parsed[1] if parsed[1] is not None else np.nan
                current = parsed[2] if parsed[2] is not None else np.nan
                source = "full"

        # ---- Pack voltajı typo düzeltmeleri ----
        if np.isfinite(v_pack):
            if v_pack > 100:           # 2122 → 21.22
                v_pack = v_pack / 100.0
            if 10.0 < v_pack < 15.0:   # 12.27 → 21.27 (eksik '2')
                v_pack = v_pack + 9.0

        # ---- Hücre voltajı tutarlılık kontrolü ----
        # Pack voltajından beklenen tek hücre ortalama ile karşılaştır
        if (np.isfinite(v_cell) and np.isfinite(v_pack)
                and np.isfinite(current)):
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
# POST-PARSE CORRECTIONS
# ============================================================

def apply_contextual_fixes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bağlamsal typo düzeltmeleri uygula.
    Chauvenet/MAD bazlı outlier tespiti + bilinen hatalar.
    """
    df = df.copy()

    # ---- Fix 1: Satır 315 bölgesi (3.42 → 3.62) ----
    # Etraftaki tüm 0A satırları 3.59–3.62 aralığında. 3.42 bağlama uymuyor.
    # Context: 22 minutes civarında, 0A rest, çevresi 3.60–3.62.
    mask_315 = (
        (df["v_cell"] > 3.40) & (df["v_cell"] < 3.44)
        & (df["current_a"] == 0.0)
    )
    # Bu bölgedeki 0A satırlardan etrafındakilere bak
    for idx in df.loc[mask_315].index:
        # Komşulardaki 0A satırları kontrol et
        neighbors = df.loc[
            max(0, idx-3):min(len(df)-1, idx+3),
        ]
        zero_neighbors = neighbors[
            (neighbors["current_a"] == 0.0)
            & (neighbors.index != idx)
            & (neighbors["v_cell"].notna())
        ]["v_cell"]
        if len(zero_neighbors) >= 2:
            neighbor_median = zero_neighbors.median()
            if abs(df.loc[idx, "v_cell"] - neighbor_median) > 0.15:
                old = df.loc[idx, "v_cell"]
                df.loc[idx, "v_cell"] = round(neighbor_median, 2)
                print(f"  Fix: idx={idx}, v_cell {old:.2f} → {df.loc[idx, 'v_cell']:.2f} "
                      f"(komşu median: {neighbor_median:.2f})")

    # ---- Fix 2: Pack voltajı 21.7 → 21.07 ----
    # Bağlam: ~47A yük, çevresi 21.04–21.12. 21.7 çok yüksek.
    for idx in df.index:
        vp = df.loc[idx, "v_pack"]
        if not np.isfinite(vp):
            continue
        # 21.5–22.0 arası ve yüksek akım → muhtemelen 21.0X typo
        if 21.5 < vp < 22.0 and np.isfinite(df.loc[idx, "current_a"]):
            curr = df.loc[idx, "current_a"]
            if curr > 40.0:  # yüksek yük altında
                neighbors = df.loc[
                    max(0, idx-5):min(len(df)-1, idx+5),
                ]
                high_load_neighbors = neighbors[
                    (neighbors["current_a"] > 40.0)
                    & (neighbors.index != idx)
                    & (neighbors["v_pack"].notna())
                    & (neighbors["v_pack"] < 21.5)
                ]["v_pack"]
                if len(high_load_neighbors) >= 3:
                    median_vp = high_load_neighbors.median()
                    if abs(vp - median_vp) > 0.4:
                        old = vp
                        # 21.7 → 21.07 (eksik sıfır)
                        fixed = float(f"{int(vp)}.{int(round((vp % 1) * 10)):02d}")
                        # Eğer bu da tutarsızsa, median'a yaklaştır
                        if abs(fixed - median_vp) > abs(old - median_vp):
                            fixed = round(median_vp, 2)
                        df.loc[idx, "v_pack"] = fixed
                        print(f"  Fix: idx={idx}, v_pack {old:.2f} → {fixed:.2f}")

    # ---- Fix 3: Genel outlier tespiti (MAD-based) ----
    # Yüksek yük (>30A) altında v_cell değerlerini kontrol et
    high_load = df[
        (df["current_a"] > 30.0)
        & df["v_cell"].notna()
    ].copy()
    if len(high_load) > 20:
        # Kayan pencere ile yerel median'dan sapma kontrol et
        window = 11
        for idx in high_load.index:
            lo = max(df.index[0], idx - window // 2)
            hi = min(df.index[-1], idx + window // 2)
            local = df.loc[lo:hi]
            local_high = local[
                (local["current_a"] > 30.0)
                & (local.index != idx)
                & local["v_cell"].notna()
            ]["v_cell"]
            if len(local_high) >= 5:
                med = local_high.median()
                mad = max(local_high.sub(med).abs().median() * 1.4826, 0.01)
                deviation = abs(df.loc[idx, "v_cell"] - med)
                if deviation > 4.0 * mad and deviation > 0.1:
                    old = df.loc[idx, "v_cell"]
                    df.loc[idx, "v_cell"] = np.nan  # Outlier → NaN
                    print(f"  Outlier: idx={idx}, v_cell {old:.2f} → NaN "
                          f"(local median: {med:.2f}, deviation: {deviation:.3f}V)")

    return df


# ============================================================
# SOC ESTIMATION — Sürekli Coulomb Counting
# ============================================================

def build_anchor_interpolators():
    """
    Anchor noktalarından OCV↔SOC ve OCV↔Ah interpolatörleri oluştur.
    """
    # SOC → OCV (SOC artan, V artan)
    order_soc = np.argsort(ANCHOR_SOC)
    soc_sorted = ANCHOR_SOC[order_soc]
    v_sorted = ANCHOR_V_REST[order_soc]
    soc_to_ocv = PchipInterpolator(soc_sorted, v_sorted, extrapolate=True)

    # OCV → Ah_used (V artan, Ah azalan)
    order_v = np.argsort(ANCHOR_V_REST)
    v_asc = ANCHOR_V_REST[order_v]
    ah_for_v = ANCHOR_AH_USED[order_v]
    ocv_to_ah = PchipInterpolator(v_asc, ah_for_v, extrapolate=True)

    return soc_to_ocv, ocv_to_ah


def estimate_initial_ah(df, ocv_to_ah):
    """
    Testin ilk birkaç satırındaki düşük-akım voltajından başlangıç Ah'ı tahmin et.
    """
    # İlk 30 satırdan düşük akım (<1A) ve geçerli v_cell olanları bul
    head = df.head(30)
    low_i = head[
        head["current_a"].notna()
        & (head["current_a"].abs() < 1.0)
        & head["v_cell"].notna()
    ]
    if len(low_i) >= 1:
        v0 = float(low_i["v_cell"].median())
    else:
        finite = head["v_cell"].dropna()
        v0 = float(finite.iloc[0]) if len(finite) > 0 else 3.88

    ah0 = float(np.clip(ocv_to_ah(v0), 0.0, USABLE_CAPACITY_AH))
    print(f"  Başlangıç dinlenmiş voltaj: {v0:.3f}V → Ah used: {ah0:.2f} → SOC: {100*(1 - ah0/USABLE_CAPACITY_AH):.1f}%")
    return ah0


def continuous_coulomb_counting(df, initial_ah, dt_s):
    """
    Sürekli (segment kırmadan) coulomb counting.

    Akım bilinmediği satırlarda Ah birikmesi durur (I=0 varsayılır).
    Bu basit ama sağlam bir yaklaşım — akımsız dönemler genellikle dinlenme.
    """
    n = len(df)
    ah_used = np.full(n, np.nan)
    current = df["current_a"].to_numpy(dtype=float)

    ah = initial_ah
    ah_used[0] = ah

    for i in range(1, n):
        i_prev = current[i - 1] if np.isfinite(current[i - 1]) else 0.0
        i_curr = current[i] if np.isfinite(current[i]) else 0.0

        # Trapezoidal integration
        d_ah = 0.5 * (i_prev + i_curr) * dt_s / 3600.0
        ah += d_ah
        ah_used[i] = ah

    df = df.copy()
    df["ah_used"] = ah_used
    df["soc_pct"] = 100.0 * (1.0 - ah_used / USABLE_CAPACITY_AH)

    return df


# ============================================================
# INTERNAL RESISTANCE ESTIMATION — Transition-Based R(V)
# ============================================================

def detect_load_transitions(df, min_delta_i=MIN_DELTA_I_FOR_TRANSITION):
    """
    Ardışık örnekler arasındaki büyük akım değişimlerinden
    anlık iç direnç (R) hesapla.

    R = -ΔV / ΔI  (akım artınca voltaj düşer → R pozitif)

    Her R değeri, düşük-akım tarafındaki voltajla etiketlenir
    (OCV'ye daha yakın olduğu için).
    """
    v = df["v_cell"].to_numpy(dtype=float)
    i = df["current_a"].to_numpy(dtype=float)
    t = df["t_s"].to_numpy(dtype=float)
    soc = df["soc_pct"].to_numpy(dtype=float)

    transitions = []

    for idx in range(len(df) - 1):
        if not (np.isfinite(v[idx]) and np.isfinite(v[idx + 1])
                and np.isfinite(i[idx]) and np.isfinite(i[idx + 1])):
            continue

        di = i[idx + 1] - i[idx]
        dv = v[idx + 1] - v[idx]

        if abs(di) < min_delta_i:
            continue

        r = -dv / di  # Pozitif olmalı

        if not (R_VALID_MIN < r < R_VALID_MAX):
            continue

        # Düşük-akım tarafının voltajını referans al (OCV'ye yakın)
        if abs(i[idx]) < abs(i[idx + 1]):
            v_ref = v[idx]
            i_low = i[idx]
            i_high = i[idx + 1]
        else:
            v_ref = v[idx + 1]
            i_low = i[idx + 1]
            i_high = i[idx]

        transitions.append({
            "t_s": (t[idx] + t[idx + 1]) / 2.0,
            "v_ref": v_ref,
            "v_avg": (v[idx] + v[idx + 1]) / 2.0,
            "r_ohm": r,
            "i_before": i[idx],
            "i_after": i[idx + 1],
            "i_low": i_low,
            "i_high": i_high,
            "delta_i": di,
            "delta_v": dv,
            "soc_avg": (soc[idx] + soc[idx + 1]) / 2.0 if (
                np.isfinite(soc[idx]) and np.isfinite(soc[idx + 1])
            ) else np.nan,
        })

    return pd.DataFrame(transitions)


def fit_r_vs_voltage(trans_df, bin_width=0.06, min_count=3):
    """
    R değerlerini voltaja göre bin'le, robust median al,
    pürüzsüz R(V) eğrisi fit et.

    Returns
    -------
    r_func : callable
        V_cell → R_ohm interpolatör
    bin_centers, bin_r_medians : arrays
        Bin verileri
    r_median_global : float
        Global median R (fallback)
    """
    if len(trans_df) < 5:
        warnings.warn("Yeterli transition bulunamadı, sabit R kullanılacak.")
        r_med = 0.006  # 6 mΩ varsayılan
        return lambda v: np.full_like(np.asarray(v, dtype=float), r_med), \
               np.array([]), np.array([]), r_med

    v = trans_df["v_ref"].to_numpy()
    r = trans_df["r_ohm"].to_numpy()

    # Global median (fallback)
    r_median_global = float(np.median(r))

    # Voltage bin'leri oluştur
    v_min = np.floor(v.min() / bin_width) * bin_width
    v_max = np.ceil(v.max() / bin_width) * bin_width
    bins = np.arange(v_min, v_max + bin_width, bin_width)

    bin_centers = []
    bin_r_medians = []

    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (v >= lo) & (v < hi)
        if mask.sum() < min_count:
            continue

        rr = r[mask]
        med = np.median(rr)
        mad = np.median(np.abs(rr - med))

        # MAD-based outlier rejection
        if mad > 1e-9:
            keep = np.abs(rr - med) <= 3.5 * 1.4826 * mad
            rr = rr[keep]

        if len(rr) >= 2:
            bin_centers.append((lo + hi) / 2.0)
            bin_r_medians.append(float(np.median(rr)))

    bin_centers = np.array(bin_centers)
    bin_r_medians = np.array(bin_r_medians)

    if len(bin_centers) < 3:
        # Yetersiz bin — sabit R kullan
        return lambda v: np.full_like(np.asarray(v, dtype=float), r_median_global), \
               bin_centers, bin_r_medians, r_median_global

    # PCHIP interpolasyonu
    order = np.argsort(bin_centers)
    bc = bin_centers[order]
    br = bin_r_medians[order]

    # Sınır extrapolasyonu için uç noktaları kopyala
    # (PCHIP extrapolate=True ile birlikte)
    r_interp = PchipInterpolator(bc, br, extrapolate=True)

    def r_func(v_input):
        v_arr = np.asarray(v_input, dtype=float)
        result = r_interp(v_arr)
        # Fiziksel sınırlar: R her zaman pozitif
        return np.clip(result, R_VALID_MIN, R_VALID_MAX)

    return r_func, bin_centers, bin_r_medians, r_median_global


def fit_r_vs_soc(trans_df, bin_width=5.0, min_count=3):
    """
    R değerlerini SOC'ye göre bin'le (ayrı grafik için).
    """
    if len(trans_df) < 5 or trans_df["soc_avg"].isna().all():
        return np.array([]), np.array([])

    v = trans_df["soc_avg"].to_numpy()
    r = trans_df["r_ohm"].to_numpy()
    mask = np.isfinite(v) & np.isfinite(r)
    v, r = v[mask], r[mask]

    bins = np.arange(0.0, 100.0 + bin_width, bin_width)
    centers, medians = [], []

    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (v >= lo) & (v < hi)
        if m.sum() < min_count:
            continue
        rr = r[m]
        med = np.median(rr)
        mad = np.median(np.abs(rr - med))
        if mad > 1e-9:
            keep = np.abs(rr - med) <= 3.5 * 1.4826 * mad
            rr = rr[keep]
        if len(rr) >= 2:
            centers.append((lo + hi) / 2.0)
            medians.append(float(np.median(rr)))

    return np.array(centers), np.array(medians)


# ============================================================
# SAG CORRECTION & REST VOLTAGE ESTIMATION
# ============================================================

def compute_rest_voltage(df, r_func):
    """
    Her satır için dinlenmiş voltaj tahmini:
    V_rest = V_cell + R(V_cell) × I

    R fonksiyonu voltaja bağlı olduğu için doğru sag düzeltmesi yapılır.
    """
    df = df.copy()
    v = df["v_cell"].to_numpy(dtype=float)
    i = df["current_a"].to_numpy(dtype=float)

    v_rest = np.full(len(df), np.nan)

    valid = np.isfinite(v) & np.isfinite(i)
    if valid.any():
        r_vals = r_func(v[valid])
        v_rest[valid] = v[valid] + r_vals * i[valid]

    df["v_rest_est"] = v_rest

    # Akım 0 olan satırlarda v_rest = v_cell (düzeltme gereksiz)
    zero_i = np.isfinite(i) & (np.abs(i) < 0.5)
    df.loc[zero_i, "v_rest_est"] = df.loc[zero_i, "v_cell"]

    return df


# ============================================================
# SOC CURVE FITTING — Pürüzsüz Eğriler
# ============================================================

def pava_increasing(y):
    """Pool Adjacent Violators Algorithm — monoton artan hale getir."""
    y = np.asarray(y, dtype=float).copy()
    n = len(y)
    # (value, weight, start, end) şeklinde bloklar
    blocks = [[y[i], 1, i, i] for i in range(n)]

    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            # Birleştir
            w = blocks[i][1] + blocks[i + 1][1]
            val = (blocks[i][0] * blocks[i][1] + blocks[i + 1][0] * blocks[i + 1][1]) / w
            blocks[i] = [val, w, blocks[i][2], blocks[i + 1][3]]
            blocks.pop(i + 1)
            # Geri kontrol
            if i > 0:
                i -= 1
        else:
            i += 1

    out = np.empty(n)
    for val, w, s, e in blocks:
        out[s:e + 1] = val
    return out


def build_smooth_soc_curve(soc_values, v_values, bin_width=1.5,
                           min_count=3, label=""):
    """
    SOC-voltaj verisinden pürüzsüz monoton eğri oluştur.

    İyileştirilmiş yaklaşım:
    1. Gaussian kernel ile ağırlıklı yerel ortalama (staircase yok)
    2. Monotonluk uygula (PAVA)
    3. PCHIP ile smooth interpolasyon (ayrık noktalar arası)
    """
    soc = np.asarray(soc_values, dtype=float)
    v = np.asarray(v_values, dtype=float)

    # Temiz veri filtresi
    valid = (
        np.isfinite(soc) & np.isfinite(v)
        & (soc >= -5) & (soc <= 105)
        & (v > 2.5) & (v < 4.4)
    )
    soc, v = soc[valid], v[valid]

    if len(soc) < 10:
        warnings.warn(f"  {label}: Yeterli veri yok ({len(soc)} nokta)")
        return None, np.array([]), np.array([])

    # ---- Kernel smoothing yaklaşımı ----
    # SOC grid'i oluştur (ince çözünürlük)
    soc_min = max(0.0, np.floor(soc.min()))
    soc_max = min(100.0, np.ceil(soc.max()))
    eval_points = np.arange(soc_min, soc_max + 0.5, 0.5)

    # Gaussian kernel bandwidth (SOC % cinsinden)
    # Daha geniş bandwidth → daha pürüzsüz eğri (wiggle yok)
    bandwidth = max(3.0, (soc_max - soc_min) / 20.0)

    smoothed_v = np.full(len(eval_points), np.nan)

    for i, s in enumerate(eval_points):
        # Gaussian ağırlıklar
        weights = np.exp(-0.5 * ((soc - s) / bandwidth) ** 2)

        # Minimum ağırlık eşiği (çok uzak noktalar dahil etme)
        significant = weights > 0.01
        if significant.sum() < 5:
            continue

        w = weights[significant]
        vv = v[significant]

        # Ağırlıklı robust median: önce ağırlıklı ortalama, sonra
        # büyük sapmalar hariç tut, tekrar ağırlıklı ortalama
        wavg = np.average(vv, weights=w)
        dev = np.abs(vv - wavg)
        wdev = np.sqrt(np.average(dev ** 2, weights=w))

        if wdev > 0.001:
            keep = dev <= 3.0 * wdev
            if keep.sum() >= 3:
                w = w[keep]
                vv = vv[keep]

        smoothed_v[i] = np.average(vv, weights=w)

    # Geçerli noktalar
    valid_mask = np.isfinite(smoothed_v)
    if valid_mask.sum() < 4:
        warnings.warn(f"  {label}: Yeterli smooth nokta yok")
        return None, eval_points[valid_mask], smoothed_v[valid_mask]

    centers = eval_points[valid_mask]
    medians = smoothed_v[valid_mask]

    # Sırala (SOC artan)
    order = np.argsort(centers)
    centers = centers[order]
    medians = medians[order]

    # Monotonluk uygula (SOC arttıkça V artmalı)
    medians_mono = pava_increasing(medians)

    # PCHIP fit
    df_tmp = pd.DataFrame({"x": centers, "y": medians_mono})
    df_tmp = df_tmp.groupby("x", as_index=False)["y"].median()
    x_unique = df_tmp["x"].to_numpy()
    y_unique = df_tmp["y"].to_numpy()

    if len(x_unique) < 3:
        return None, centers, medians_mono

    interp = PchipInterpolator(x_unique, y_unique, extrapolate=False)

    return interp, centers, medians_mono


# ============================================================
# LINEARITY ANALYSIS
# ============================================================

def analyze_linearity(soc_grid, v_curve, window_pct=LINEARITY_WINDOW_PCT,
                      r2_threshold=LINEARITY_R2_THRESHOLD):
    """
    SOC eğrisinin lineer olduğu bölgeyi bul.

    Kayan pencere ile R² hesapla. R² > threshold olan bölge lineer.

    Returns
    -------
    linear_mask : bool array
        SOC grid üzerinde lineer olan noktalar
    r2_values : float array
        Her nokta için R² değeri
    slopes : float array
        Her nokta için yerel eğim (mV/% SOC)
    linear_range : tuple or None
        (SOC_min, SOC_max) lineer bölge sınırları
    """
    n = len(soc_grid)
    valid = np.isfinite(v_curve)
    window = max(5, int(window_pct / (soc_grid[1] - soc_grid[0])))

    r2_values = np.full(n, np.nan)
    slopes = np.full(n, np.nan)

    half_w = window // 2
    for i in range(half_w, n - half_w):
        lo, hi = i - half_w, i + half_w + 1
        x = soc_grid[lo:hi]
        y = v_curve[lo:hi]

        mask = np.isfinite(y)
        if mask.sum() < 5:
            continue

        x_v, y_v = x[mask], y[mask]
        if len(x_v) < 5:
            continue

        # Lineer fit
        coeffs = np.polyfit(x_v, y_v, 1)
        y_fit = np.polyval(coeffs, x_v)
        ss_res = np.sum((y_v - y_fit) ** 2)
        ss_tot = np.sum((y_v - np.mean(y_v)) ** 2)

        if ss_tot > 1e-15:
            r2 = 1.0 - ss_res / ss_tot
        else:
            r2 = 1.0

        r2_values[i] = r2
        slopes[i] = coeffs[0] * 1000.0  # mV/% SOC

    # Lineer bölge: R² > threshold olan en uzun sürekli bölge
    linear_mask = r2_values > r2_threshold

    # En uzun sürekli True bölgesini bul
    if not linear_mask.any():
        return linear_mask, r2_values, slopes, None

    # Run-length encoding
    changes = np.diff(linear_mask.astype(int))
    starts = np.where(changes == 1)[0] + 1
    ends = np.where(changes == -1)[0] + 1

    if linear_mask[0]:
        starts = np.concatenate([[0], starts])
    if linear_mask[-1]:
        ends = np.concatenate([ends, [n]])

    if len(starts) == 0 or len(ends) == 0:
        return linear_mask, r2_values, slopes, None

    lengths = ends[:len(starts)] - starts[:len(ends)]
    best = np.argmax(lengths)
    best_start = starts[best]
    best_end = ends[best] - 1

    linear_range = (float(soc_grid[best_start]), float(soc_grid[best_end]))

    return linear_mask, r2_values, slopes, linear_range


# ============================================================
# PLOTTING
# ============================================================

def plot_r_vs_voltage(trans_df, r_func, bin_centers, bin_r_medians,
                      r_median_global):
    """Plot 1: İç direnç vs voltaj."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Scatter — tüm transition noktaları
    ax.scatter(trans_df["v_ref"], trans_df["r_ohm"] * 1000,
               s=15, alpha=0.25, color="steelblue", label="Transition R noktaları")

    # Bin medyanları
    if len(bin_centers) > 0:
        ax.scatter(bin_centers, bin_r_medians * 1000,
                   s=60, marker="D", color="orangered", zorder=5,
                   label="Bin median")

    # Smooth R(V) eğrisi
    if len(bin_centers) >= 3:
        v_grid = np.linspace(
            max(2.9, bin_centers.min() - 0.1),
            min(4.0, bin_centers.max() + 0.1),
            200
        )
        r_smooth = r_func(v_grid) * 1000
        ax.plot(v_grid, r_smooth, linewidth=2.5, color="darkred",
                label="R(V) smooth fit")

    # Global median referansı
    ax.axhline(r_median_global * 1000, color="gray", linestyle="--",
               linewidth=1, alpha=0.6,
               label=f"Global median: {r_median_global*1000:.2f} mΩ")

    ax.set_xlabel("Hücre Voltajı [V]")
    ax.set_ylabel("İç Direnç R [mΩ]")
    ax.set_title("Voltaja Bağlı İç Direnç R(V)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "r_vs_voltage.png")
    plt.close(fig)


def plot_r_vs_soc(trans_df, soc_centers, soc_r_medians):
    """Plot 2: İç direnç vs SOC."""
    fig, ax = plt.subplots(figsize=(10, 6))

    valid = trans_df["soc_avg"].notna()
    if valid.any():
        ax.scatter(trans_df.loc[valid, "soc_avg"],
                   trans_df.loc[valid, "r_ohm"] * 1000,
                   s=15, alpha=0.25, color="steelblue",
                   label="Transition R noktaları")

    if len(soc_centers) > 0:
        ax.scatter(soc_centers, soc_r_medians * 1000,
                   s=60, marker="D", color="orangered", zorder=5,
                   label="Bin median")

    ax.set_xlabel("SOC [%]")
    ax.set_ylabel("İç Direnç R [mΩ]")
    ax.set_title("SOC'ye Bağlı İç Direnç R(SOC)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(100, 0)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "r_vs_soc.png")
    plt.close(fig)


def plot_soc_curves(grid_soc, v_rest_smooth, v_load_smooth,
                    rest_bin_x, rest_bin_y,
                    linear_range_rest, linear_range_load):
    """Plot 3: Ana SOC-Voltaj eğrileri."""
    fig, ax = plt.subplots(figsize=(11, 7))

    # Dinlenmiş eğri
    valid_r = np.isfinite(v_rest_smooth)
    ax.plot(grid_soc[valid_r], v_rest_smooth[valid_r], linewidth=2.5,
            color="#2196F3", label="Dinlenmiş / OCV (rest)")

    # Yüklü eğri
    valid_l = np.isfinite(v_load_smooth)
    ax.plot(grid_soc[valid_l], v_load_smooth[valid_l], linewidth=2.5,
            color="#FF9800", label=f"Yorgun / {REFERENCE_LOAD_A:.0f}A yük altı")

    # Anchor noktaları
    ax.scatter(ANCHOR_SOC, ANCHOR_V_REST, s=70, marker="x", color="#4CAF50",
               linewidth=2, zorder=5, label="Anchor noktaları (düşük C-rate)")

    # Lineer bölgeler
    if linear_range_rest is not None:
        ax.axvspan(linear_range_rest[1], linear_range_rest[0],
                   alpha=0.08, color="blue",
                   label=f"Lineer bölge (rest): {linear_range_rest[0]:.0f}–{linear_range_rest[1]:.0f}% SOC")
    if linear_range_load is not None:
        ax.axvspan(linear_range_load[1], linear_range_load[0],
                   alpha=0.08, color="orange",
                   label=f"Lineer bölge (load): {linear_range_load[0]:.0f}–{linear_range_load[1]:.0f}% SOC")

    ax.set_xlabel("SOC [%]")
    ax.set_ylabel("Tek Hücre Voltajı [V]")
    ax.set_title("SOC–Voltaj Eğrileri: Dinlenmiş ve Yorgun")
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(100, 0)
    ax.set_ylim(2.9, 4.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "soc_voltage_curves_v2.png")
    plt.close(fig)


def plot_scatter_validation(df, grid_soc, v_rest_smooth, v_load_smooth,
                            r_func):
    """Plot 4: Scatter veri + fit validasyonu."""
    fig, ax = plt.subplots(figsize=(11, 7))

    # Sag-düzeltilmiş data (tüm noktalar)
    valid = df["v_rest_est"].notna() & df["soc_pct"].notna()
    ax.scatter(df.loc[valid, "soc_pct"], df.loc[valid, "v_rest_est"],
               s=8, alpha=0.15, color="#64B5F6", label="Sag düzeltilmiş data")

    # Yüksek yük ham data
    high_load = (
        valid
        & (df["current_a"] >= 30.0)
        & (df["current_a"] <= 55.0)
    )
    ax.scatter(df.loc[high_load, "soc_pct"], df.loc[high_load, "v_cell"],
               s=8, alpha=0.15, color="#FFB74D",
               label="Yüksek yük ham data (I≥30A)")

    # Smooth eğriler
    valid_r = np.isfinite(v_rest_smooth)
    ax.plot(grid_soc[valid_r], v_rest_smooth[valid_r], linewidth=2.5,
            color="#1565C0", label="Dinlenmiş smooth")

    valid_l = np.isfinite(v_load_smooth)
    ax.plot(grid_soc[valid_l], v_load_smooth[valid_l], linewidth=2.5,
            color="#E65100", label=f"{REFERENCE_LOAD_A:.0f}A yük smooth")

    # Anchor noktaları
    ax.scatter(ANCHOR_SOC, ANCHOR_V_REST, s=70, marker="x", color="#4CAF50",
               linewidth=2, zorder=5, label="Anchor")

    ax.set_xlabel("SOC [%]")
    ax.set_ylabel("Tek Hücre Voltajı [V]")
    ax.set_title("SOC–Voltaj Fit Validasyonu")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(100, 0)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "soc_scatter_validation_v2.png")
    plt.close(fig)


def plot_time_trace(df):
    """Plot 5: Zaman serisi — ölçülen vs dinlenmiş voltaj + akım."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8),
                                    sharex=True, height_ratios=[3, 1])

    # Üst panel: voltaj
    ax1.plot(df["t_min"], df["v_cell"], linewidth=0.8, color="#1976D2",
             alpha=0.8, label="Ölçülen hücre voltajı")
    ax1.plot(df["t_min"], df["v_rest_est"], linewidth=0.8, color="#F57C00",
             alpha=0.8, label="Sag düzeltilmiş / rest tahmini")
    ax1.set_ylabel("Tek Hücre Voltajı [V]")
    ax1.set_title("Zaman Serisi: Voltaj ve Akım")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Alt panel: akım
    ax2.fill_between(df["t_min"], 0, df["current_a"],
                     alpha=0.4, color="#4CAF50")
    ax2.plot(df["t_min"], df["current_a"], linewidth=0.5, color="#2E7D32")
    ax2.set_ylabel("Akım [A]")
    ax2.set_xlabel("Zaman [dk]")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "time_trace_v2.png")
    plt.close(fig)


def plot_linearity(grid_soc, r2_rest, r2_load, slopes_rest, slopes_load,
                   linear_range_rest, linear_range_load):
    """Plot 6: Lineerlik analizi."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

    # Üst panel: R² değerleri
    valid_r = np.isfinite(r2_rest)
    valid_l = np.isfinite(r2_load)
    if valid_r.any():
        ax1.plot(grid_soc[valid_r], r2_rest[valid_r], linewidth=1.5,
                 color="#2196F3", label="Rest eğrisi R²")
    if valid_l.any():
        ax1.plot(grid_soc[valid_l], r2_load[valid_l], linewidth=1.5,
                 color="#FF9800", label="Load eğrisi R²")

    ax1.axhline(LINEARITY_R2_THRESHOLD, color="red", linestyle="--",
                linewidth=1, alpha=0.6,
                label=f"Lineerlik eşiği: R²={LINEARITY_R2_THRESHOLD}")

    if linear_range_rest is not None:
        ax1.axvspan(linear_range_rest[1], linear_range_rest[0],
                    alpha=0.1, color="blue")
    if linear_range_load is not None:
        ax1.axvspan(linear_range_load[1], linear_range_load[0],
                    alpha=0.1, color="orange")

    ax1.set_ylabel("R² (kayan pencere)")
    ax1.set_title("Lineerlik Analizi")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0.95, 1.005)

    # Alt panel: eğim (dV/dSOC)
    valid_r = np.isfinite(slopes_rest)
    valid_l = np.isfinite(slopes_load)
    if valid_r.any():
        ax2.plot(grid_soc[valid_r], slopes_rest[valid_r], linewidth=1.5,
                 color="#2196F3", label="Rest dV/dSOC")
    if valid_l.any():
        ax2.plot(grid_soc[valid_l], slopes_load[valid_l], linewidth=1.5,
                 color="#FF9800", label="Load dV/dSOC")

    ax2.set_ylabel("dV/dSOC [mV / %SOC]")
    ax2.set_xlabel("SOC [%]")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(100, 0)

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "linearity_analysis_v2.png")
    plt.close(fig)


def plot_r_histogram(trans_df, r_median_global):
    """Plot 7: R dağılımı histogramı."""
    fig, ax = plt.subplots(figsize=(9, 5))
    r_mohm = trans_df["r_ohm"].to_numpy() * 1000
    ax.hist(r_mohm, bins=40, color="#64B5F6", edgecolor="white", alpha=0.8)
    ax.axvline(r_median_global * 1000, color="#D32F2F", linewidth=2,
               label=f"Median = {r_median_global*1000:.2f} mΩ")
    ax.set_xlabel("Etkili R [mΩ]")
    ax.set_ylabel("Adet")
    ax.set_title("Transition-Based R Dağılımı")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "r_histogram_v2.png")
    plt.close(fig)


def plot_soc_over_time(df):
    """Plot 8: SOC vs zaman."""
    fig, ax = plt.subplots(figsize=(11, 5))
    valid = df["soc_pct"].notna()
    ax.plot(df.loc[valid, "t_min"], df.loc[valid, "soc_pct"],
            linewidth=1.2, color="#7B1FA2")
    ax.set_xlabel("Zaman [dk]")
    ax.set_ylabel("SOC [%]")
    ax.set_title("SOC Zaman Serisi")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "soc_over_time_v2.png")
    plt.close(fig)


# ============================================================
# PRACTICAL FLIGHT PLANNING TABLE
# ============================================================

def print_practical_table(rest_interp, r_func, grid_soc, v_rest_smooth):
    """
    Pratik uçuş planlama tablosu yazdır.
    """
    print("\n" + "=" * 80)
    print("PRATIK UÇUŞ PLANLAMA TABLOSU")
    print("=" * 80)
    print(f"{'SOC':>5} | {'V_rest':>8} | {'V@{:.0f}A'.format(REFERENCE_LOAD_A):>8} | "
          f"{'R_int':>8} | {'Sag':>7} | Durum")
    print("-" * 80)

    for soc in [100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50,
                45, 40, 35, 30, 25, 20, 15, 10, 5, 0]:
        if rest_interp is not None:
            v_r = float(rest_interp(soc))
        else:
            continue

        if np.isnan(v_r):
            continue

        r = float(r_func(v_r))
        sag = r * REFERENCE_LOAD_A
        v_l = v_r - sag

        if soc >= 30:
            status = "✓ Güvenli"
        elif soc >= 15:
            status = "⚠ Dikkat"
        elif soc >= 5:
            status = "⛔ Kritik"
        else:
            status = "🚫 TEHLİKE"

        print(f"{soc:>4}% | {v_r:>7.3f}V | {v_l:>7.3f}V | "
              f"{r*1000:>6.2f}mΩ | {sag*1000:>5.0f}mV | {status}")

    print("-" * 80)
    print(f"Not: {REFERENCE_LOAD_A:.0f}A referans yük altında hesaplanmıştır.")
    print(f"     Kapasite: {USABLE_CAPACITY_AH} Ah (3.36V → 4.20V)")


def print_voltage_conversion_table(rest_interp, r_func):
    """
    Voltaj dönüşüm tablosu: ölçülen → dinlenmiş / SOC.
    """
    print("\n" + "=" * 80)
    print("VOLTAJ DÖNÜŞÜM TABLOSU (Multimetre → Gerçek Durum)")
    print("=" * 80)

    for load_a in [0, 20, 35, 45, 50]:
        print(f"\n--- {load_a}A yük altında ---")
        print(f"{'V_okunan':>9} | {'V_rest':>8} | {'SOC':>5}")
        print("-" * 35)

        for v_read in np.arange(2.9, 4.25, 0.05):
            r = float(r_func(v_read))
            v_rest = v_read + r * load_a

            # SOC lookup (ters interpolasyon)
            if rest_interp is not None:
                soc_grid = np.linspace(0, 100, 1001)
                v_grid = rest_interp(soc_grid)
                valid = np.isfinite(v_grid)
                if valid.any():
                    # En yakın V_rest'e karşılık gelen SOC
                    idx = np.nanargmin(np.abs(v_grid - v_rest))
                    soc_est = soc_grid[idx]
                else:
                    soc_est = np.nan
            else:
                soc_est = np.nan

            if np.isfinite(soc_est) and 0 <= soc_est <= 100:
                print(f"{v_read:>8.3f}V | {v_rest:>7.3f}V | {soc_est:>4.1f}%")

    print()


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("Li-ion Solid State Pil SOC Analizi v2")
    print("=" * 60)

    # ---- 1. Anchor interpolatörleri ----
    soc_to_ocv, ocv_to_ah = build_anchor_interpolators()

    # ---- 2. Veri parsing ----
    print("\n[1/7] Veri parsing...")
    df = parse_raw_data(RAW_DATA, SAMPLE_PERIOD_S)
    print(f"  Toplam satır: {len(df)}")
    print(f"  Kaynak dağılımı: {df['source'].value_counts().to_dict()}")

    # ---- 3. Bağlamsal düzeltmeler ----
    print("\n[2/7] Bağlamsal düzeltmeler...")
    df = apply_contextual_fixes(df)

    # ---- 4. SOC estimation ----
    print("\n[3/7] SOC estimation (sürekli coulomb counting)...")
    initial_ah = estimate_initial_ah(df, ocv_to_ah)
    df = continuous_coulomb_counting(df, initial_ah, SAMPLE_PERIOD_S)
    print(f"  SOC aralığı: {df['soc_pct'].min():.1f}% – {df['soc_pct'].max():.1f}%")
    print(f"  Toplam Ah tüketilen: {df['ah_used'].max() - df['ah_used'].min():.2f} Ah")

    # ---- 5. Transition-based R(V) estimation ----
    print("\n[4/7] İç direnç R(V) estimation...")
    trans_df = detect_load_transitions(df)
    print(f"  Bulunan transition sayısı: {len(trans_df)}")

    if len(trans_df) > 0:
        print(f"  R aralığı: {trans_df['r_ohm'].min()*1000:.2f} – "
              f"{trans_df['r_ohm'].max()*1000:.2f} mΩ")
        print(f"  R median: {trans_df['r_ohm'].median()*1000:.2f} mΩ")

    r_func, r_bin_v, r_bin_r, r_median = fit_r_vs_voltage(trans_df)
    soc_r_centers, soc_r_medians = fit_r_vs_soc(trans_df)

    print(f"  R(V) bin sayısı: {len(r_bin_v)}")
    if len(r_bin_v) > 0:
        print(f"  R(3.8V) = {r_func(3.8)*1000:.2f} mΩ")
        print(f"  R(3.5V) = {r_func(3.5)*1000:.2f} mΩ")
        print(f"  R(3.2V) = {r_func(3.2)*1000:.2f} mΩ")

    # ---- 6. Sag correction ve SOC eğrileri ----
    print("\n[5/7] Sag düzeltme ve SOC eğrileri...")
    df = compute_rest_voltage(df, r_func)

    # Rest eğrisi verisi: sag-corrected + anchor
    rest_mask = (
        df["soc_pct"].notna()
        & df["v_rest_est"].notna()
        & (df["v_rest_est"] > 2.8)
        & (df["v_rest_est"] < 4.3)
        & (df["soc_pct"] >= -5)
        & (df["soc_pct"] <= 105)
    )
    rest_soc_data = np.concatenate([
        df.loc[rest_mask, "soc_pct"].to_numpy(),
        ANCHOR_SOC
    ])
    rest_v_data = np.concatenate([
        df.loc[rest_mask, "v_rest_est"].to_numpy(),
        ANCHOR_V_REST
    ])

    rest_interp, rest_bx, rest_by = build_smooth_soc_curve(
        rest_soc_data, rest_v_data, bin_width=1.5, min_count=3,
        label="Rest/OCV"
    )

    # Load eğrisi: yüksek akım verisi
    load_mask = (
        df["soc_pct"].notna()
        & df["v_cell"].notna()
        & df["current_a"].notna()
        & (df["current_a"] >= 30.0)
        & (df["current_a"] <= 55.0)
        & (df["v_cell"] > 2.7)
        & (df["soc_pct"] >= -5)
        & (df["soc_pct"] <= 105)
    )
    load_interp, load_bx, load_by = build_smooth_soc_curve(
        df.loc[load_mask, "soc_pct"].to_numpy(),
        df.loc[load_mask, "v_cell"].to_numpy(),
        bin_width=1.5, min_count=3,
        label=f"Loaded ({REFERENCE_LOAD_A:.0f}A)"
    )

    # Grid üzerinde smooth eğriler
    grid_soc = np.linspace(0, 100, 501)
    v_rest_smooth = rest_interp(grid_soc) if rest_interp else np.full(501, np.nan)
    v_load_smooth = load_interp(grid_soc) if load_interp else np.full(501, np.nan)

    # Alternatif load eğrisi: rest - R(V)*I
    if rest_interp is not None:
        v_load_from_rest = np.full(501, np.nan)
        for i, soc in enumerate(grid_soc):
            vr = v_rest_smooth[i]
            if np.isfinite(vr):
                r = float(r_func(vr))
                v_load_from_rest[i] = vr - r * REFERENCE_LOAD_A

    # ---- 7. Linearity analysis ----
    print("\n[6/7] Lineerlik analizi...")
    _, r2_rest, slopes_rest, linear_range_rest = analyze_linearity(
        grid_soc, v_rest_smooth
    )
    _, r2_load, slopes_load, linear_range_load = analyze_linearity(
        grid_soc, v_load_smooth
    )

    if linear_range_rest:
        soc_lo, soc_hi = linear_range_rest
        # Voltaj karşılıklarını bul
        v_at_lo = float(rest_interp(soc_lo)) if rest_interp else np.nan
        v_at_hi = float(rest_interp(soc_hi)) if rest_interp else np.nan
        v_lo_s = f"{v_at_lo:.3f}V" if np.isfinite(v_at_lo) else "N/A"
        v_hi_s = f"{v_at_hi:.3f}V" if np.isfinite(v_at_hi) else "N/A"
        print(f"  Rest lineer bölge: SOC {soc_hi:.0f}% – {soc_lo:.0f}%")
        print(f"    Voltaj: {v_lo_s} – {v_hi_s}")
    else:
        print("  Rest eğrisi için belirgin lineer bölge bulunamadı.")

    if linear_range_load:
        soc_lo, soc_hi = linear_range_load
        v_at_lo = float(load_interp(soc_lo)) if load_interp else np.nan
        v_at_hi = float(load_interp(soc_hi)) if load_interp else np.nan
        v_lo_s = f"{v_at_lo:.3f}V" if np.isfinite(v_at_lo) else "N/A"
        v_hi_s = f"{v_at_hi:.3f}V" if np.isfinite(v_at_hi) else "N/A"
        print(f"  Load lineer bölge: SOC {soc_hi:.0f}% – {soc_lo:.0f}%")
        print(f"    Voltaj: {v_lo_s} – {v_hi_s}")
    else:
        print("  Load eğrisi için belirgin lineer bölge bulunamadı.")

    # ---- 8. Çıktılar ----
    print("\n[7/7] Grafikler ve CSV çıktıları...")

    # CSV'ler
    df.to_csv(OUTPUT_DIR / "cleaned_data_v2.csv", index=False)

    curve_df = pd.DataFrame({
        "soc_pct": grid_soc,
        "v_rest_smooth": v_rest_smooth,
        "v_load_smooth": v_load_smooth,
    })
    if rest_interp is not None:
        curve_df["v_load_from_rest_minus_sag"] = v_load_from_rest
    curve_df.to_csv(OUTPUT_DIR / "soc_curves_v2.csv", index=False)

    if len(trans_df) > 0:
        trans_df.to_csv(OUTPUT_DIR / "transitions_v2.csv", index=False)

    r_table = pd.DataFrame({
        "v_bin_center": r_bin_v,
        "r_ohm_median": r_bin_r,
        "r_mohm_median": r_bin_r * 1000,
    })
    r_table.to_csv(OUTPUT_DIR / "r_vs_voltage_v2.csv", index=False)

    # Grafikler
    if len(trans_df) > 0:
        plot_r_vs_voltage(trans_df, r_func, r_bin_v, r_bin_r, r_median)
        plot_r_vs_soc(trans_df, soc_r_centers, soc_r_medians)
        plot_r_histogram(trans_df, r_median)

    plot_soc_curves(grid_soc, v_rest_smooth, v_load_smooth,
                    rest_bx, rest_by,
                    linear_range_rest, linear_range_load)
    plot_scatter_validation(df, grid_soc, v_rest_smooth, v_load_smooth, r_func)
    plot_time_trace(df)
    plot_linearity(grid_soc, r2_rest, r2_load, slopes_rest, slopes_load,
                   linear_range_rest, linear_range_load)
    plot_soc_over_time(df)

    # Terminal çıktıları
    print_practical_table(rest_interp, r_func, grid_soc, v_rest_smooth)
    # print_voltage_conversion_table(rest_interp, r_func)  # çok uzun, isteğe göre

    # Özet
    print("\n" + "=" * 60)
    print("ÖZET")
    print("=" * 60)
    print(f"Global R_internal median: {r_median*1000:.2f} mΩ")
    if len(r_bin_v) > 0:
        print(f"R(V) aralığı: {r_bin_r.min()*1000:.2f} – {r_bin_r.max()*1000:.2f} mΩ")
    print(f"Transition sayısı: {len(trans_df)}")
    print(f"Toplam veri noktası: {len(df)}")
    print(f"Test süresi: {df['t_min'].max():.1f} dakika")
    print(f"SOC aralığı: {df['soc_pct'].min():.1f}% – {df['soc_pct'].max():.1f}%")

    if linear_range_rest:
        lo, hi = linear_range_rest
        v_lo = float(rest_interp(lo)) if rest_interp else np.nan
        v_hi = float(rest_interp(hi)) if rest_interp else np.nan
        print(f"\nLineer bölge (dinlenmiş):")
        print(f"  SOC: {hi:.0f}% – {lo:.0f}%")
        v_lo_str = f"{v_lo:.3f}V" if np.isfinite(v_lo) else "N/A"
        v_hi_str = f"{v_hi:.3f}V" if np.isfinite(v_hi) else "N/A"
        print(f"  Voltaj: {v_lo_str} – {v_hi_str}")
        # Eğim hesapla — doğrudan smooth eğriden
        if np.isfinite(v_lo) and np.isfinite(v_hi) and abs(hi - lo) > 0.5:
            slope_mv = (v_hi - v_lo) / (hi - lo) * 1000.0  # mV/%SOC
            print(f"  Eğim: {slope_mv:.2f} mV / % SOC")

    if linear_range_load:
        lo, hi = linear_range_load
        v_lo = float(load_interp(lo)) if load_interp else np.nan
        v_hi = float(load_interp(hi)) if load_interp else np.nan
        print(f"\nLineer bölge (yüklü, ~{REFERENCE_LOAD_A:.0f}A):")
        print(f"  SOC: {hi:.0f}% – {lo:.0f}%")
        v_lo_str = f"{v_lo:.3f}V" if np.isfinite(v_lo) else "N/A"
        v_hi_str = f"{v_hi:.3f}V" if np.isfinite(v_hi) else "N/A"
        print(f"  Voltaj: {v_lo_str} – {v_hi_str}")
        if np.isfinite(v_lo) and np.isfinite(v_hi) and abs(hi - lo) > 0.5:
            slope_mv = (v_hi - v_lo) / (hi - lo) * 1000.0
            print(f"  Eğim: {slope_mv:.2f} mV / % SOC")

    print("\n" + "=" * 60)
    print("UÇUŞ PLANLAMA TAVSİYELERİ")
    print("=" * 60)
    if rest_interp is not None:
        # En düşük güvenli voltaj (SOC 20%)
        v_safe_rest = float(rest_interp(20))
        r_at_safe = float(r_func(v_safe_rest))
        v_safe_load = v_safe_rest - r_at_safe * REFERENCE_LOAD_A
        print(f"Güvenli alt sınır (SOC 20%):")
        print(f"  Dinlenmiş voltaj: {v_safe_rest:.3f}V")
        print(f"  {REFERENCE_LOAD_A:.0f}A yük altı voltaj: {v_safe_load:.3f}V")

        # Acil durum sınırı (SOC 10%)
        v_emerg_rest = float(rest_interp(10))
        r_at_emerg = float(r_func(v_emerg_rest))
        v_emerg_load = v_emerg_rest - r_at_emerg * REFERENCE_LOAD_A
        print(f"\nAcil durum sınırı (SOC 10%):")
        print(f"  Dinlenmiş voltaj: {v_emerg_rest:.3f}V")
        print(f"  {REFERENCE_LOAD_A:.0f}A yük altı voltaj: {v_emerg_load:.3f}V")

        print(f"\n💡 Test uçuşu planı:")
        print(f"  1. Tam şarjla başla (4.2V/cell)")
        if linear_range_rest:
            lo, hi = linear_range_rest
            print(f"  2. Lineer bölge: SOC {hi:.0f}%–{lo:.0f}% arası")
            print(f"     Bu bölgede 10dk uçup X mesafe gittiysen,")
            print(f"     15dk uçarsan 1.5X mesafe gidersin (lineer extrapolasyon geçerli)")
        print(f"  3. İnince multimetre ile cell voltajını ölç (dinlenmiş)")
        print(f"  4. Yukarıdaki tablodan SOC'yi oku")
        print(f"  5. {v_safe_rest:.2f}V altına indirme (SOC 20%)")

    # Dosya listesi
    print(f"\nOluşturulan dosyalar:")
    for p in sorted(OUTPUT_DIR.iterdir()):
        if p.name.endswith("_v2.csv") or p.name.endswith("_v2.png"):
            print(f"  - {p}")


if __name__ == "__main__":
    main()
