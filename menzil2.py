# TARIK ZİYA İNCİ VE FURKAN DEMİRYÜREK TARAFINDAN ÖZENLE HAZIRLANDI

import math
import sys
import csv
import re
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class BauersfeldMenzilHesaplayici:
    def __init__(self,
                 hover_power_w,  # Hover Gücü
                 correction_factor,  # Correction Factor
                 battery_wh,  # Batarya Enerjisi
                 total_mass_kg,  # Toplam Kütle
                 drag_area_cm2,  # A (Makalede Surface Area)
                 prop_diameter_inch,  # Pervane Çapı
                 num_rotors):  # Motor Sayısı

        self.P_h_measured = hover_power_w
        self.cf = correction_factor
        self.energy_wh = battery_wh
        self.m = total_mass_kg
        self.A_ref = drag_area_cm2  # Makale katsayıları cm^2 bazlıdır!
        self.Nr = num_rotors

        # Fiziksel Sabitler
        self.g = 9.81
        self.rho = 1.225

        # Pervane Alanı (Tek pervane değil, toplam disk)
        self.r_prop = (prop_diameter_inch * 0.0254) / 2.0
        self.A_prop = math.pi * (self.r_prop ** 2)

        # Hover İndüklenen Hız (vi,h)
        # Eq 4: vi,h = sqrt(mg / 2*rho*pi*r^2*Nr)
        numerator = self.m * self.g
        denominator = 2 * self.rho * math.pi * (self.r_prop ** 2) * self.Nr
        self.vi_h = math.sqrt(numerator / denominator)

        # KATSAYILAR (Tablo II)
        # Range (Menzil) Katsayıları
        self.c0_r = 0.041546
        self.c1_r = 0.041122
        self.c2_r = 0.00053292

        # Endurance (Dayanım) Katsayıları
        self.c0_e = 0.10188
        self.c1_e = 0.071358
        self.c2_e = 0.0007381

    def solve(self):
        # Optimal Hızları Hesapla (Eq 18)
        # Formül: v_opt = vi,h / (c0 + c1*vi,h + c2*A)

        # 1. Maksimum Menzil Hızı (v_range)
        denom_r = self.c0_r + (self.c1_r * self.vi_h) + (self.c2_r * self.A_ref)
        v_range_ms = self.vi_h / denom_r

        # 2. Maksimum Dayanım Hızı (v_endurance) - (Genelde hover'dan biraz hızlıdır)
        denom_e = self.c0_e + (self.c1_e * self.vi_h) + (self.c2_e * self.A_ref)
        v_endurance_ms = self.vi_h / denom_e

        # Güç Tüketimlerini Hesapla (Eq 17)
        # Makale diyor ki:
        # P_range = 1.092 * P_hover
        # P_endurance = 0.914 * P_hover

        # Burada ölçülen P_hover'ı baz alıyoruz (Correction Factor uygulanmamış ham güç)
        P_range_w = 1.092 * self.P_h_measured
        P_endurance_w = 0.914 * self.P_h_measured

        # Süre ve Menzil Hesabı
        # Menzil Modu İçin:
        flight_time_hours_r = (self.energy_wh / P_range_w) * self.cf
        max_range_km = (v_range_ms * 3.6) * flight_time_hours_r

        # Dayanım Modu İçin:
        flight_time_hours_e = (self.energy_wh / P_endurance_w) * self.cf
        max_range_km_e = (v_endurance_ms * 3.6) * flight_time_hours_e

        return {
            "vi_h": self.vi_h,
            "max_range_km": max_range_km,
            "optimal_speed_ms": v_range_ms,
            "flight_time_min_range": flight_time_hours_r * 60,
            "power_range_w": P_range_w,

            "max_endurance_min": flight_time_hours_e * 60,
            "optimal_endurance_speed_ms": v_endurance_ms,
            "power_endurance_w": P_endurance_w,
            "max_range_km_endurance": max_range_km_e
        }


# VERİ SETLERİ (DATASHEETS) 

# 1. P80 III KV100 + MF Pervane (Referans - Vibe)
p80_raw_data = [
    [3505, 47.87, 6.23],
    [3744, 47.87, 6.71],
    [3992, 47.85, 7.43],
    [4267, 47.83, 8.2],
    [4565, 47.82, 8.98],
    [4885, 47.80, 9.75],
    [5248, 47.77, 11]
]
p80_thrust_power = [[row[0], row[1] * row[2]] for row in p80_raw_data]

# 2. MN7005 KV115 + P24x7.2 (12S - 48V Test Verisi)
mn7005_thrust_power = [
    [1322, 97], [1408, 105], [1513, 117], [1606, 126],
    [1707, 138], [1807, 150], [1947, 168], [2068, 183],
    [2164, 194], [2280, 210], [2398, 226], [2507, 243],
    [2627, 260], [2756, 278], [2888, 299], [3014, 320],
    [3346, 377], [3605, 421], [4224, 537], [4783, 669]
]

# 3. CM-X6-SE 380KV Technical Parameters HF18*6.0" - 6S
cmx6_old_thrust_power = [
    [892, 86.3], [1042, 103.9], [1199, 123.3], [1361, 144.3],
    [1659, 186.1], [1793, 206.2], [1962, 232.8], [2235, 278.2],
    [2409, 309.0], [2694, 361.9], [2841, 390.4], [3143, 452.3],
    [3299, 485.8], [3582, 548.4], [3748, 586.7], [4046, 657.3],
    [4348, 731.9], [4648, 807.9], [4815, 851.3], [5090, 923.3],
    [5596, 1057.5]
]

# 4. CM-X6-SE HF22*7.0"
cmx6_tech_thrust_power = [
    [1195, 93.9], [1327, 107.9], [1460, 123.0], [1596, 139.1],
    [1802, 165.2], [2013, 193.5], [2229, 223.9], [2449, 256.3],
    [2673, 290.9], [2901, 327.6], [3132, 366.6], [3365, 407.9],
    [3600, 451.7], [3836, 498.0], [4071, 546.8], [4306, 597.9],
    [4538, 651.3], [4768, 706.5], [4993, 763.0], [5213, 820.3],
    [5427, 877.8], [6058, 1051.6]
]

# 5. M5208 HP/UL
m5208_thrust_power = [
    [923, 70.2], [1042, 81.3], [1164, 94.1], [1287, 108.4],
    [1475, 132.3], [1666, 158.8], [1861, 187.4], [2061, 217.8],
    [2265, 250.1], [2473, 284.3], [2688, 320.5], [2907, 359.1],
    [3133, 400.5], [3363, 445.0], [3598, 493.1], [3835, 544.9],
    [4073, 600.2], [4308, 658.6], [4537, 718.7], [4756, 778.7],
    [4957, 836.0], [5399, 964.6]
]

# 6. MN7005 KV230 + P24x7.2
mn7005_kv230_thrust_power = [
    [1407, 105], [1501, 114], [1592, 123], [1698, 136],
    [1837, 152], [1951, 167], [2063, 181], [2153, 194],
    [2261, 209], [2378, 225], [2491, 241], [2605, 259],
    [2708, 273], [2841, 297], [2948, 317], [3060, 336],
    [3344, 387], [3632, 438], [4184, 551], [4691, 670]
]

# 7. U8 Lite KV150 (6S - 24V) + G29*9.5" CF
u8lite_kv150_thrust_power = [
    [1296, 77], [1416, 86], [1509, 94], [1654, 106],
    [1728, 113], [1833, 125], [2006, 139], [2128, 151],
    [2243, 166], [2357, 182], [2486, 192], [2612, 206],
    [2707, 218], [2862, 235], [2995, 252], [3142, 276],
    [3469, 317], [3774, 365], [4536, 475], [5378, 629]
]

# 7. M8108 Light 150KV + MSC 28x9.2 (23V - 6S Test Verisi)
m8108_light_data = [
    [871, 47.2], [968, 53.7], [1070, 61.2], [1178, 69.5],
    [1349, 83.6], [1529, 99.6], [1720, 117.4], [1919, 137.0],
    [2127, 158.4], [2344, 181.6], [2569, 206.7], [2802, 234.0],
    [3043, 263.5], [3290, 295.3], [3542, 329.6], [3798, 366.3],
    [4054, 404.9], [4307, 445.0], [4554, 485.3], [4789, 524.7],
    [5005, 561.3], [5483, 640.0]
]

# 8. M6208 155KV + MSC 21x6.3 (12S - 46V Test Verisi)
m6208_12s_data = [
    [853, 67.7], [953, 77.8], [1075, 90.2], [1212, 104.6],
    [1440, 129.2], [1683, 157.2], [1934, 188.1], [2185, 221.7],
    [2436, 257.7], [2684, 296.1], [2931, 336.7], [3178, 379.8],
    [3428, 425.8], [3684, 475.0], [3949, 528.1], [4225, 585.5],
    [4512, 647.4], [4812, 714.2], [5121, 785.7], [5435, 861.4],
    [5748, 940.3], [6582, 1180.0]
]

# 9. M8108 Light 150KV + MSC 29x9.5 (23V - 6S Test Verisi)
m8108_light_29in_data = [
    [869, 46.1], [963, 52.4], [1064, 59.6], [1171, 67.8],
    [1341, 81.7], [1522, 97.6], [1712, 115.2], [1911, 134.4],
    [2117, 155.4], [2332, 178.1], [2555, 202.5], [2786, 228.9],
    [3026, 257.4], [3273, 288.2], [3528, 321.4], [3788, 356.9],
    [4050, 394.7], [4312, 434.1], [4569, 474.2], [4814, 513.8],
    [5040, 551.1], [5517, 629.8]
]

# 10. MN601S KV170 + T-MOTOR P21x6.3 (12S - 48V Test Verisi)
mn601s_kv170_data = [
    [1677, 149], [1774, 168], [1966, 192], [2062, 206],
    [2182, 221], [2307, 244], [2463, 264], [2624, 287],
    [2726, 316], [2912, 340], [3027, 359], [3165, 382],
    [3366, 420], [3485, 444], [3641, 468], [3799, 496],
    [4186, 576], [4593, 661], [5412, 858], [6605, 1166]
]

# 11. U10II KV100 + G32x11" (8S - 32V Test Verisi)
u10ii_kv100_data = [
    [1651, 105], [1761, 113], [1882, 124], [2000, 135],
    [2133, 147], [2257, 159], [2403, 171], [2538, 186],
    [2689, 200], [2828, 217], [2935, 233], [2964, 250],
    [3245, 269], [3418, 285], [3511, 304], [3739, 324],
    [4119, 375], [4535, 430], [5518, 571], [6430, 722]
]

# 12. U10II KV100 + G30x10.5" (8S - 32V Test Verisi)
u10ii_kv100_30in_data = [
    [1405, 85], [1487, 91], [1597, 100], [1714, 109],
    [1817, 118], [1934, 128], [2048, 138], [2180, 150],
    [2307, 163], [2431, 176], [2586, 190], [2749, 205],
    [2879, 219], [3032, 236], [3161, 252], [3297, 266],
    [3655, 309], [4144, 367], [4899, 465], [5717, 593]
]

# 13. MN6007 II KV320 + P22x6.6" (6S - 24V Test Verisi)
mn6007ii_kv320_data = [
    [1737, 160], [1878, 178], [2080, 208], [2178, 223],
    [2297, 241], [2431, 262], [2565, 283], [2696, 304],
    [2803, 320], [2925, 342], [3059, 369], [3185, 392],
    [3311, 416], [3454, 445], [3573, 469], [3704, 496],
    [4347, 636], [5084, 814], [5882, 1041]
]

# 14. MN6007 II KV160 + P21x6.3" (12S - 48V Test Verisi)
mn6007ii_kv160_data = [
    [1444, 126], [1563, 141], [1760, 161], [1875, 180],
    [2006, 199], [2125, 215], [2249, 233], [2355, 251],
    [2488, 270], [2624, 293], [2762, 314], [2892, 338],
    [3030, 362], [3160, 390], [3243, 402], [3388, 426],
    [4118, 569], [4889, 738], [5838, 978]
]

# 15. U8 Lite KV150 + G30x10.5" (6S - 24V Test Verisi)
u8lite_kv150_g30_data = [
    [1551, 91], [1684, 103], [1766, 110], [1850, 120],
    [1991, 137], [2132, 149], [2256, 161], [2420, 178],
    [2536, 190], [2676, 204], [2816, 221], [2923, 235],
    [3097, 257], [3229, 276], [3334, 290], [3475, 310],
    [3917, 370], [4237, 420], [5020, 547], [5912, 713]
]

# 16. U8 Lite KV190 + G29*9.5" CF (6S - 24V)
u8lite_kv190_g29_data = [
    [2035, 149], [2173, 166], [2328, 180], [2486, 199],
    [2627, 218], [2812, 238], [2961, 257], [3195, 288],
    [3344, 312], [3502, 341], [3669, 353], [3833, 389],
    [4005, 410], [4214, 442], [4365, 468], [4782, 540],
    [5184, 610], [6026, 773], [7334, 1049]
]

# 17. U8 Lite KV190 + G28x9.2" (6S - 24V Test Verisi)
u8lite_kv190_data = [
    [1662, 115], [1806, 130], [1951, 144], [2134, 163],
    [2254, 173], [2401, 194], [2566, 214], [2774, 240],
    [2892, 252], [3081, 278], [3208, 298], [3389, 324],
    [3502, 338], [3623, 360], [3801, 379], [3934, 408],
    [4376, 470], [4816, 542], [5563, 696], [6761, 929]
]

# 17. U8II KV85 + G28x9.2" (12S - 48V Test Verisi)
u8ii_kv85_data = [
    [1465, 86], [1572, 96], [1717, 110], [1852, 125],
    [1997, 139], [2140, 154], [2256, 163], [2378, 178],
    [2528, 197], [2757, 221], [2957, 245], [3027, 254],
    [3171, 274], [3307, 298], [3448, 317], [3662, 341],
    [4043, 394], [4468, 456], [5248, 586], [6352, 792]
]

# 18. T-MOTOR P80 MF3218 (12S - 48V Test Verisi)
# Not: Görsellerdeki Thrust (g) ve Power (W) değerleri birleştirildi.
mf3218_data = [
    [3505, 298], [3744, 321], [3992, 356], [4267, 392],
    [4565, 429], [4885, 466], [5248, 525], [5592, 570],
    [6039, 632], [6510, 699], [7018, 777], [7408, 843],
    [7803, 911], [8227, 979], [8732, 1065], [9167, 1146],
    [10531, 1414], [11825, 1700], [13079, 1988], [14412, 2312],
    [15849, 2671]
]

# 19. T-MOTOR P60 KV170 + P22x6.6 (12S - 48V Test Verisi)
p60_kv170_data = [
    [2801, 316.8], [3312, 412.8], [3763, 475.2], [4356, 595.2],
    [2801, 316.8], [3312, 412.8], [3763, 475.2], [4356, 595.2],
    [5372, 820.8], [6582, 1113.6], [8414, 1632]
]

# 20. U10II KV100 + G28*9.2" CF (12S - 48V) - NEW
u10ii_kv100_new_data = [
    [2087, 167], [2298, 187], [2425, 208], [2732, 226],
    [3007, 262], [3119, 279], [3376, 305], [3578, 327],
    [3722, 351], [3947, 379], [4053, 401], [4348, 437],
    [4507, 459], [4692, 488], [4846, 516], [5115, 553],
    [5496, 610], [6070, 709], [7285, 922], [8629, 1176]
]

# 21. U8 Lite KV150 + G29*9.5" CF (6S - 24V) - NEW
u8lite_kv150_new_data = [
    [1296, 77], [1416, 86], [1509, 94], [1654, 106],
    [1728, 113], [1833, 125], [2006, 139], [2128, 151],
    [2243, 166], [2357, 182], [2486, 192], [2612, 206],
    [2707, 218], [2862, 235], [2995, 252], [3142, 276],
    [3469, 317], [3774, 365], [4536, 475], [5378, 629]
]

# 22. U8II-X KV100 (Alpha 60A 12S) + MF2815 (12S - 48V) - NEW
u8iix_kv100_data = [
    [2088, 167], [2594, 224], [3145, 293], [3747, 375],
    [4384, 470], [5028, 579], [5740, 703], [6440, 842],
    [7115, 992], [7771, 1156], [8403, 1331], [8903, 1491],
    [9082, 1569]
]

# 23. Yıldızlar İyi Motor - 24V (6S LIPO) + HQ9x5x3 Propeller
yildizlar_iyi_motor_data = [
    [784, 129], [1263, 267], [1736, 435], [2300, 649],
    [3062, 935], [3910, 1304], [4279, 1535]
]

# 24. Yıldızlar Kötü Motor - SE 3115 900KV + HQ 9x5x3 (6S - 24V)
yildizlar_kotu_motor_data = [
    [265, 45.36], [835, 189.00], [1321, 332.64], [1987, 599.89],
    [2838, 1012.50], [3249, 1289.60], [3656, 1530.16], [3784, 1596.54]
]

# 25. Yıldızlar Geçen Sene Motoru - DAL T5045 Tri-blade
yildizlar_gecen_sene_data = [
    [96, 16.00], [221, 49.60], [326, 81.60], [407, 113.60],
    [499, 145.60], [579, 177.60], [645, 209.60], [719, 241.60],
    [792, 273.60], [855, 305.60], [918, 339.20], [976, 369.60],
    [1041, 401.60], [1103, 433.60], [1160, 465.60], [1215, 496.00],
    [1281, 537.60]
]

# 26. Yıldızlar Sanal Ortalama Motor - (İyi ve Kötü Motor Ortalaması)
yildizlar_sanal_ortalama_data = [
    [265, 22.68], [784, 152.57], [835, 166.35], [1263, 291.25],
    [1321, 310.12], [1736, 467.08], [1987, 565.06], [2300, 700.32],
    [2838, 931.71], [3062, 1049.26], [3249, 1152.99], [3656, 1361.82],
    [3784, 1422.86]
]


# --- FONKSİYONLAR ---

def interpolate(value, x_list, y_list):
    if value < x_list[0]: return y_list[0]
    if value > x_list[-1]: return y_list[-1]
    for i in range(len(x_list) - 1):
        if x_list[i] == x_list[i + 1]: continue
        if x_list[i] <= value <= x_list[i + 1]:
            x1, x2 = x_list[i], x_list[i + 1]
            y1, y2 = y_list[i], y_list[i + 1]
            slope = (y2 - y1) / (x2 - x1)
            return y1 + slope * (value - x1)
    return y_list[-1]


def get_power_from_thrust(thrust, data_list):
    thrusts = [d[0] for d in data_list]
    powers = [d[1] for d in data_list]
    return interpolate(thrust, thrusts, powers)


def _det3(m):
    """3x3 matris determinantı (Cramer kuralı için)"""
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
          - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
          + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def quadratic_regression(data_list):
    """Kuadratik regresyon: power = a*thrust^2 + b*thrust + c
    Tüm veri noktalarına en küçük kareler yöntemiyle 2. derece polinom uydurur."""
    n = len(data_list)
    sx  = sum(d[0] for d in data_list)
    sy  = sum(d[1] for d in data_list)
    sx2 = sum(d[0]**2 for d in data_list)
    sx3 = sum(d[0]**3 for d in data_list)
    sx4 = sum(d[0]**4 for d in data_list)
    sxy = sum(d[0] * d[1] for d in data_list)
    sx2y = sum(d[0]**2 * d[1] for d in data_list)

    # Normal denklemler: A·[a,b,c]^T = rhs
    A_mat = [[sx4, sx3, sx2],
             [sx3, sx2, sx],
             [sx2, sx,  n]]
    det_A = _det3(A_mat)

    if abs(det_A) < 1e-12:
        # Dejenere durum — lineer fallback
        return 0, sy / max(sx, 1e-12), 0

    a = _det3([[sx2y, sx3, sx2], [sxy, sx2, sx], [sy, sx, n]]) / det_A
    b = _det3([[sx4, sx2y, sx2], [sx3, sxy, sx], [sx2, sy, n]]) / det_A
    c = _det3([[sx4, sx3, sx2y], [sx3, sx2, sxy], [sx2, sx, sy]]) / det_A

    return a, b, c


def get_power_from_thrust_quadratic(thrust, data_list):
    """Aralık içinde lineer interpolasyon, aralık dışında kuadratik regresyon ile ekstrapolasyon."""
    thrusts = [d[0] for d in data_list]

    # Veri aralığı içindeyse normal interpolasyon kullan
    if thrusts[0] <= thrust <= thrusts[-1]:
        return get_power_from_thrust(thrust, data_list)

    # Aralık dışı: kuadratik regresyon ile ekstrapolasyon
    a, b, c = quadratic_regression(data_list)
    power = a * (thrust ** 2) + b * thrust + c
    return max(0, power)  # Negatif güç fiziksel olarak anlamsız


def calculate_poly_coeffs(v_e, v_r):
    # Solves y = ax^2 + bx + 1 for (0,1), (ve, 0.914), (vr, 1.092)
    d_Pe = 0.914 - 1.0
    d_Pr = 1.092 - 1.0
    
    numerator = d_Pe * v_r - d_Pr * v_e
    denominator = v_e * v_r * (v_e - v_r)
    
    if denominator == 0:
        return 0, 0, 1
        
    a = numerator / denominator
    b = (d_Pe / v_e) - a * v_e
    
    return a, b


FIRFIR_SPEED_PRESET = {
    "vehicle_name": "Firfir",
    "mass_kg": 12.4,
    "num_rotors": 4,
    "prop_diameter_inch": 29.0,
    "blade_count": 2,
    "rho": 1.225,
    "utip_ms": 80.0,
    "hover_rpm_estimate": 2047.0,
    "rotor_solidity_s": 0.05,
    "mean_blade_chord_m": 0.029,
    "blade_profile_drag_delta": 0.012,
    "induced_correction_k": 0.1,
    "eta_propulsion": 1.0,
    "p_hotel_w": 0.0,
    "body_area_m2": 0.045,
    "cda_body_m2": 0.38,
    "cda_pitch_m2": 0.38,
    "pitch_measurement_speed_ms": 6.04,
    "pitch_measurement_deg": 4.0,
    "p_endurance_ratio": 0.914,
    "p_range_ratio": 1.092,
}

FIRFIR_ATTITUDE_LOG_CANDIDATES = [
    "flight_attitude_00000075.csv",
    "flight_attitude_00000075_armed.csv",
]
FIRFIR_DATALINK_ROOT_CANDIDATES = [
    "Datalink Data From my Retarded Friend/datalink",
]
FIRFIR_ARDUPILOT_BIN_GLOBS = [
    "D:/Tak*/it* ikinci sene/Loglar/Drone 0.0/*.BIN",
]
DATALINK_EXPECTED_MOTOR_COUNT = 4
DATALINK_RECORD_HEADER_BYTES = 32
DATALINK_RECORD_BYTES = 160
DATALINK_SLOT_BYTES = 19
DATALINK_DEFAULT_SAMPLE_HZ = 20.0
DATALINK_CURRENT_SCALE = 100.0
DATALINK_SPEED_BIN_WIDTH_MS = 1.0
DATALINK_MIN_BIN_SAMPLES = 80
DATALINK_DATE_HINT_ENV = "MENZIL_DATALINK_DATE_HINT"
DATALINK_MEASURED_CURVE_DATE_HINT = "260703"
DATALINK_MEASURED_EXTRAPOLATION_START_MS = 18.0
DATALINK_MEASURED_OUTPUT_PREFIX = "measured_datalink_power_curve"
DATALINK_EMPIRICAL_OUTPUT_PATH = "empirical_datalink_power_curve.png"
DATALINK_EMPIRICAL_COMPARISON_RANGE_OUTPUT_PATH = "datalink_empirical_model_comparison_range_time.png"
DATALINK_EMPIRICAL_COMPARISON_POWER_OUTPUT_PATH = "datalink_empirical_model_comparison_power_ratio.png"
DATALINK_DIAGNOSTIC_SURROGATE_OUTPUT_PATH = "diagnostic_datalink_surrogate_fits.png"
DATALINK_SCIENTIFIC_AUDIT_PATH = "scientific_model_fit_audit.md"
DATALINK_EMPIRICAL_COMPANION_MODELS = (
    "hybrid_calibrated_zeng_fit",
    "faessler_drag_constrained_zeng",
    "kirschstein_component_benchmark",
)
DATALINK_DATASHEET_UTIP_RANGE_MS = (120.0, 230.0)
DATALINK_FIRFIR_LAMBDA_ACCEPTANCE_N_PER_MS = (0.3, 3.5)
DATALINK_BODY_CD_MAX = 5.0

FIRFIR_STADIUM_LAP_VOLTAGES_V = [
    23.00, 22.9, 22.8, 22.8, 22.7,
    22.6, 22.6, 22.5, 22.4, 22.4,
]
FIRFIR_STADIUM_LAP_DISTANCE_M = 280.0
FIRFIR_STADIUM_SPEED_MS = 6.0
FIRFIR_STADIUM_CELLS = 6
FIRFIR_STADIUM_SAG_OPTIONS_PER_CELL = [0.03, 0.10, 0.20]
FIRFIR_STADIUM_DEFAULT_SAG_PER_CELL = 0.10
FIRFIR_DATALINK_QC_EXPECTED_6MS_PPH_BAND = (0.89, 0.92)
FIRFIR_DATALINK_QC_DEFAULT_6MS_PPH = 0.914

# Rest-voltage anchors from ham_ucus_verileri.md for the 6S Li-ion solid-state pack.
FIRFIR_REST_VOLTAGE_SOC_ANCHORS = [
    (4.178, 100.0),
    (3.815, 100.0 * (1.0 - 11.6 / 25.2)),
    (3.718, 100.0 * (1.0 - 14.9 / 25.2)),
    (3.643, 100.0 * (1.0 - 17.7 / 25.2)),
    (3.360, 0.0),
]


def tip_speed_from_rpm(prop_diameter_inch, rpm):
    diameter_m = prop_diameter_inch * 0.0254
    return math.pi * diameter_m * rpm / 60.0


def zeng_induced_ratio(speed_ms, v0_ms):
    if v0_ms <= 0:
        return 1.0
    v = max(0.0, speed_ms)
    inner = math.sqrt(1.0 + (v ** 4) / (4.0 * v0_ms ** 4)) - (v ** 2) / (2.0 * v0_ms ** 2)
    return math.sqrt(max(inner, 0.0))


def zeng_profile_ratio(speed_ms, utip_ms):
    if utip_ms <= 0:
        raise ValueError("Utip must be positive.")
    return 1.0 + 3.0 * (speed_ms ** 2) / (utip_ms ** 2)


def fit_bauersfeld_anchored_zeng(v_endurance, v_range, v0_ms, utip_ms,
                                 p_endurance_ratio=0.914, p_range_ratio=1.092):
    be = zeng_profile_ratio(v_endurance, utip_ms)
    br = zeng_profile_ratio(v_range, utip_ms)
    ie = zeng_induced_ratio(v_endurance, v0_ms)
    ir = zeng_induced_ratio(v_range, v0_ms)

    # p(V)=f0*profile_ratio(V)+(1-f0)*induced_ratio(V)+k_par*V^3
    a11 = be - ie
    a12 = v_endurance ** 3
    a21 = br - ir
    a22 = v_range ** 3
    y1 = p_endurance_ratio - ie
    y2 = p_range_ratio - ir
    det = a11 * a22 - a12 * a21
    if abs(det) < 1e-12:
        raise ValueError("Bauersfeld-anchored Zeng fit is singular.")

    f0 = (y1 * a22 - a12 * y2) / det
    k_par = (a11 * y2 - y1 * a21) / det
    return {
        "v0_ms": v0_ms,
        "utip_ms": utip_ms,
        "f0": f0,
        "induced_fraction": 1.0 - f0,
        "k_par": k_par,
        "p_endurance_ratio": p_endurance_ratio,
        "p_range_ratio": p_range_ratio,
    }


def power_ratio_bauersfeld_anchored_zeng(speed_ms, params):
    return (
        params["f0"] * zeng_profile_ratio(speed_ms, params["utip_ms"])
        + params["induced_fraction"] * zeng_induced_ratio(speed_ms, params["v0_ms"])
        + params["k_par"] * speed_ms ** 3
    )


def build_theoretical_zeng_params(model_profile, hover_power_reference_w):
    rho = model_profile["rho"]
    mass_kg = model_profile["mass_kg"]
    num_rotors = model_profile["num_rotors"]
    diameter_m = model_profile["prop_diameter_inch"] * 0.0254
    radius_m = diameter_m / 2.0
    area_one_m2 = math.pi * radius_m ** 2
    area_total_m2 = num_rotors * area_one_m2
    weight_n = mass_kg * 9.81
    utip_ms = model_profile["utip_ms"]
    solidity_s = model_profile["rotor_solidity_s"]
    delta = model_profile["blade_profile_drag_delta"]
    k_induced = model_profile["induced_correction_k"]
    eta = model_profile["eta_propulsion"]
    p_hotel_w = model_profile["p_hotel_w"]
    cda_body_m2 = model_profile.get(
        "cda_body_m2",
        model_profile.get("cda_pitch_m2", 0.045),
    )
    blade_count = model_profile.get("blade_count", 2)

    v0_ms = math.sqrt(weight_n / (2.0 * rho * area_total_m2))
    p0_mech = (delta / 8.0) * rho * solidity_s * area_total_m2 * utip_ms ** 3
    pi_mech = (1.0 + k_induced) * (weight_n ** 1.5) / math.sqrt(2.0 * rho * area_total_m2)
    equivalent_chord_m = solidity_s * math.pi * radius_m / blade_count

    return {
        "rho": rho,
        "mass_kg": mass_kg,
        "num_rotors": num_rotors,
        "radius_m": radius_m,
        "area_total_m2": area_total_m2,
        "v0_ms": v0_ms,
        "utip_ms": utip_ms,
        "rotor_solidity_s": solidity_s,
        "equivalent_chord_m": equivalent_chord_m,
        "delta": delta,
        "k_induced": k_induced,
        "eta_propulsion": eta,
        "p_hotel_w": p_hotel_w,
        "body_area_m2": model_profile.get("body_area_m2", cda_body_m2),
        "cda_body_m2": cda_body_m2,
        "p0_mech": p0_mech,
        "pi_mech": pi_mech,
        "hover_power_reference_w": hover_power_reference_w,
    }


def power_theoretical_zeng(speed_ms, params):
    v = max(0.0, speed_ms)
    profile = params["p0_mech"] * zeng_profile_ratio(v, params["utip_ms"])
    induced = params["pi_mech"] * zeng_induced_ratio(v, params["v0_ms"])
    parasite = 0.5 * params["rho"] * params["cda_body_m2"] * v ** 3
    total_mech = profile + induced + parasite
    return total_mech / params["eta_propulsion"] + params["p_hotel_w"]


def _percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = int(round((len(sorted_values) - 1) * fraction))
    idx = max(0, min(len(sorted_values) - 1, idx))
    return sorted_values[idx]


def _median(values):
    if not values:
        return None
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return 0.5 * (values[mid - 1] + values[mid])


def _sorted_unique_strings(values):
    return sorted({str(value) for value in values if value not in (None, "")})


def soc_from_rest_cell_voltage(v_cell):
    pairs = sorted(FIRFIR_REST_VOLTAGE_SOC_ANCHORS)
    if v_cell <= pairs[0][0]:
        return pairs[0][1]
    if v_cell >= pairs[-1][0]:
        return pairs[-1][1]
    for (v0, soc0), (v1, soc1) in zip(pairs, pairs[1:]):
        if v0 <= v_cell <= v1:
            t = (v_cell - v0) / (v1 - v0)
            return soc0 + t * (soc1 - soc0)
    return pairs[-1][1]


def find_attitude_log_path(profile):
    explicit = profile.get("attitude_log_csv")
    candidates = [explicit] if explicit else []
    candidates.extend(FIRFIR_ATTITUDE_LOG_CANDIDATES)

    base_dir = Path(__file__).resolve().parent
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_absolute():
            path = base_dir / path
        if path.exists():
            return path
    return None


def load_attitude_rows(csv_path):
    rows = []
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            try:
                time_s = float(raw.get("time_s", raw.get("TimeS", "")))
                pitch_deg = float(raw.get("pitch_deg", raw.get("Pitch", "")))
                roll_deg = float(raw.get("roll_deg", raw.get("Roll", "")))
                if raw.get("speed_xy_ms"):
                    vx_ms = float(raw["speed_xy_ms"])
                    vy_ms = 0.0
                else:
                    vx_ms = float(raw.get("vx_ms", raw.get("VN", "")))
                    vy_ms = float(raw.get("vy_ms", raw.get("VE", "")))
            except (TypeError, ValueError):
                continue
            values = [time_s, vx_ms, vy_ms, pitch_deg, roll_deg]
            if all(math.isfinite(v) for v in values):
                rows.append({
                    "time_s": time_s,
                    "vx_ms": vx_ms,
                    "vy_ms": vy_ms,
                    "pitch_deg": pitch_deg,
                    "roll_deg": roll_deg,
                })
    rows.sort(key=lambda row: row["time_s"])
    return rows


def estimate_cda_from_attitude_log(profile, min_speed_ms=3.0, max_speed_ms=7.2,
                                   max_accel_ms2=0.8, max_tilt_deg=25.0):
    path = find_attitude_log_path(profile)
    if not path:
        return None

    rows = load_attitude_rows(path)
    if len(rows) < 5:
        return None

    rho = profile.get("rho", 1.225)
    mass_kg = profile["mass_kg"]
    weight_n = mass_kg * 9.81
    cda_values = []
    used_speeds = []
    used_accels = []
    bin_samples = {}
    bin_width_ms = 0.5

    for idx, row in enumerate(rows):
        if idx == 0 or idx == len(rows) - 1:
            accel_xy = float("inf")
        else:
            prev_row = rows[idx - 1]
            next_row = rows[idx + 1]
            dt = next_row["time_s"] - prev_row["time_s"]
            if dt <= 0 or dt > 1.0:
                accel_xy = float("inf")
            else:
                ax = (next_row["vx_ms"] - prev_row["vx_ms"]) / dt
                ay = (next_row["vy_ms"] - prev_row["vy_ms"]) / dt
                accel_xy = math.hypot(ax, ay)

        speed_ms = math.hypot(row["vx_ms"], row["vy_ms"])
        pitch_rad = math.radians(row["pitch_deg"])
        roll_rad = math.radians(row["roll_deg"])
        cos_tilt = math.cos(pitch_rad) * math.cos(roll_rad)
        tilt_rad = math.acos(max(-1.0, min(1.0, cos_tilt)))
        tilt_deg = math.degrees(tilt_rad)

        if not (min_speed_ms <= speed_ms <= max_speed_ms):
            continue
        if accel_xy > max_accel_ms2:
            continue
        if tilt_deg > max_tilt_deg:
            continue

        cda = 2.0 * weight_n * math.tan(tilt_rad) / (rho * speed_ms ** 2)
        if math.isfinite(cda) and 0.02 <= cda <= 5.0:
            cda_values.append(cda)
            used_speeds.append(speed_ms)
            used_accels.append(accel_xy)
            bin_center = round((math.floor(speed_ms / bin_width_ms) + 0.5) * bin_width_ms, 2)
            bin_samples.setdefault(bin_center, []).append(cda)

    if len(cda_values) < 20:
        return {
            "path": path,
            "raw_count": len(rows),
            "sample_count": len(cda_values),
            "error": "not_enough_filtered_samples",
        }

    cda_sorted = sorted(cda_values)
    speed_sorted = sorted(used_speeds)
    accel_sorted = sorted(used_accels)
    p10 = _percentile(cda_sorted, 0.10)
    p90 = _percentile(cda_sorted, 0.90)
    trimmed = [value for value in cda_values if p10 <= value <= p90]
    cda_m2 = _median(trimmed)
    speed_bins = []
    for bin_center, values in sorted(bin_samples.items()):
        if len(values) < 30:
            continue
        sorted_values = sorted(values)
        b10 = _percentile(sorted_values, 0.10)
        b90 = _percentile(sorted_values, 0.90)
        btrim = [value for value in sorted_values if b10 <= value <= b90]
        speed_bins.append({
            "speed_ms": bin_center,
            "sample_count": len(values),
            "cda_m2": _median(btrim),
            "cda_p25_m2": _percentile(sorted_values, 0.25),
            "cda_p75_m2": _percentile(sorted_values, 0.75),
        })

    return {
        "path": path,
        "raw_count": len(rows),
        "sample_count": len(cda_values),
        "rho": rho,
        "cda_m2": cda_m2,
        "cda_p25_m2": _percentile(cda_sorted, 0.25),
        "cda_p75_m2": _percentile(cda_sorted, 0.75),
        "speed_median_ms": _median(used_speeds),
        "speed_p95_ms": _percentile(speed_sorted, 0.95),
        "accel_p95_ms2": _percentile(accel_sorted, 0.95),
        "min_speed_ms": min_speed_ms,
        "max_accel_ms2": max_accel_ms2,
        "speed_bins": speed_bins,
    }


def estimate_stadium_voltage_anchor(hover_power_w, battery_wh, correction_factor):
    voltages = FIRFIR_STADIUM_LAP_VOLTAGES_V
    speed_ms = FIRFIR_STADIUM_SPEED_MS
    hover_20_min = battery_wh / hover_power_w * 60.0 * correction_factor
    hover_range_if_ratio_1 = speed_ms * 3.6 * hover_20_min / 60.0
    candidates = []

    span_options = [
        ("nine_intervals", (len(voltages) - 1) * FIRFIR_STADIUM_LAP_DISTANCE_M / 1000.0),
        ("full_10_laps", len(voltages) * FIRFIR_STADIUM_LAP_DISTANCE_M / 1000.0),
    ]
    for sag_per_cell in FIRFIR_STADIUM_SAG_OPTIONS_PER_CELL:
        rest_soc = [
            soc_from_rest_cell_voltage(v / FIRFIR_STADIUM_CELLS + sag_per_cell)
            for v in voltages
        ]
        delta_soc = rest_soc[0] - rest_soc[-1]
        if delta_soc <= 0:
            continue
        for label, distance_km in span_options:
            range_20_km = distance_km * 80.0 / delta_soc
            ratio = hover_range_if_ratio_1 / range_20_km
            candidates.append({
                "speed_ms": speed_ms,
                "power_ratio": ratio,
                "sag_per_cell": sag_per_cell,
                "span_label": label,
                "distance_km": distance_km,
                "soc_start": rest_soc[0],
                "soc_end": rest_soc[-1],
                "delta_soc": delta_soc,
                "range_20_km": range_20_km,
            })

    preferred = None
    for candidate in candidates:
        if (candidate["span_label"] == "nine_intervals"
                and abs(candidate["sag_per_cell"] - FIRFIR_STADIUM_DEFAULT_SAG_PER_CELL) < 1e-9):
            preferred = candidate
            break
    if preferred is None and candidates:
        preferred = candidates[0]

    return {
        "preferred": preferred,
        "candidates": candidates,
        "hover_20_min": hover_20_min,
        "hover_range_if_ratio_1": hover_range_if_ratio_1,
    }


def _parse_datalink_filename_times(path):
    match = re.search(r"UART-(\d{6})-(\d{6})(?:-(\d{6}))?", Path(path).stem)
    if not match:
        return None, None
    date_part, start_part, end_part = match.groups()
    year = 2000 + int(date_part[0:2])
    month = int(date_part[2:4])
    day = int(date_part[4:6])

    def parse_clock(clock_text):
        return datetime(
            year,
            month,
            day,
            int(clock_text[0:2]),
            int(clock_text[2:4]),
            int(clock_text[4:6]),
        )

    start_dt = parse_clock(start_part)
    end_dt = parse_clock(end_part) if end_part else None
    if end_dt and end_dt < start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def _datalink_naive_to_utc(value, timestamp_mode):
    if value is None:
        return None
    if timestamp_mode in {"filename_trt", "filename_local", "filename_europe_istanbul"}:
        return (value - timedelta(hours=3)).replace(tzinfo=timezone.utc)
    return value.replace(tzinfo=timezone.utc)


def _datalink_session_utc_bounds(session, timestamp_mode):
    return (
        _datalink_naive_to_utc(session["start_naive"], timestamp_mode),
        _datalink_naive_to_utc(session["end_naive"], timestamp_mode),
    )


def parse_datalink_udat_file(path, prop_diameter_inch=29.0,
                             timestamp_mode="filename_utc",
                             current_scale=DATALINK_CURRENT_SCALE,
                             expected_motor_count=DATALINK_EXPECTED_MOTOR_COUNT):
    path = Path(path)
    data = path.read_bytes()
    if len(data) < DATALINK_RECORD_HEADER_BYTES + DATALINK_RECORD_BYTES:
        return {
            "path": path,
            "samples": [],
            "record_count": 0,
            "raw_record_count": 0,
            "error": "file_too_small",
        }
    if not data.startswith(b"LINK-"):
        return {
            "path": path,
            "samples": [],
            "record_count": 0,
            "raw_record_count": 0,
            "error": "unexpected_header",
        }

    raw_record_count = (len(data) - DATALINK_RECORD_HEADER_BYTES) // DATALINK_RECORD_BYTES
    start_naive, end_naive = _parse_datalink_filename_times(path)
    if start_naive and end_naive:
        duration_s = max(1e-9, (end_naive - start_naive).total_seconds())
        sample_rate_hz = raw_record_count / duration_s
    else:
        sample_rate_hz = DATALINK_DEFAULT_SAMPLE_HZ
    start_utc = _datalink_naive_to_utc(start_naive, timestamp_mode)

    samples = []
    active_counts = []
    voltages = []
    currents = []
    powers = []
    rpms = []
    utips = []
    diameter_m = prop_diameter_inch * 0.0254

    for record_idx in range(raw_record_count):
        offset = DATALINK_RECORD_HEADER_BYTES + record_idx * DATALINK_RECORD_BYTES
        record = data[offset:offset + DATALINK_RECORD_BYTES]
        motors = []
        for slot_idx in range(8):
            slot_offset = slot_idx * DATALINK_SLOT_BYTES
            slot = record[slot_offset:slot_offset + DATALINK_SLOT_BYTES]
            if len(slot) < DATALINK_SLOT_BYTES:
                continue
            motor_id = slot[6]
            voltage_v = int.from_bytes(slot[15:17], "big") / 10.0
            current_a = int.from_bytes(slot[17:19], "big") / current_scale
            rpm = int.from_bytes(slot[13:15], "big")
            if motor_id < 1 or motor_id > expected_motor_count:
                continue
            if not (10.0 <= voltage_v <= 30.0):
                continue
            if not (0.0 <= current_a <= 100.0):
                continue
            if not (300.0 <= rpm <= 12000.0):
                continue
            motors.append({
                "motor_id": motor_id,
                "voltage_v": voltage_v,
                "current_a": current_a,
                "rpm": rpm,
            })

        active_counts.append(len(motors))
        if len(motors) != expected_motor_count:
            continue

        time_s = record_idx / sample_rate_hz
        timestamp_utc = start_utc + timedelta(seconds=time_s) if start_utc else None
        power_w = sum(motor["voltage_v"] * motor["current_a"] for motor in motors)
        rpm_median = _median(motor["rpm"] for motor in motors)
        utip_ms = tip_speed_from_rpm(prop_diameter_inch, rpm_median)
        voltage_median = _median(motor["voltage_v"] for motor in motors)
        current_sum = sum(motor["current_a"] for motor in motors)
        samples.append({
            "time_s": time_s,
            "timestamp_utc": timestamp_utc,
            "source_session": path.parent.name,
            "source_udat": path.name,
            "active_motor_count": len(motors),
            "voltage_v": voltage_median,
            "current_total_a": current_sum,
            "power_w": power_w,
            "rpm_median": rpm_median,
            "utip_ms": utip_ms,
            "motors": motors,
        })
        voltages.append(voltage_median)
        currents.extend(motor["current_a"] for motor in motors)
        powers.append(power_w)
        rpms.append(rpm_median)
        utips.append(utip_ms)

    return {
        "path": path,
        "samples": samples,
        "record_count": len(samples),
        "raw_record_count": raw_record_count,
        "sample_rate_hz": sample_rate_hz,
        "active_motor_count_median": int(round(_median(active_counts))) if active_counts else 0,
        "voltage_median_v": _median(voltages) if voltages else None,
        "motor_current_median_a": _median(currents) if currents else None,
        "power_median_w": _median(powers) if powers else None,
        "rpm_median": _median(rpms) if rpms else None,
        "utip_median_ms": _median(utips) if utips else None,
        "start_naive": start_naive,
        "end_naive": end_naive,
        "timestamp_mode": timestamp_mode,
        "current_scale": current_scale,
    }


def summarize_datalink_session(session_dir):
    session_dir = Path(session_dir)
    files = sorted(session_dir.glob("*.udat"))
    starts = []
    ends = []
    for path in files:
        start_naive, end_naive = _parse_datalink_filename_times(path)
        if not start_naive:
            continue
        if end_naive is None:
            raw_records = max(0, (path.stat().st_size - DATALINK_RECORD_HEADER_BYTES) // DATALINK_RECORD_BYTES)
            end_naive = start_naive + timedelta(seconds=raw_records / DATALINK_DEFAULT_SAMPLE_HZ)
        starts.append(start_naive)
        ends.append(end_naive)
    if not starts:
        return None
    return {
        "path": session_dir,
        "name": session_dir.name,
        "files": files,
        "file_count": len(files),
        "start_naive": min(starts),
        "end_naive": max(ends),
    }


def find_datalink_session_dirs(root=None):
    roots = []
    if root:
        roots.append(Path(root))
    else:
        base_dir = Path(__file__).resolve().parent
        for candidate in FIRFIR_DATALINK_ROOT_CANDIDATES:
            path = Path(candidate)
            if not path.is_absolute():
                path = base_dir / path
            roots.append(path)
    sessions = []
    for root_path in roots:
        if not root_path.exists():
            continue
        for child in sorted(root_path.iterdir()):
            if child.is_dir() and any(child.glob("*.udat")):
                summary = summarize_datalink_session(child)
                if summary:
                    sessions.append(summary)
    return sessions


def normalize_datalink_date_hint(value):
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 8 and digits.startswith("20"):
        return digits[2:]
    if len(digits) == 6:
        return digits
    return None


def filter_datalink_sessions_by_date_hint(sessions, date_hint):
    normalized = normalize_datalink_date_hint(date_hint)
    if not normalized:
        return sessions
    prefix = f"UART-{normalized}"
    return [session for session in sessions if session["name"].startswith(prefix)]


def _gps_week_ms_to_utc(gps_week, gps_ms):
    return (
        datetime(1980, 1, 6, tzinfo=timezone.utc)
        + timedelta(weeks=int(gps_week), milliseconds=float(gps_ms))
    )


def find_ardupilot_bin_log_paths(log_dir=None, name_filter=None):
    paths = []
    if log_dir:
        paths.extend(sorted(Path(log_dir).glob("*.BIN")))
    else:
        for pattern in FIRFIR_ARDUPILOT_BIN_GLOBS:
            paths.extend(sorted(Path().glob(pattern) if not re.match(r"^[A-Za-z]:", pattern)
                                else Path(pattern[0:3]).glob(pattern[3:])))
    if name_filter:
        paths = [path for path in paths if path.name == name_filter]
    return sorted(paths)


def read_ardupilot_bin_time_span(bin_path):
    try:
        from pymavlink import mavutil
    except Exception as exc:
        return {"path": Path(bin_path), "error": f"pymavlink_unavailable: {exc}"}

    bin_path = Path(bin_path)
    try:
        log = mavutil.mavlink_connection(str(bin_path), robust_parsing=True)
    except Exception as exc:
        return {"path": bin_path, "error": f"open_failed: {exc}"}

    first = None
    last = None
    gps_count = 0
    while True:
        msg = log.recv_match(type="GPS", blocking=False)
        if msg is None:
            break
        data = msg.to_dict()
        if not data.get("GWk") or not data.get("GMS"):
            continue
        current = {
            "timeus_s": data["TimeUS"] / 1e6,
            "utc": _gps_week_ms_to_utc(data["GWk"], data["GMS"]),
        }
        if first is None:
            first = current
        last = current
        gps_count += 1

    if first is None or last is None:
        return {"path": bin_path, "error": "no_gps_time", "gps_count": gps_count}
    return {
        "path": bin_path,
        "first_utc": first["utc"],
        "last_utc": last["utc"],
        "first_timeus_s": first["timeus_s"],
        "last_timeus_s": last["timeus_s"],
        "gps_count": gps_count,
    }


def find_datalink_bin_overlaps(sessions, bin_spans, min_overlap_s=30.0):
    overlaps = []
    for session in sessions:
        for timestamp_mode in ("filename_utc", "filename_trt"):
            session_start, session_end = _datalink_session_utc_bounds(session, timestamp_mode)
            if session_start is None or session_end is None:
                continue
            for bin_span in bin_spans:
                if bin_span.get("error"):
                    continue
                overlap_start = max(session_start, bin_span["first_utc"])
                overlap_end = min(session_end, bin_span["last_utc"])
                overlap_s = (overlap_end - overlap_start).total_seconds()
                if overlap_s >= min_overlap_s:
                    overlaps.append({
                        "session": session,
                        "bin_span": bin_span,
                        "timestamp_mode": timestamp_mode,
                        "start_utc": overlap_start,
                        "end_utc": overlap_end,
                        "overlap_s": overlap_s,
                    })
    overlaps.sort(key=lambda item: item["overlap_s"], reverse=True)
    return overlaps


def read_ardupilot_flight_samples(bin_path, start_utc=None, end_utc=None):
    try:
        from pymavlink import mavutil
    except Exception:
        return []

    span = read_ardupilot_bin_time_span(bin_path)
    if span.get("error"):
        return []

    anchor_utc = span["first_utc"]
    anchor_timeus_s = span["first_timeus_s"]
    samples = []
    log = mavutil.mavlink_connection(str(bin_path), robust_parsing=True)
    while True:
        msg = log.recv_match(type="XKF1", blocking=False)
        if msg is None:
            break
        data = msg.to_dict()
        if data.get("C", 0) != 0:
            continue
        timestamp_utc = anchor_utc + timedelta(seconds=data["TimeUS"] / 1e6 - anchor_timeus_s)
        if start_utc and timestamp_utc < start_utc:
            continue
        if end_utc and timestamp_utc > end_utc:
            continue
        vx_ms = data.get("VN", 0.0)
        vy_ms = data.get("VE", 0.0)
        samples.append({
            "timestamp_utc": timestamp_utc,
            "source_bin": bin_path.name,
            "speed_ms": math.hypot(vx_ms, vy_ms),
            "vx_ms": vx_ms,
            "vy_ms": vy_ms,
            "vertical_speed_ms": -data.get("VD", 0.0),
            "altitude_m": -data.get("PD", 0.0),
            "pitch_deg": data.get("Pitch", 0.0),
            "roll_deg": data.get("Roll", 0.0),
        })
    samples.sort(key=lambda item: item["timestamp_utc"])
    return samples


def _parse_datalink_session_samples(session, timestamp_mode, prop_diameter_inch):
    samples = []
    for path in session.get("files", []):
        parsed = parse_datalink_udat_file(
            path,
            prop_diameter_inch=prop_diameter_inch,
            timestamp_mode=timestamp_mode,
        )
        samples.extend(sample for sample in parsed["samples"] if sample.get("timestamp_utc"))
    samples.sort(key=lambda item: item["timestamp_utc"])
    return samples


def join_datalink_and_flight_samples(datalink_samples, flight_samples, hover_power_w,
                                     max_dt_s=0.35):
    if not datalink_samples or not flight_samples:
        return []
    joined = []
    idx = 0
    for dl_sample in datalink_samples:
        dl_time = dl_sample["timestamp_utc"]
        while (idx + 1 < len(flight_samples)
               and flight_samples[idx + 1]["timestamp_utc"] <= dl_time):
            idx += 1
        candidates = [flight_samples[idx]]
        if idx + 1 < len(flight_samples):
            candidates.append(flight_samples[idx + 1])
        nearest = min(
            candidates,
            key=lambda item: abs((item["timestamp_utc"] - dl_time).total_seconds()),
        )
        dt_s = abs((nearest["timestamp_utc"] - dl_time).total_seconds())
        if dt_s > max_dt_s:
            continue
        power_ratio = dl_sample["power_w"] / hover_power_w if hover_power_w > 0 else float("nan")
        if not math.isfinite(power_ratio) or power_ratio <= 0:
            continue
        joined.append({
            "timestamp_utc": dl_time,
            "dt_s": dt_s,
            "speed_ms": nearest["speed_ms"],
            "vx_ms": nearest.get("vx_ms", 0.0),
            "vy_ms": nearest.get("vy_ms", 0.0),
            "vertical_speed_ms": nearest.get("vertical_speed_ms", 0.0),
            "altitude_m": nearest.get("altitude_m", 0.0),
            "pitch_deg": nearest["pitch_deg"],
            "roll_deg": nearest["roll_deg"],
            "power_w": dl_sample["power_w"],
            "power_ratio": power_ratio,
            "rpm_median": dl_sample["rpm_median"],
            "utip_ms": dl_sample["utip_ms"],
            "voltage_v": dl_sample["voltage_v"],
            "current_total_a": dl_sample["current_total_a"],
            "source_session": dl_sample.get("source_session"),
            "source_udat": dl_sample.get("source_udat"),
            "source_bin": nearest.get("source_bin"),
        })
    return joined


def annotate_joined_sample_stability(joined_samples,
                                     max_abs_accel_ms2=8.0,
                                     max_abs_vertical_speed_ms=1.5,
                                     max_abs_roll_deg=28.0,
                                     max_abs_pitch_deg=28.0):
    if not joined_samples:
        return []
    samples = [dict(sample) for sample in sorted(joined_samples, key=lambda item: item["timestamp_utc"])]
    for idx, sample in enumerate(samples):
        accel_ms2 = 0.0
        if 0 < idx < len(samples) - 1:
            prev_sample = samples[idx - 1]
            next_sample = samples[idx + 1]
            dt_s = (next_sample["timestamp_utc"] - prev_sample["timestamp_utc"]).total_seconds()
            if 0.0 < dt_s <= 1.0:
                accel_ms2 = abs(next_sample["speed_ms"] - prev_sample["speed_ms"]) / dt_s
        elif idx > 0:
            prev_sample = samples[idx - 1]
            dt_s = (sample["timestamp_utc"] - prev_sample["timestamp_utc"]).total_seconds()
            if 0.0 < dt_s <= 1.0:
                accel_ms2 = abs(sample["speed_ms"] - prev_sample["speed_ms"]) / dt_s
        sample["accel_ms2"] = accel_ms2
        sample["stable"] = (
            accel_ms2 <= max_abs_accel_ms2
            and abs(sample.get("vertical_speed_ms", 0.0)) <= max_abs_vertical_speed_ms
            and abs(sample.get("roll_deg", 0.0)) <= max_abs_roll_deg
            and abs(sample.get("pitch_deg", 0.0)) <= max_abs_pitch_deg
        )
    return samples


def estimate_datalink_hover_power(joined_samples, max_speed_ms=1.5,
                                  max_abs_pitch_deg=8.0, max_abs_roll_deg=8.0,
                                  min_power_w=100.0, min_samples=200):
    powers = []
    for sample in joined_samples:
        speed_ms = sample.get("speed_ms", float("inf"))
        power_w = sample.get("power_w", 0.0)
        pitch_deg = sample.get("pitch_deg", 0.0)
        roll_deg = sample.get("roll_deg", 0.0)
        if speed_ms > max_speed_ms:
            continue
        if abs(pitch_deg) > max_abs_pitch_deg or abs(roll_deg) > max_abs_roll_deg:
            continue
        if not math.isfinite(power_w) or power_w < min_power_w:
            continue
        powers.append(power_w)
    if len(powers) < min_samples:
        return None
    return _median(powers)


def build_datalink_speed_observations(joined_samples,
                                      min_speed_ms=2.0,
                                      max_speed_ms=25.0,
                                      bin_width_ms=DATALINK_SPEED_BIN_WIDTH_MS,
                                      min_samples=DATALINK_MIN_BIN_SAMPLES,
                                      power_reference_w=None,
                                      stable_only=False,
                                      min_stable_fraction=0.5,
                                      extrapolation_start_ms=None):
    bins = {}
    for sample in joined_samples:
        speed_ms = sample["speed_ms"]
        if not (min_speed_ms <= speed_ms <= max_speed_ms):
            continue
        bin_center = round((math.floor(speed_ms / bin_width_ms) + 0.5) * bin_width_ms, 2)
        bins.setdefault(bin_center, []).append(sample)

    observations = []
    for bin_center, values in sorted(bins.items()):
        stable_values = [sample for sample in values if sample.get("stable", True)]
        stable_fraction = len(stable_values) / len(values) if values else 0.0
        values_for_stats = stable_values if stable_only else values
        if stable_only and stable_fraction < min_stable_fraction:
            continue
        if len(values_for_stats) < min_samples:
            continue
        if power_reference_w and power_reference_w > 0:
            ratios = [sample["power_w"] / power_reference_w for sample in values_for_stats]
        else:
            ratios = [sample["power_ratio"] for sample in values_for_stats]
        powers = [sample["power_w"] for sample in values_for_stats]
        rpms = [sample["rpm_median"] for sample in values_for_stats]
        utips = [sample["utip_ms"] for sample in values_for_stats]
        speeds = [sample["speed_ms"] for sample in values_for_stats]
        dt_values = [
            sample.get("dt_s") for sample in values_for_stats
            if sample.get("dt_s") is not None and math.isfinite(sample.get("dt_s"))
        ]
        speed_ms = _median(speeds)
        extrapolation_region = "measured"
        if extrapolation_start_ms is not None and speed_ms > extrapolation_start_ms:
            extrapolation_region = "extrapolation"
        observations.append({
            "label": f"DataLink v~{bin_center:.1f}",
            "speed_ms": speed_ms,
            "power_ratio": _median(ratios),
            "power_w": _median(powers),
            "rpm_median": _median(rpms),
            "utip_ms": _median(utips),
            "sample_count": len(values_for_stats),
            "raw_sample_count": len(values),
            "stable_sample_count": len(stable_values),
            "stable_fraction": stable_fraction,
            "weight": min(30.0, max(4.0, len(values_for_stats) / 200.0)),
            "source": "datalink",
            "source_bins": _sorted_unique_strings(
                sample.get("source_bin") for sample in values_for_stats
            ),
            "source_sessions": _sorted_unique_strings(
                sample.get("source_session") for sample in values_for_stats
            ),
            "source_udats": _sorted_unique_strings(
                sample.get("source_udat") for sample in values_for_stats
            ),
            "dt_s_max": max(dt_values) if dt_values else None,
            "dt_s_median": _median(dt_values) if dt_values else None,
            "power_reference_w": power_reference_w,
            "extrapolation_region": extrapolation_region,
        })
    return observations


def build_empirical_datalink_power_curve(observations):
    measured_points = [
        dict(obs) for obs in observations
        if obs.get("extrapolation_region", "measured") == "measured"
        and math.isfinite(obs.get("speed_ms", float("nan")))
        and math.isfinite(obs.get("power_ratio", float("nan")))
    ]
    measured_points.sort(key=lambda obs: obs["speed_ms"])
    source_bins = []
    source_sessions = []
    source_udats = []
    for obs in measured_points:
        source_bins.extend(obs.get("source_bins", []))
        source_sessions.extend(obs.get("source_sessions", []))
        source_udats.extend(obs.get("source_udats", []))

    warnings = []
    if len(measured_points) < 2:
        warnings.append("not_enough_measured_bins_for_interpolation")

    return {
        "kind": "datalink_empirical_pv",
        "interpolation": "linear",
        "measured_points": measured_points,
        "min_speed_ms": measured_points[0]["speed_ms"] if measured_points else None,
        "max_speed_ms": measured_points[-1]["speed_ms"] if measured_points else None,
        "sample_count_total": sum(obs.get("sample_count", 0) for obs in measured_points),
        "raw_sample_count_total": sum(obs.get("raw_sample_count", 0) for obs in measured_points),
        "stable_fraction_min": min(
            (obs.get("stable_fraction", 0.0) for obs in measured_points),
            default=None,
        ),
        "source_bins": _sorted_unique_strings(source_bins),
        "source_sessions": _sorted_unique_strings(source_sessions),
        "source_udats": _sorted_unique_strings(source_udats),
        "warnings": warnings,
    }


def evaluate_empirical_datalink_power_ratio(curve, speed_ms):
    points = curve.get("measured_points", [])
    if not points:
        return {
            "available": False,
            "reason": "no_measured_points",
            "speed_ms": speed_ms,
        }

    min_speed = curve["min_speed_ms"]
    max_speed = curve["max_speed_ms"]
    if speed_ms < min_speed or speed_ms > max_speed:
        return {
            "available": False,
            "reason": "out_of_measured_range",
            "speed_ms": speed_ms,
            "min_speed_ms": min_speed,
            "max_speed_ms": max_speed,
        }

    for point in points:
        if abs(point["speed_ms"] - speed_ms) <= 1e-9:
            return {
                "available": True,
                "basis": "measured_bin",
                "speed_ms": speed_ms,
                "power_ratio": point["power_ratio"],
                "lower": point,
                "upper": point,
            }

    lower = points[0]
    upper = points[-1]
    for left, right in zip(points, points[1:]):
        if left["speed_ms"] <= speed_ms <= right["speed_ms"]:
            lower = left
            upper = right
            break
    span = upper["speed_ms"] - lower["speed_ms"]
    if span <= 0:
        power_ratio = lower["power_ratio"]
    else:
        t = (speed_ms - lower["speed_ms"]) / span
        power_ratio = lower["power_ratio"] + t * (upper["power_ratio"] - lower["power_ratio"])
    return {
        "available": True,
        "basis": "linear_interpolation",
        "speed_ms": speed_ms,
        "power_ratio": power_ratio,
        "lower": lower,
        "upper": upper,
    }


def audit_scientific_fit_parameters(model_name, params, profile=None):
    reasons = []
    warnings = []
    status = "accepted"
    profile = profile or {}

    utip_source = params.get("utip_source") or profile.get("utip_source")
    utip_ms = params.get("utip_ms", profile.get("utip_ms"))
    if utip_source == "fitted":
        reasons.append("utip_must_not_be_fitted")
    if utip_source == "datalink_rpm" and utip_ms is not None:
        lo, hi = DATALINK_DATASHEET_UTIP_RANGE_MS
        if not (lo <= utip_ms <= hi):
            reasons.append("datalink_utip_outside_guardrail")

    if "lambda_n_per_ms" in params:
        lambda_value = params.get("lambda_n_per_ms")
        lambda_source = params.get("lambda_source")
        if lambda_value is None:
            warnings.append("lambda_missing")
        elif lambda_value < 0:
            reasons.append("negative_lambda")
        elif lambda_source == "attitude_log":
            lo, hi = DATALINK_FIRFIR_LAMBDA_ACCEPTANCE_N_PER_MS
            if not (lo <= lambda_value <= hi):
                reasons.append("lambda_outside_firfir_guardrail")
        elif lambda_source in {None, "none"}:
            warnings.append("lambda_not_measured")

    body_cd_fit = params.get("body_cd_fit")
    if body_cd_fit is not None and body_cd_fit > DATALINK_BODY_CD_MAX:
        reasons.append("body_cd_unphysical")

    if reasons:
        status = "rejected"
    elif warnings:
        status = "accepted_with_warnings"

    return {
        "model": model_name,
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "params": params,
    }


def build_datalink_pph_consistency_anchor(profile, voltage_anchor=None):
    band_min, band_max = FIRFIR_DATALINK_QC_EXPECTED_6MS_PPH_BAND
    target_speed = (
        voltage_anchor["speed_ms"]
        if voltage_anchor and voltage_anchor.get("speed_ms")
        else FIRFIR_STADIUM_SPEED_MS
    )
    if voltage_anchor:
        ratio = voltage_anchor.get("power_ratio")
        if ratio is not None and band_min <= ratio <= band_max:
            anchor = dict(voltage_anchor)
            anchor["source"] = "stadium_voltage_anchor"
            return anchor

    target_ratio = profile.get(
        "p_endurance_ratio",
        FIRFIR_DATALINK_QC_DEFAULT_6MS_PPH,
    )
    anchor = {
        "speed_ms": target_speed,
        "power_ratio": target_ratio,
        "source": "bauersfeld_log_6ms_sanity",
        "expected_band": FIRFIR_DATALINK_QC_EXPECTED_6MS_PPH_BAND,
    }
    if voltage_anchor:
        anchor["raw_voltage_anchor"] = voltage_anchor
    return anchor


def evaluate_datalink_pph_consistency(observations, voltage_anchor=None,
                                      tolerance_ratio=0.15):
    warnings = []
    if not observations:
        return {
            "fit_allowed": False,
            "warnings": ["no_datalink_observations"],
            "nearest_6ms": None,
        }
    target_speed = voltage_anchor["speed_ms"] if voltage_anchor else 6.0
    target_ratio = voltage_anchor["power_ratio"] if voltage_anchor else 0.905
    near_6 = [
        obs for obs in observations
        if abs(obs["speed_ms"] - target_speed) <= 0.75
    ]
    nearest = None
    fit_allowed = True
    if near_6:
        nearest = min(near_6, key=lambda obs: abs(obs["speed_ms"] - target_speed))
        error = nearest["power_ratio"] - target_ratio
        if abs(error) > tolerance_ratio:
            fit_allowed = False
            warnings.append(
                f"datalink_6ms_inconsistent: target={target_ratio:.3f}, "
                f"datalink={nearest['power_ratio']:.3f}, err={error:+.3f}"
            )
    else:
        warnings.append("no_6ms_datalink_consistency_point")

    return {
        "fit_allowed": fit_allowed,
        "warnings": warnings,
        "nearest_6ms": nearest,
        "target_speed_ms": target_speed,
        "target_power_ratio": target_ratio,
        "tolerance_ratio": tolerance_ratio,
    }


def build_datalink_power_observations(profile, hover_power_w, voltage_anchor=None,
                                      datalink_root=None, bin_paths=None,
                                      session_date_hint=None):
    session_date_hint = (
        session_date_hint
        or profile.get("datalink_session_date_hint")
        or os.environ.get(DATALINK_DATE_HINT_ENV)
    )
    normalized_date_hint = normalize_datalink_date_hint(session_date_hint)
    sessions = find_datalink_session_dirs(datalink_root)
    if normalized_date_hint:
        sessions = filter_datalink_sessions_by_date_hint(sessions, normalized_date_hint)
    if not sessions:
        warning = "no_datalink_sessions"
        if normalized_date_hint:
            warning = f"no_datalink_sessions_for_date:{normalized_date_hint}"
        return {
            "fit_allowed": False,
            "observations": [],
            "raw_observations": [],
            "qc": {"fit_allowed": False, "warnings": [warning]},
            "overlaps": [],
            "utip_ms": None,
            "session_date_hint": normalized_date_hint,
            "datalink_hover_power_w": None,
        }

    if bin_paths is None:
        bin_paths = find_ardupilot_bin_log_paths()
    bin_spans = [read_ardupilot_bin_time_span(path) for path in bin_paths]
    overlaps = find_datalink_bin_overlaps(sessions, bin_spans)
    if not overlaps:
        warning = "no_datalink_bin_overlap"
        if normalized_date_hint:
            warning = f"no_datalink_bin_overlap_for_date:{normalized_date_hint}"
        return {
            "fit_allowed": False,
            "observations": [],
            "raw_observations": [],
            "qc": {"fit_allowed": False, "warnings": [warning]},
            "overlaps": [],
            "utip_ms": None,
            "session_date_hint": normalized_date_hint,
            "datalink_hover_power_w": None,
        }

    joined_all = []
    overlap_reports = []
    prop_diameter_inch = profile["prop_diameter_inch"]
    for overlap in overlaps[:3]:
        datalink_samples = _parse_datalink_session_samples(
            overlap["session"],
            overlap["timestamp_mode"],
            prop_diameter_inch,
        )
        datalink_samples = [
            sample for sample in datalink_samples
            if overlap["start_utc"] <= sample["timestamp_utc"] <= overlap["end_utc"]
        ]
        flight_samples = read_ardupilot_flight_samples(
            overlap["bin_span"]["path"],
            overlap["start_utc"],
            overlap["end_utc"],
        )
        joined = join_datalink_and_flight_samples(datalink_samples, flight_samples, hover_power_w)
        joined_all.extend(joined)
        overlap_reports.append({
            "session": overlap["session"]["name"],
            "bin": Path(overlap["bin_span"]["path"]).name,
            "timestamp_mode": overlap["timestamp_mode"],
            "overlap_s": overlap["overlap_s"],
            "datalink_samples": len(datalink_samples),
            "flight_samples": len(flight_samples),
            "joined_samples": len(joined),
        })

    datalink_hover_power_w = estimate_datalink_hover_power(joined_all)
    power_reference_w = datalink_hover_power_w or hover_power_w
    raw_observations = build_datalink_speed_observations(
        joined_all,
        power_reference_w=power_reference_w,
    )
    qc_anchor = build_datalink_pph_consistency_anchor(profile, voltage_anchor)
    qc = evaluate_datalink_pph_consistency(raw_observations, qc_anchor)
    qc["anchor_source"] = qc_anchor.get("source")
    qc["power_reference_source"] = (
        "datalink_measured_hover" if datalink_hover_power_w else "static_hover_reference"
    )
    qc["power_reference_w"] = power_reference_w
    if normalized_date_hint:
        qc["session_date_hint"] = normalized_date_hint
    if not datalink_hover_power_w:
        qc["warnings"].insert(0, "no_datalink_hover_reference_using_static_hover")
    if qc_anchor.get("raw_voltage_anchor"):
        raw_anchor = qc_anchor["raw_voltage_anchor"]
        band_min, band_max = qc_anchor["expected_band"]
        qc["warnings"].insert(
            0,
            f"stadium_anchor_outside_expected_band: raw={raw_anchor['power_ratio']:.3f}, "
            f"expected={band_min:.2f}-{band_max:.2f}; "
            f"using_bauersfeld_log_target={qc_anchor['power_ratio']:.3f}"
        )
    accepted = raw_observations if qc["fit_allowed"] else []
    utip_values = [obs["utip_ms"] for obs in accepted if obs.get("utip_ms")]
    return {
        "fit_allowed": qc["fit_allowed"],
        "observations": accepted,
        "raw_observations": raw_observations,
        "qc": qc,
        "overlaps": overlap_reports,
        "utip_ms": _median(utip_values) if utip_values else None,
        "joined_sample_count": len(joined_all),
        "session_date_hint": normalized_date_hint,
        "datalink_hover_power_w": datalink_hover_power_w,
        "power_reference_w": power_reference_w,
    }


def find_measured_curve_log_root(log_root=None):
    if log_root:
        path = Path(log_root)
        if path.exists():
            return path
        raise FileNotFoundError(f"DataLink measured log root not found: {path}")

    base_dir = Path(__file__).resolve().parent
    for child in sorted(base_dir.iterdir()):
        if child.is_dir() and child.name.startswith("3 Temmuz"):
            return child
    raise FileNotFoundError("3 Temmuz log klasoru bulunamadi.")


def read_battery_monitor_rows(bin_path, start_utc=None, end_utc=None):
    try:
        from pymavlink import mavutil
    except Exception:
        return []

    span = read_ardupilot_bin_time_span(bin_path)
    if span.get("error"):
        return []

    rows = []
    anchor_utc = span["first_utc"]
    anchor_timeus_s = span["first_timeus_s"]
    log = mavutil.mavlink_connection(str(bin_path), robust_parsing=True)
    while True:
        msg = log.recv_match(type="BAT", blocking=False)
        if msg is None:
            break
        data = msg.to_dict()
        if data.get("Inst", 0) != 0 or "TimeUS" not in data:
            continue
        timestamp_utc = anchor_utc + timedelta(seconds=data["TimeUS"] / 1e6 - anchor_timeus_s)
        if start_utc and timestamp_utc < start_utc:
            continue
        if end_utc and timestamp_utc > end_utc:
            continue
        rows.append({
            "timestamp_utc": timestamp_utc,
            "bin": Path(bin_path).name,
            "volt_v": data.get("Volt"),
            "voltr_v": data.get("VoltR"),
            "curr_a": data.get("Curr"),
            "currtot_ah": data.get("CurrTot"),
            "enrgtot_raw": data.get("EnrgTot"),
            "rempct": data.get("RemPct"),
            "res_mohm": data.get("Res"),
        })
    rows.sort(key=lambda row: row["timestamp_utc"])
    return rows


def integrate_joined_energy_wh(joined_samples, max_dt_s=1.0):
    samples = sorted(joined_samples, key=lambda sample: sample["timestamp_utc"])
    chunks = []
    current_chunk = []
    energy_wh = 0.0
    for sample in samples:
        if current_chunk:
            dt_s = (sample["timestamp_utc"] - current_chunk[-1]["timestamp_utc"]).total_seconds()
            if 0.0 < dt_s <= max_dt_s:
                energy_wh += 0.5 * (current_chunk[-1]["power_w"] + sample["power_w"]) * dt_s / 3600.0
            elif dt_s > 60.0:
                chunks.append(current_chunk)
                current_chunk = []
        current_chunk.append(sample)
    if current_chunk:
        chunks.append(current_chunk)

    chunk_summaries = []
    for chunk in chunks:
        if not chunk:
            continue
        duration_s = (chunk[-1]["timestamp_utc"] - chunk[0]["timestamp_utc"]).total_seconds()
        chunk_energy_wh = 0.0
        for prev_sample, sample in zip(chunk, chunk[1:]):
            dt_s = (sample["timestamp_utc"] - prev_sample["timestamp_utc"]).total_seconds()
            if 0.0 < dt_s <= max_dt_s:
                chunk_energy_wh += 0.5 * (prev_sample["power_w"] + sample["power_w"]) * dt_s / 3600.0
        speeds = [sample["speed_ms"] for sample in chunk]
        chunk_summaries.append({
            "start_utc": chunk[0]["timestamp_utc"],
            "end_utc": chunk[-1]["timestamp_utc"],
            "duration_s": duration_s,
            "energy_wh": chunk_energy_wh,
            "avg_power_w": chunk_energy_wh * 3600.0 / duration_s if duration_s > 0 else 0.0,
            "median_speed_ms": _median(speeds),
            "sample_count": len(chunk),
        })
    return energy_wh, chunk_summaries


def build_battery_qc_report(bin_paths, joined_samples):
    battery_rows = []
    energy_delta_raw = 0.0
    currtot_delta_ah = 0.0
    for bin_path in bin_paths:
        rows = read_battery_monitor_rows(bin_path)
        battery_rows.extend(rows)
        if len(rows) >= 2:
            if rows[0].get("enrgtot_raw") is not None and rows[-1].get("enrgtot_raw") is not None:
                energy_delta_raw += rows[-1]["enrgtot_raw"] - rows[0]["enrgtot_raw"]
            if rows[0].get("currtot_ah") is not None and rows[-1].get("currtot_ah") is not None:
                currtot_delta_ah += rows[-1]["currtot_ah"] - rows[0]["currtot_ah"]

    battery_rows.sort(key=lambda row: row["timestamp_utc"])
    datalink_energy_wh, chunks = integrate_joined_energy_wh(joined_samples)
    currents = [
        row["curr_a"] for row in battery_rows
        if row.get("curr_a") is not None and math.isfinite(row["curr_a"])
    ]
    voltr_values = [
        row["voltr_v"] for row in battery_rows
        if row.get("voltr_v") is not None and math.isfinite(row["voltr_v"])
    ]
    warnings = []
    direct_current_fit_enabled = True
    current_median = _median(currents) if currents else None
    energy_scale_ratio = None
    if energy_delta_raw > 0:
        energy_scale_ratio = datalink_energy_wh / energy_delta_raw
    if current_median is None or current_median < 1.0:
        direct_current_fit_enabled = False
        warnings.append("battery_current_scale_suspect: BAT.Curr is near zero")
    if energy_scale_ratio is None or energy_scale_ratio > 5.0:
        direct_current_fit_enabled = False
        warnings.append("battery_energy_scale_suspect: BAT.EnrgTot disagrees with DataLink energy")

    return {
        "bat_rows": len(battery_rows),
        "voltr_start_v": voltr_values[0] if voltr_values else None,
        "voltr_end_v": voltr_values[-1] if voltr_values else None,
        "voltr_min_v": min(voltr_values) if voltr_values else None,
        "voltr_max_v": max(voltr_values) if voltr_values else None,
        "current_median_a": current_median,
        "currtot_delta_ah": currtot_delta_ah,
        "battery_energy_delta_raw": energy_delta_raw,
        "datalink_energy_wh": datalink_energy_wh,
        "energy_scale_ratio": energy_scale_ratio,
        "direct_current_fit_enabled": direct_current_fit_enabled,
        "warnings": warnings,
        "energy_chunks": chunks,
        "rows": battery_rows,
    }


def build_measured_curve_model_fit(profile, sonuc, hover_power_reference_w,
                                   observations, faessler_fit=None):
    vi_h = sonuc["vi_h"]
    measured_profile = dict(profile)
    utip_values = [obs["utip_ms"] for obs in observations if obs.get("utip_ms")]
    if utip_values:
        measured_profile["utip_ms"] = _median(utip_values)
        measured_profile["utip_source"] = "datalink_rpm"
        measured_profile["hover_rpm_estimate"] = (
            measured_profile["utip_ms"] * 60.0
            / (math.pi * measured_profile["prop_diameter_inch"] * 0.0254)
        )
    theoretical_params = build_theoretical_zeng_params(measured_profile, hover_power_reference_w)
    if faessler_fit is None:
        faessler_fit = estimate_faessler_drag_from_attitude_log(measured_profile)
    zeng_params = fit_observation_weighted_zeng(
        vi_h,
        measured_profile["utip_ms"],
        hover_power_reference_w,
        theoretical_params,
        None,
        observations,
    )
    faessler_params = fit_faessler_drag_constrained_zeng(
        vi_h,
        measured_profile["utip_ms"],
        hover_power_reference_w,
        theoretical_params,
        faessler_fit,
        None,
        observations=observations,
    )
    kirschstein_params = fit_kirschstein_all_data(
        measured_profile,
        hover_power_reference_w,
        vi_h,
        observations,
        faessler_fit=faessler_fit,
    )
    model_functions = {
        "zeng_measured_fit": (
            lambda v, p=zeng_params: power_ratio_bauersfeld_anchored_zeng(v, p)
        ),
        "faessler_measured_fit": (
            lambda v, p=faessler_params: power_ratio_faessler_drag_constrained_zeng(v, p)
        ),
        "kirschstein_measured_fit": (
            lambda v, p=kirschstein_params: power_ratio_kirschstein_all_data(v, p)
        ),
    }
    residuals = {}
    for name, ratio_fn in model_functions.items():
        rows = []
        for obs in observations:
            predicted = ratio_fn(obs["speed_ms"])
            rows.append({
                "label": obs["label"],
                "speed_ms": obs["speed_ms"],
                "target": obs["power_ratio"],
                "fit": predicted,
                "error": predicted - obs["power_ratio"],
                "sample_count": obs["sample_count"],
            })
        residuals[name] = rows
    fit_audit = {
        "fit_family": "diagnostic_surrogate_fits",
        "scope": (
            "These are low-dimensional diagnostic fits against measured DataLink bins; "
            "they are not independent physical validation curves."
        ),
        "models": {
            "zeng_measured_fit": audit_scientific_fit_parameters(
                "zeng_measured_fit",
                zeng_params,
                measured_profile,
            ),
            "faessler_measured_fit": audit_scientific_fit_parameters(
                "faessler_measured_fit",
                faessler_params,
                measured_profile,
            ),
            "kirschstein_measured_fit": audit_scientific_fit_parameters(
                "kirschstein_measured_fit",
                kirschstein_params,
                measured_profile,
            ),
        },
    }
    return {
        "profile": measured_profile,
        "faessler_fit": faessler_fit,
        "model_functions": model_functions,
        "model_fit_residuals": residuals,
        "fit_audit": fit_audit,
        "zeng_params": zeng_params,
        "faessler_params": faessler_params,
        "kirschstein_params": kirschstein_params,
    }


def plot_measured_power_curve(observations, model_functions=None,
                              output_path=DATALINK_DIAGNOSTIC_SURROGATE_OUTPUT_PATH,
                              extrapolation_start_ms=DATALINK_MEASURED_EXTRAPOLATION_START_MS):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    measured = [obs for obs in observations if obs["extrapolation_region"] == "measured"]
    extrapolated = [obs for obs in observations if obs["extrapolation_region"] == "extrapolation"]
    if measured:
        ax.scatter(
            [obs["speed_ms"] for obs in measured],
            [obs["power_ratio"] for obs in measured],
            marker="o",
            color="blue",
            label="DataLink measured bins",
        )
    if extrapolated:
        ax.scatter(
            [obs["speed_ms"] for obs in extrapolated],
            [obs["power_ratio"] for obs in extrapolated],
            marker="^",
            color="orange",
            label="DataLink sparse/high-speed bins",
        )
    if model_functions:
        speeds = [0.1 + i * (24.9 / 249.0) for i in range(250)]
        for name, ratio_fn in model_functions.items():
            solid_speeds = [speed for speed in speeds if speed <= extrapolation_start_ms]
            dashed_speeds = [speed for speed in speeds if speed >= extrapolation_start_ms]
            ax.plot(solid_speeds, [ratio_fn(speed) for speed in solid_speeds], label=name)
            ax.plot(dashed_speeds, [ratio_fn(speed) for speed in dashed_speeds], linestyle="--")
    ax.axvline(extrapolation_start_ms, linestyle="--", color="gray", alpha=0.7)
    ax.set_xlabel("Hiz [m/s]")
    ax.set_ylabel("P(V) / P_hover_measured")
    ax.set_title("Diagnostic surrogate fits; measured bins are the data source")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


def plot_empirical_datalink_power_curve(empirical_curve,
                                        output_path=DATALINK_EMPIRICAL_OUTPUT_PATH):
    import matplotlib.pyplot as plt

    points = empirical_curve.get("measured_points", [])
    fig, ax = plt.subplots(figsize=(12, 7))
    if points:
        speeds = [obs["speed_ms"] for obs in points]
        ratios = [obs["power_ratio"] for obs in points]
        ax.plot(speeds, ratios, color="black", linewidth=1.5, label="linear interpolation")
        ax.scatter(speeds, ratios, color="blue", label="DataLink measured bins")
        for idx, obs in enumerate(points):
            short_bins = [
                Path(name).stem.lstrip("0") or Path(name).stem
                for name in obs.get("source_bins", [])[:2]
            ]
            bins = ",".join(short_bins) or "source?"
            if len(obs.get("source_bins", [])) > 2:
                bins += ",..."
            label = (
                f"n={obs.get('sample_count', 0)}, sf={obs.get('stable_fraction', 0.0):.2f}\n"
                f"BIN {bins}"
            )
            y_offset = 10 if idx % 2 == 0 else -24
            ax.annotate(
                label,
                (obs["speed_ms"], obs["power_ratio"]),
                textcoords="offset points",
                xytext=(5, y_offset),
                fontsize=7,
                va="bottom" if y_offset > 0 else "top",
            )
    ax.set_xlabel("Hiz [m/s]")
    ax.set_ylabel("P(V) / P_hover_measured")
    ax.set_title("DataLink empirical P(v): measured range only")
    ax.margins(y=0.18)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


def plot_battery_voltage_timeline(battery_rows, sync_report,
                                  output_path="measured_datalink_battery_voltage.png"):
    import matplotlib.pyplot as plt

    rows = [row for row in battery_rows if row.get("voltr_v") is not None]
    fig, ax = plt.subplots(figsize=(11, 5))
    if rows:
        start = rows[0]["timestamp_utc"]
        times_min = [(row["timestamp_utc"] - start).total_seconds() / 60.0 for row in rows]
        ax.plot(times_min, [row["voltr_v"] for row in rows], color="green", label="BAT VoltR")
        for report in sync_report:
            if not report.get("accepted_for_fit"):
                continue
            begin = (report["start_utc"] - start).total_seconds() / 60.0
            end = (report["end_utc"] - start).total_seconds() / 60.0
            ax.axvspan(begin, end, color="blue", alpha=0.08)
    ax.set_xlabel("Log zamani [dk]")
    ax.set_ylabel("BAT VoltR [V]")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


def run_datalink_measured_curve_analysis(profile, sonuc, hover_power_w,
                                         battery_wh, correction_factor,
                                         log_root=None,
                                         date_hint=DATALINK_MEASURED_CURVE_DATE_HINT,
                                         make_graph=True,
                                         timestamp_mode="filename_trt"):
    log_root = find_measured_curve_log_root(log_root)
    datalink_root = log_root / "Datalink"
    bin_paths = sorted(log_root.glob("*.BIN"))
    normalized_date_hint = normalize_datalink_date_hint(date_hint)
    sessions = find_datalink_session_dirs(datalink_root)
    sessions = filter_datalink_sessions_by_date_hint(sessions, normalized_date_hint)
    bin_spans = [read_ardupilot_bin_time_span(path) for path in bin_paths]
    overlaps = find_datalink_bin_overlaps(sessions, bin_spans, min_overlap_s=30.0)

    sync_report = []
    joined_for_fit = []
    prop_diameter_inch = profile["prop_diameter_inch"]
    parsed_session_cache = {}
    for overlap in overlaps:
        cache_key = (overlap["session"]["name"], overlap["timestamp_mode"])
        if cache_key not in parsed_session_cache:
            parsed_session_cache[cache_key] = _parse_datalink_session_samples(
                overlap["session"],
                overlap["timestamp_mode"],
                prop_diameter_inch,
            )
        datalink_samples = [
            sample for sample in parsed_session_cache[cache_key]
            if overlap["start_utc"] <= sample["timestamp_utc"] <= overlap["end_utc"]
        ]
        flight_samples = read_ardupilot_flight_samples(
            overlap["bin_span"]["path"],
            overlap["start_utc"],
            overlap["end_utc"],
        )
        joined = join_datalink_and_flight_samples(datalink_samples, flight_samples, hover_power_w)
        accepted = bool(joined) and overlap["timestamp_mode"] == timestamp_mode
        reject_reason = None
        if not joined:
            reject_reason = "no_joined_samples"
        elif overlap["timestamp_mode"] != timestamp_mode:
            reject_reason = f"non_preferred_timestamp_mode:{overlap['timestamp_mode']}"
        if accepted:
            joined_for_fit.extend(joined)
        sync_report.append({
            "session": overlap["session"]["name"],
            "bin": Path(overlap["bin_span"]["path"]).name,
            "timestamp_mode": overlap["timestamp_mode"],
            "start_utc": overlap["start_utc"],
            "end_utc": overlap["end_utc"],
            "overlap_s": overlap["overlap_s"],
            "datalink_samples": len(datalink_samples),
            "flight_samples": len(flight_samples),
            "joined_samples": len(joined),
            "accepted_for_fit": accepted,
            "reject_reason": reject_reason,
        })

    joined_for_fit = annotate_joined_sample_stability(joined_for_fit)
    measured_hover_power_w = estimate_datalink_hover_power(joined_for_fit)
    power_reference_w = measured_hover_power_w or hover_power_w
    observations = build_datalink_speed_observations(
        joined_for_fit,
        min_speed_ms=2.0,
        max_speed_ms=25.0,
        min_samples=DATALINK_MIN_BIN_SAMPLES,
        power_reference_w=power_reference_w,
        stable_only=True,
        min_stable_fraction=0.5,
        extrapolation_start_ms=DATALINK_MEASURED_EXTRAPOLATION_START_MS,
    )
    empirical_curve = build_empirical_datalink_power_curve(observations)
    battery_qc_report = build_battery_qc_report(bin_paths, joined_for_fit)
    model_fit = build_measured_curve_model_fit(profile, sonuc, power_reference_w, observations)
    graph_paths = {}
    result = {
        "fit_mode": "measured_datalink_power_curve",
        "log_root": log_root,
        "date_hint": normalized_date_hint,
        "sync_report": sync_report,
        "battery_qc_report": battery_qc_report,
        "speed_bin_observations": observations,
        "empirical_curve": empirical_curve,
        "model_fit_residuals": model_fit["model_fit_residuals"],
        "model_functions": model_fit["model_functions"],
        "fit_audit": model_fit["fit_audit"],
        "model_profile": model_fit["profile"],
        "joined_sample_count": len(joined_for_fit),
        "measured_hover_power_w": measured_hover_power_w,
        "power_reference_w": power_reference_w,
        "utip_ms": model_fit["profile"].get("utip_ms"),
        "extrapolation_start_ms": DATALINK_MEASURED_EXTRAPOLATION_START_MS,
        "graph_paths": graph_paths,
    }
    if make_graph:
        graph_paths["empirical_power"] = plot_empirical_datalink_power_curve(
            empirical_curve,
            output_path=DATALINK_EMPIRICAL_OUTPUT_PATH,
        )
        graph_paths["diagnostic_surrogates"] = plot_measured_power_curve(
            observations,
            model_fit["model_functions"],
            output_path=DATALINK_DIAGNOSTIC_SURROGATE_OUTPUT_PATH,
        )
        graph_paths["battery"] = plot_battery_voltage_timeline(
            battery_qc_report.get("rows", []),
            sync_report,
            output_path=f"{DATALINK_MEASURED_OUTPUT_PREFIX}_battery_voltage.png",
        )
        graph_paths["audit"] = write_scientific_fit_audit(result)

    return result


def _mean_abs_error(residual_rows):
    if not residual_rows:
        return None
    return sum(abs(row["error"]) for row in residual_rows) / len(residual_rows)


def format_scientific_fit_audit_markdown(result):
    lines = [
        "# Scientific Model Fit Audit",
        "",
        f"Fit mode: `{result.get('fit_mode')}`",
        f"Date hint: `{result.get('date_hint')}`",
        f"Joined samples accepted for fit: `{result.get('joined_sample_count', 0)}`",
        "",
    ]
    if result.get("measured_hover_power_w"):
        lines.append(f"Measured DataLink hover reference: `{result['measured_hover_power_w']:.1f} W`")
    if result.get("power_reference_w"):
        lines.append(f"Power reference used: `{result['power_reference_w']:.1f} W`")
    if result.get("utip_ms"):
        lines.append(f"DataLink RPM Utip: `{result['utip_ms']:.1f} m/s`")

    empirical_curve = result.get("empirical_curve", {})
    lines.extend([
        "",
        "## Empirical DataLink P(v)",
        "",
        f"Measured speed range: `{empirical_curve.get('min_speed_ms')}` - `{empirical_curve.get('max_speed_ms')}` m/s",
        f"Stable samples in measured bins: `{empirical_curve.get('sample_count_total', 0)}`",
        f"Raw samples in measured bins: `{empirical_curve.get('raw_sample_count_total', 0)}`",
        f"Source BIN logs: `{', '.join(empirical_curve.get('source_bins', []))}`",
        f"Source DataLink sessions: `{', '.join(empirical_curve.get('source_sessions', []))}`",
        "",
        "| speed m/s | P/Ph | n | raw n | stable fraction | dt max s | source bins |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ])
    for obs in empirical_curve.get("measured_points", []):
        dt_s_max = obs.get("dt_s_max")
        dt_text = f"{dt_s_max:.3f}" if dt_s_max is not None else ""
        lines.append(
            f"| {obs['speed_ms']:.2f} | {obs['power_ratio']:.4f} | "
            f"{obs.get('sample_count', 0)} | {obs.get('raw_sample_count', 0)} | "
            f"{obs.get('stable_fraction', 0.0):.2f} | {dt_text} | "
            f"{', '.join(obs.get('source_bins', []))} |"
        )

    fit_audit = result.get("fit_audit", {})
    lines.extend([
        "",
        "## Diagnostic Surrogate Fits",
        "",
        fit_audit.get("scope", ""),
        "",
        "| model | status | MAE | reasons | warnings |",
        "|---|---|---:|---|---|",
    ])
    residuals = result.get("model_fit_residuals", {})
    for model_name, audit in fit_audit.get("models", {}).items():
        mae = _mean_abs_error(residuals.get(model_name, []))
        mae_text = f"{mae:.5f}" if mae is not None else ""
        lines.append(
            f"| {model_name} | {audit.get('status')} | {mae_text} | "
            f"{', '.join(audit.get('reasons', []))} | "
            f"{', '.join(audit.get('warnings', []))} |"
        )
    lines.extend([
        "",
        "### Key fitted and derived parameters",
        "",
        "| model | parameters |",
        "|---|---|",
    ])
    report_param_keys = [
        "v0_ms",
        "utip_ms",
        "f0",
        "induced_fraction",
        "k_par",
        "body_cda_fit_m2",
        "body_cd_fit",
        "lambda_n_per_ms",
        "lambda_source",
        "k_body",
        "k_rotor",
        "drag_scale",
        "induced_relief_scale",
        "extra_cubic_k",
        "p_profile_hover_w",
        "lift_power_per_newton",
    ]
    for model_name, audit in fit_audit.get("models", {}).items():
        params = audit.get("params", {})
        parts = []
        for key in report_param_keys:
            if key not in params:
                continue
            value = params[key]
            if isinstance(value, float):
                parts.append(f"{key}={value:.6g}")
            elif isinstance(value, (int, str)):
                parts.append(f"{key}={value}")
        lines.append(f"| {model_name} | {'; '.join(parts)} |")
    lines.append("")
    return "\n".join(lines)


def write_scientific_fit_audit(result, output_path=DATALINK_SCIENTIFIC_AUDIT_PATH):
    path = Path(output_path)
    path.write_text(format_scientific_fit_audit_markdown(result), encoding="utf-8")
    return path.resolve()


def print_datalink_measured_curve_report(result):
    print("\n--- DATALINK MEASURED P(V) ANALIZI ---")
    print(f"Log root: {result['log_root']}")
    print(f"Date hint: {result.get('date_hint')}")
    print(f"Joined samples accepted for fit: {result['joined_sample_count']}")
    if result.get("measured_hover_power_w"):
        print(f"Measured DataLink hover reference: {result['measured_hover_power_w']:.1f} W")
    print(f"DataLink RPM Utip: {result.get('utip_ms', 0.0):.1f} m/s")
    print(f"Extrapolation starts above: {result['extrapolation_start_ms']:.1f} m/s")
    empirical_curve = result.get("empirical_curve", {})
    if empirical_curve.get("measured_points"):
        print(
            "Empirical DataLink P(v) measured range: "
            f"{empirical_curve['min_speed_ms']:.2f}-{empirical_curve['max_speed_ms']:.2f} m/s; "
            f"n={empirical_curve['sample_count_total']} stable samples"
        )

    print("\nSync report:")
    for row in result["sync_report"]:
        status = "ACCEPT" if row["accepted_for_fit"] else f"SKIP ({row['reject_reason']})"
        print(
            f"  {status}: {row['session']} + {row['bin']} "
            f"{row['timestamp_mode']}, overlap={row['overlap_s']:.1f}s, "
            f"joined={row['joined_samples']}"
        )

    battery = result["battery_qc_report"]
    print("\nBattery QC:")
    print(f"  BAT rows: {battery['bat_rows']}")
    if battery.get("voltr_start_v") is not None:
        print(
            f"  VoltR: {battery['voltr_start_v']:.2f} -> "
            f"{battery['voltr_end_v']:.2f} V "
            f"(min={battery['voltr_min_v']:.2f}, max={battery['voltr_max_v']:.2f})"
        )
    print(f"  DataLink integrated energy: {battery['datalink_energy_wh']:.1f} Wh")
    print(f"  BAT EnrgTot delta raw: {battery['battery_energy_delta_raw']:.4f}")
    print(f"  Direct current fit enabled: {battery['direct_current_fit_enabled']}")
    for warning in battery.get("warnings", []):
        print(f"  [QC] {warning}")

    print("\nMeasured speed bins:")
    for obs in result["speed_bin_observations"]:
        region = obs.get("extrapolation_region", "measured")
        print(
            f"  {obs['label']}: v={obs['speed_ms']:.2f} m/s, "
            f"P/Ph={obs['power_ratio']:.4f}, P={obs['power_w']:.1f} W, "
            f"n={obs['sample_count']}, raw_n={obs.get('raw_sample_count', 0)}, "
            f"stable={obs['stable_fraction']:.2f}, bins={','.join(obs.get('source_bins', []))}, "
            f"Utip={obs['utip_ms']:.1f}, {region}"
        )

    print("\nDiagnostic surrogate fit audit:")
    for model_name, audit in result.get("fit_audit", {}).get("models", {}).items():
        reasons = ",".join(audit.get("reasons", [])) or "-"
        warnings = ",".join(audit.get("warnings", [])) or "-"
        print(f"  {model_name}: {audit['status']} reasons={reasons} warnings={warnings}")

    print("\nDiagnostic surrogate residual summary:")
    for name, rows in result["model_fit_residuals"].items():
        mae = _mean_abs_error(rows)
        if mae is not None:
            print(f"  {name}: mean_abs_err={mae:.4f}")

    if result.get("graph_paths"):
        print("\nMeasured curve graph outputs:")
        for path in result["graph_paths"].values():
            print(f"  * {path}")


def _fit_two_parameter_weighted(rows):
    s11 = s12 = s22 = b1 = b2 = 0.0
    for a1, a2, target, weight in rows:
        s11 += weight * a1 * a1
        s12 += weight * a1 * a2
        s22 += weight * a2 * a2
        b1 += weight * a1 * target
        b2 += weight * a2 * target
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-18:
        raise ValueError("Weighted Zeng fit is singular.")
    return (b1 * s22 - b2 * s12) / det, (s11 * b2 - s12 * b1) / det


def _zeng_linear_row(speed_ms, power_ratio, v0_ms, utip_ms, weight):
    induced = zeng_induced_ratio(speed_ms, v0_ms)
    profile = zeng_profile_ratio(speed_ms, utip_ms)
    return profile - induced, speed_ms ** 3, power_ratio - induced, weight


def fit_weighted_zeng_ratio(v0_ms, utip_ms, observations, k_prior=None,
                            k_prior_speed_ms=6.0, k_prior_weight=1.0,
                            k_priors=None):
    rows = [
        _zeng_linear_row(obs["speed_ms"], obs["power_ratio"], v0_ms, utip_ms, obs["weight"])
        for obs in observations
    ]
    if k_prior is not None and k_prior_weight > 0:
        rows.append((0.0, k_prior_speed_ms ** 3,
                     k_prior * k_prior_speed_ms ** 3, k_prior_weight))
    if k_priors:
        for prior in k_priors:
            speed_ms = prior["speed_ms"]
            weight = prior.get("weight", 1.0)
            if speed_ms > 0 and weight > 0:
                rows.append((0.0, speed_ms ** 3,
                             prior["k_par"] * speed_ms ** 3, weight))

    f0, k_par = _fit_two_parameter_weighted(rows)
    return {
        "v0_ms": v0_ms,
        "utip_ms": utip_ms,
        "f0": f0,
        "induced_fraction": 1.0 - f0,
        "k_par": k_par,
    }


def fit_observation_weighted_zeng(v0_ms, utip_ms, hover_power_w,
                                  theoretical_params, attitude_fit,
                                  observations):
    k_prior = None
    k_prior_weight = 0.0
    k_priors = []
    if attitude_fit and attitude_fit.get("cda_m2"):
        rho = attitude_fit.get("rho", 1.225)
        for speed_bin in attitude_fit.get("speed_bins", []):
            k_bin = 0.5 * rho * speed_bin["cda_m2"] / hover_power_w
            k_priors.append({
                "speed_ms": speed_bin["speed_ms"],
                "k_par": k_bin,
                "weight": min(3.0, max(0.5, speed_bin["sample_count"] / 500.0)),
                "sample_count": speed_bin["sample_count"],
                "cda_m2": speed_bin["cda_m2"],
            })
        if not k_priors:
            k_prior = 0.5 * rho * attitude_fit["cda_m2"] / hover_power_w
            k_prior_weight = 6.0

    if not observations:
        hover_split = theoretical_params["p0_mech"] / (
            theoretical_params["p0_mech"] + theoretical_params["pi_mech"]
        )
        return {
            "v0_ms": v0_ms,
            "utip_ms": utip_ms,
            "f0": hover_split,
            "induced_fraction": 1.0 - hover_split,
            "k_par": theoretical_params["k_par"],
            "fit_observations": [],
            "k_prior": k_prior,
            "k_priors": k_priors,
            "attitude_fit": attitude_fit,
        }

    params = fit_weighted_zeng_ratio(
        v0_ms,
        utip_ms,
        observations,
        k_prior=k_prior,
        k_prior_speed_ms=observations[0]["speed_ms"],
        k_prior_weight=k_prior_weight,
        k_priors=k_priors,
    )
    params.update({
        "fit_observations": observations,
        "k_prior": k_prior,
        "k_priors": k_priors,
        "attitude_fit": attitude_fit,
    })
    return params


def fit_hybrid_calibrated_zeng(v_endurance, v_range, v0_ms, utip_ms, hover_power_w,
                               attitude_fit, voltage_anchor,
                               p_endurance_ratio=0.914, p_range_ratio=1.092):
    # Hybrid model:
    # - Tutar: Bauersfeld'in endurance/range guc oranlarini ana referans kabul eder.
    # - Tutar: stadyum voltaj verisinden gelen 6 m/s civari P/Ph anchor'ini kullanir.
    # - Tutar: logdaki farkli hiz bantlarindan pitch/roll kaynakli C_DA/k_drag prior'lari kullanir.
    # - Tutmaz: P(v)'yi tamamen logdan olcmus saymaz; current/power olmadigi icin 10 m/s ustu halen extrapolation.
    observations = [
        {"label": "Bauersfeld endurance", "speed_ms": v_endurance,
         "power_ratio": p_endurance_ratio, "weight": 30.0},
        {"label": "Bauersfeld range", "speed_ms": v_range,
         "power_ratio": p_range_ratio, "weight": 30.0},
    ]
    if voltage_anchor:
        observations.append({
            "label": "stadium voltage lap",
            "speed_ms": voltage_anchor["speed_ms"],
            "power_ratio": voltage_anchor["power_ratio"],
            "weight": 8.0,
        })

    k_prior = None
    k_prior_weight = 0.0
    k_priors = []
    if attitude_fit and attitude_fit.get("cda_m2"):
        rho = attitude_fit.get("rho", 1.225)
        for speed_bin in attitude_fit.get("speed_bins", []):
            k_bin = 0.5 * rho * speed_bin["cda_m2"] / hover_power_w
            k_priors.append({
                "speed_ms": speed_bin["speed_ms"],
                "k_par": k_bin,
                "weight": min(3.0, max(0.5, speed_bin["sample_count"] / 500.0)),
                "sample_count": speed_bin["sample_count"],
                "cda_m2": speed_bin["cda_m2"],
            })
        if not k_priors:
            k_prior = 0.5 * rho * attitude_fit["cda_m2"] / hover_power_w
            k_prior_weight = 6.0

    params = fit_weighted_zeng_ratio(
        v0_ms,
        utip_ms,
        observations,
        k_prior=k_prior,
        k_prior_speed_ms=voltage_anchor["speed_ms"] if voltage_anchor else 6.0,
        k_prior_weight=k_prior_weight,
        k_priors=k_priors,
    )
    params.update({
        "fit_observations": observations,
        "k_prior": k_prior,
        "k_priors": k_priors,
        "attitude_fit": attitude_fit,
        "voltage_anchor": voltage_anchor,
    })
    return params


def fit_pure_zeng_flight(v0_ms, utip_ms, hover_power_w, theoretical_params,
                         attitude_fit, voltage_anchor):
    # Pure flight-fit Zeng model:
    # - Tutar: P(0)/P_hover = 1 olacak sekilde normalize edilmis Zeng formunu kullanir.
    # - Tutar: log hiz bantlarindan gelen C_DA bilgisini parasite/drag terimine koyar.
    # - Tutar: stadyum voltaj verisiyle 6 m/s civari P/Ph noktasini yakalar.
    # - Tutmaz: Bauersfeld endurance/range noktalarini zorla tutmaz.
    # - Tutmaz: U_tip, v0 gibi rotor parametrelerini serbest fit etmez; mevcut logda bunlar ayirt edilemez.
    if attitude_fit and attitude_fit.get("cda_m2"):
        if attitude_fit.get("speed_bins"):
            total_weight = 0.0
            weighted_cda = 0.0
            for speed_bin in attitude_fit["speed_bins"]:
                weight = min(3.0, max(0.5, speed_bin["sample_count"] / 500.0))
                weighted_cda += weight * speed_bin["cda_m2"]
                total_weight += weight
            cda_m2 = weighted_cda / total_weight
            cda_source = "attitude_log_speed_bins"
        else:
            cda_m2 = attitude_fit["cda_m2"]
            cda_source = "attitude_log"
    else:
        cda_m2 = theoretical_params["cda_body_m2"]
        cda_source = "theoretical_profile"

    k_par = 0.5 * theoretical_params["rho"] * cda_m2 / hover_power_w

    if voltage_anchor:
        speed_ms = voltage_anchor["speed_ms"]
        induced = zeng_induced_ratio(speed_ms, v0_ms)
        profile = zeng_profile_ratio(speed_ms, utip_ms)
        denom = profile - induced
        if abs(denom) > 1e-12:
            f0_raw = (voltage_anchor["power_ratio"] - induced - k_par * speed_ms ** 3) / denom
            f0 = max(0.0, min(1.0, f0_raw))
            f0_source = "stadium_voltage_anchor"
        else:
            f0_raw = None
            f0 = theoretical_params["p0_mech"] / (theoretical_params["p0_mech"] + theoretical_params["pi_mech"])
            f0_source = "theoretical_hover_split"
    else:
        f0_raw = None
        f0 = theoretical_params["p0_mech"] / (theoretical_params["p0_mech"] + theoretical_params["pi_mech"])
        f0_source = "theoretical_hover_split"

    return {
        "v0_ms": v0_ms,
        "utip_ms": utip_ms,
        "f0": f0,
        "f0_raw": f0_raw,
        "induced_fraction": 1.0 - f0,
        "k_par": k_par,
        "cda_m2": cda_m2,
        "cda_source": cda_source,
        "f0_source": f0_source,
        "attitude_fit": attitude_fit,
        "voltage_anchor": voltage_anchor,
    }


def estimate_faessler_drag_from_attitude_log(profile, min_speed_ms=3.0,
                                             max_speed_ms=7.2,
                                             max_accel_ms2=0.8,
                                             max_tilt_deg=25.0):
    path = find_attitude_log_path(profile)
    if not path:
        return None

    rows = load_attitude_rows(path)
    if len(rows) < 5:
        return None

    rho = profile.get("rho", 1.225)
    mass_kg = profile["mass_kg"]
    weight_n = mass_kg * 9.81
    body_area_m2 = profile.get("body_area_m2", profile.get("cda_body_m2", 0.045))

    samples = []
    used_speeds = []
    used_accels = []
    bin_width_ms = 0.5

    for idx, row in enumerate(rows):
        if idx == 0 or idx == len(rows) - 1:
            accel_xy = float("inf")
        else:
            prev_row = rows[idx - 1]
            next_row = rows[idx + 1]
            dt = next_row["time_s"] - prev_row["time_s"]
            if dt <= 0 or dt > 1.0:
                accel_xy = float("inf")
            else:
                ax = (next_row["vx_ms"] - prev_row["vx_ms"]) / dt
                ay = (next_row["vy_ms"] - prev_row["vy_ms"]) / dt
                accel_xy = math.hypot(ax, ay)

        speed_ms = math.hypot(row["vx_ms"], row["vy_ms"])
        pitch_rad = math.radians(row["pitch_deg"])
        roll_rad = math.radians(row["roll_deg"])
        cos_tilt = math.cos(pitch_rad) * math.cos(roll_rad)
        tilt_rad = math.acos(max(-1.0, min(1.0, cos_tilt)))
        tilt_deg = math.degrees(tilt_rad)

        if not (min_speed_ms <= speed_ms <= max_speed_ms):
            continue
        if accel_xy > max_accel_ms2:
            continue
        if tilt_deg > max_tilt_deg:
            continue

        total_drag_n = weight_n * math.tan(tilt_rad)
        if math.isfinite(total_drag_n) and 0.0 <= total_drag_n <= 200.0:
            samples.append((speed_ms, total_drag_n, accel_xy))
            used_speeds.append(speed_ms)
            used_accels.append(accel_xy)

    if len(samples) < 20:
        return {
            "path": path,
            "raw_count": len(rows),
            "sample_count": len(samples),
            "body_area_m2": body_area_m2,
            "error": "not_enough_filtered_samples",
        }

    # Fit total tilt-implied drag as F = 0.5*rho*C_DA*v^2 + lambda*v.
    s11 = s12 = s22 = b1 = b2 = 0.0
    for speed_ms, total_drag_n, _accel_xy in samples:
        x_body = 0.5 * rho * speed_ms ** 2
        x_rotor = speed_ms
        s11 += x_body * x_body
        s12 += x_body * x_rotor
        s22 += x_rotor * x_rotor
        b1 += x_body * total_drag_n
        b2 += x_rotor * total_drag_n
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-18:
        cda_fit_m2 = 0.0
        lambda_fit = max(0.0, b2 / s22) if s22 > 0 else 0.0
    else:
        cda_fit_m2 = (b1 * s22 - b2 * s12) / det
        lambda_fit = (s11 * b2 - s12 * b1) / det
        if cda_fit_m2 < 0.0 and s22 > 0:
            cda_fit_m2 = 0.0
            lambda_fit = b2 / s22
        if lambda_fit < 0.0 and s11 > 0:
            lambda_fit = 0.0
            cda_fit_m2 = b1 / s11
    cda_fit_m2 = max(0.0, cda_fit_m2)
    lambda_fit = max(0.0, lambda_fit)

    lambda_values = []
    total_drag_values = []
    body_drag_values = []
    rotor_drag_values = []
    bin_samples = {}
    for speed_ms, total_drag_n, _accel_xy in samples:
        body_drag_n = 0.5 * rho * cda_fit_m2 * speed_ms ** 2
        rotor_drag_n = max(0.0, total_drag_n - body_drag_n)
        lambda_n_per_ms = rotor_drag_n / speed_ms if speed_ms > 0 else 0.0
        lambda_values.append(lambda_n_per_ms)
        total_drag_values.append(total_drag_n)
        body_drag_values.append(body_drag_n)
        rotor_drag_values.append(rotor_drag_n)
        bin_center = round((math.floor(speed_ms / bin_width_ms) + 0.5) * bin_width_ms, 2)
        bin_samples.setdefault(bin_center, []).append(lambda_n_per_ms)

    lambda_sorted = sorted(lambda_values)
    speed_sorted = sorted(used_speeds)
    accel_sorted = sorted(used_accels)
    p10 = _percentile(lambda_sorted, 0.10)
    p90 = _percentile(lambda_sorted, 0.90)
    trimmed = [value for value in lambda_values if p10 <= value <= p90]
    speed_bins = []
    for bin_center, values in sorted(bin_samples.items()):
        if len(values) < 30:
            continue
        sorted_values = sorted(values)
        b10 = _percentile(sorted_values, 0.10)
        b90 = _percentile(sorted_values, 0.90)
        btrim = [value for value in sorted_values if b10 <= value <= b90]
        speed_bins.append({
            "speed_ms": bin_center,
            "sample_count": len(values),
            "lambda_n_per_ms": _median(btrim),
            "lambda_p25_n_per_ms": _percentile(sorted_values, 0.25),
            "lambda_p75_n_per_ms": _percentile(sorted_values, 0.75),
        })

    return {
        "path": path,
        "raw_count": len(rows),
        "sample_count": len(lambda_values),
        "rho": rho,
        "body_area_m2": body_area_m2,
        "body_cda_fit_m2": cda_fit_m2,
        "body_cd_fit": cda_fit_m2 / body_area_m2 if body_area_m2 > 0 else None,
        "lambda_fit_n_per_ms": lambda_fit,
        "lambda_n_per_ms": _median(trimmed),
        "lambda_p25_n_per_ms": _percentile(lambda_sorted, 0.25),
        "lambda_p75_n_per_ms": _percentile(lambda_sorted, 0.75),
        "speed_median_ms": _median(used_speeds),
        "speed_p95_ms": _percentile(speed_sorted, 0.95),
        "accel_p95_ms2": _percentile(accel_sorted, 0.95),
        "total_drag_median_n": _median(total_drag_values),
        "body_drag_median_n": _median(body_drag_values),
        "rotor_drag_median_n": _median(rotor_drag_values),
        "min_speed_ms": min_speed_ms,
        "max_accel_ms2": max_accel_ms2,
        "speed_bins": speed_bins,
    }


def fit_faessler_drag_constrained_zeng(v0_ms, utip_ms, hover_power_w,
                                       theoretical_params, faessler_fit,
                                       voltage_anchor, observations=None):
    rho = theoretical_params["rho"]
    body_area_m2 = theoretical_params.get(
        "body_area_m2",
        theoretical_params.get("cda_body_m2", 0.045),
    )
    body_cda_fit_m2 = body_area_m2
    body_cd_fit = None
    if faessler_fit and faessler_fit.get("body_cda_fit_m2") is not None:
        body_cda_fit_m2 = faessler_fit["body_cda_fit_m2"]
        body_cd_fit = faessler_fit.get("body_cd_fit")

    lambda_n_per_ms = 0.0
    lambda_source = "none"
    if faessler_fit and faessler_fit.get("lambda_fit_n_per_ms") is not None:
        lambda_n_per_ms = faessler_fit["lambda_fit_n_per_ms"]
        lambda_source = "attitude_log"

    k_body = 0.5 * rho * body_cda_fit_m2 / hover_power_w
    k_rotor = lambda_n_per_ms / hover_power_w
    hover_split = theoretical_params["p0_mech"] / (
        theoretical_params["p0_mech"] + theoretical_params["pi_mech"]
    )
    f0 = max(0.0, min(1.0, hover_split))
    f0_raw = None
    drag_scale = 1.0
    drag_scale_raw = None
    f0_source = "theoretical_hover_split"

    if observations is None:
        observations = []
        if voltage_anchor:
            observations.append({
                "label": "stadium voltage lap",
                "speed_ms": voltage_anchor["speed_ms"],
                "power_ratio": voltage_anchor["power_ratio"],
                "weight": 8.0,
            })

    if len(observations) >= 2:
        rows = []
        for obs in observations:
            speed_ms = obs["speed_ms"]
            induced = zeng_induced_ratio(speed_ms, v0_ms)
            profile = zeng_profile_ratio(speed_ms, utip_ms)
            drag_shape = k_body * speed_ms ** 3 + k_rotor * speed_ms ** 2
            rows.append((
                profile - induced,
                drag_shape,
                obs["power_ratio"] - induced,
                obs.get("weight", 1.0),
            ))
        try:
            f0_raw, drag_scale_raw = _fit_two_parameter_weighted(rows)
            f0 = max(0.0, min(1.0, f0_raw))
            drag_scale = max(0.0, drag_scale_raw)
            f0_source = "all_data_weighted_fit"
        except ValueError:
            pass
    else:
        num = den = 0.0
        for obs in observations:
            speed_ms = obs["speed_ms"]
            induced = zeng_induced_ratio(speed_ms, v0_ms)
            profile = zeng_profile_ratio(speed_ms, utip_ms)
            x = profile - induced
            y = (
                obs["power_ratio"]
                - induced
                - k_body * speed_ms ** 3
                - k_rotor * speed_ms ** 2
            )
            weight = obs.get("weight", 1.0)
            num += weight * x * y
            den += weight * x * x
        if den > 1e-18:
            f0_raw = num / den
            f0 = max(0.0, min(1.0, f0_raw))
            f0_source = observations[0]["label"]

    return {
        "v0_ms": v0_ms,
        "utip_ms": utip_ms,
        "f0": f0,
        "f0_raw": f0_raw,
        "induced_fraction": 1.0 - f0,
        "k_body": k_body,
        "k_rotor": k_rotor,
        "drag_scale": drag_scale,
        "drag_scale_raw": drag_scale_raw,
        "body_area_m2": body_area_m2,
        "body_cda_fit_m2": body_cda_fit_m2,
        "body_cd_fit": body_cd_fit,
        "lambda_n_per_ms": lambda_n_per_ms,
        "lambda_source": lambda_source,
        "f0_source": f0_source,
        "faessler_fit": faessler_fit,
        "voltage_anchor": voltage_anchor,
        "fit_observations": observations,
    }


def power_ratio_faessler_drag_constrained_zeng(speed_ms, params):
    v = max(0.0, speed_ms)
    drag_scale = params.get("drag_scale", 1.0)
    return (
        params["f0"] * zeng_profile_ratio(v, params["utip_ms"])
        + params["induced_fraction"] * zeng_induced_ratio(v, params["v0_ms"])
        + drag_scale * (params["k_body"] * v ** 3 + params["k_rotor"] * v ** 2)
    )


def build_kirschstein_params(profile, hover_power_reference_w, faessler_fit=None):
    rho = profile.get("rho", 1.225)
    mass_kg = profile["mass_kg"]
    weight_n = mass_kg * 9.81
    num_rotors = profile["num_rotors"]
    radius_m = profile["prop_diameter_inch"] * 0.0254 / 2.0
    utip_ms = profile["utip_ms"]
    solidity_s = profile.get("rotor_solidity_s", 0.05)
    blade_drag = profile.get("blade_profile_drag_delta", 0.012)
    p_hotel_w = profile.get("p_hotel_w", 0.0)
    body_area_m2 = profile.get("body_area_m2", profile.get("cda_body_m2", 0.045))
    body_cda_fit_m2 = body_area_m2
    body_cd_fit = None
    if faessler_fit and faessler_fit.get("body_cda_fit_m2") is not None:
        body_cda_fit_m2 = faessler_fit["body_cda_fit_m2"]
        body_cd_fit = faessler_fit.get("body_cd_fit")
    p_profile_hover_w = (
        num_rotors * rho * radius_m * utip_ms ** 3
        * solidity_s * blade_drag / 8.0
    )
    lift_power_per_newton = max(
        0.0,
        (hover_power_reference_w - p_profile_hover_w - p_hotel_w) / weight_n,
    )

    return {
        "rho": rho,
        "mass_kg": mass_kg,
        "weight_n": weight_n,
        "num_rotors": num_rotors,
        "radius_m": radius_m,
        "utip_ms": utip_ms,
        "rotor_solidity_s": solidity_s,
        "blade_profile_drag_delta": blade_drag,
        "p_hotel_w": p_hotel_w,
        "body_area_m2": body_area_m2,
        "body_cda_fit_m2": body_cda_fit_m2,
        "body_cd_fit": body_cd_fit,
        "p_profile_hover_w": p_profile_hover_w,
        "lift_power_per_newton": lift_power_per_newton,
        "hover_power_reference_w": hover_power_reference_w,
    }


def power_kirschstein_component(speed_ms, params):
    v = max(0.0, speed_ms)
    rho = params["rho"]
    body_drag_n = 0.5 * rho * params["body_cda_fit_m2"] * v ** 2
    p_air_w = body_drag_n * v
    thrust_n = math.sqrt(params["weight_n"] ** 2 + body_drag_n ** 2)
    p_lift_w = params["lift_power_per_newton"] * thrust_n
    p_profile_w = params["p_profile_hover_w"] * (
        1.0 + 3.0 * v ** 2 / params["utip_ms"] ** 2
    )
    return p_air_w + p_lift_w + p_profile_w + params["p_hotel_w"]


def fit_kirschstein_all_data(profile, hover_power_reference_w, v0_ms,
                             observations, faessler_fit=None):
    params = build_kirschstein_params(profile, hover_power_reference_w, faessler_fit)
    rows = []
    for obs in observations:
        speed_ms = obs["speed_ms"]
        base_ratio = power_kirschstein_component(speed_ms, params) / hover_power_reference_w
        induced_relief_shape = zeng_induced_ratio(speed_ms, v0_ms) - 1.0
        cubic_shape = speed_ms ** 3
        rows.append((
            induced_relief_shape,
            cubic_shape,
            obs["power_ratio"] - base_ratio,
            obs.get("weight", 1.0),
        ))

    try:
        induced_relief_scale, extra_cubic_k = _fit_two_parameter_weighted(rows)
    except ValueError:
        induced_relief_scale = 0.0
        extra_cubic_k = 0.0

    params.update({
        "v0_ms": v0_ms,
        "induced_relief_scale": induced_relief_scale,
        "extra_cubic_k": extra_cubic_k,
        "fit_observations": observations,
    })
    return params


def fit_kirschstein_experimental_data(profile, hover_power_reference_w, v0_ms,
                                      voltage_anchor, faessler_fit=None):
    params = build_kirschstein_params(profile, hover_power_reference_w, faessler_fit)
    observations = []
    if voltage_anchor:
        observations.append({
            "label": "stadium voltage lap",
            "speed_ms": voltage_anchor["speed_ms"],
            "power_ratio": voltage_anchor["power_ratio"],
            "weight": 8.0,
        })

    induced_relief_scale = 0.0
    extra_cubic_k = 0.0
    if observations:
        obs = observations[0]
        speed_ms = obs["speed_ms"]
        base_ratio = power_kirschstein_component(speed_ms, params) / hover_power_reference_w
        target_delta = obs["power_ratio"] - base_ratio
        induced_relief_shape = zeng_induced_ratio(speed_ms, v0_ms) - 1.0
        if abs(induced_relief_shape) > 1e-12:
            induced_relief_scale = target_delta / induced_relief_shape
        elif speed_ms > 0:
            extra_cubic_k = target_delta / speed_ms ** 3

    params.update({
        "v0_ms": v0_ms,
        "induced_relief_scale": induced_relief_scale,
        "extra_cubic_k": extra_cubic_k,
        "fit_observations": observations,
    })
    return params


def power_ratio_kirschstein_all_data(speed_ms, params):
    v = max(0.0, speed_ms)
    base_ratio = power_kirschstein_component(v, params) / params["hover_power_reference_w"]
    correction = (
        params.get("induced_relief_scale", 0.0) * (zeng_induced_ratio(v, params["v0_ms"]) - 1.0)
        + params.get("extra_cubic_k", 0.0) * v ** 3
    )
    return max(0.01, base_ratio + correction)


def zeng_fit_residuals(params, observations):
    residuals = []
    for obs in observations:
        predicted = power_ratio_bauersfeld_anchored_zeng(obs["speed_ms"], params)
        residuals.append({
            "label": obs["label"],
            "speed_ms": obs["speed_ms"],
            "target": obs["power_ratio"],
            "predicted": predicted,
            "error": predicted - obs["power_ratio"],
        })
    return residuals


def estimate_cda_from_pitch(speed_ms, pitch_deg, mass_kg, rho=1.225):
    weight_n = mass_kg * 9.81
    drag_n = weight_n * math.tan(math.radians(abs(pitch_deg)))
    return 2.0 * drag_n / (rho * speed_ms ** 2)


def estimate_tilt_from_cda(speed_ms, cda_m2, mass_kg, rho=1.225):
    weight_n = mass_kg * 9.81
    drag_n = 0.5 * rho * cda_m2 * speed_ms ** 2
    theta_rad = math.atan(drag_n / weight_n)
    theta_deg = math.degrees(theta_rad)
    drag_power_w = drag_n * speed_ms
    return drag_n, theta_deg, drag_power_w


def calculate_flight_for_speed(speed_ms, power_ratio, hover_power_w, battery_wh, correction_factor):
    power_w = hover_power_w * power_ratio
    time_100_min = battery_wh / power_w * 60.0
    time_20_min = time_100_min * correction_factor
    range_20_km = speed_ms * 3.6 * time_20_min / 60.0
    time_10_min = time_20_min * 1.125
    range_10_km = range_20_km * 1.125
    return {
        "speed_ms": speed_ms,
        "power_ratio": power_ratio,
        "power_w": power_w,
        "time_20_min": time_20_min,
        "range_20_km": range_20_km,
        "time_10_min": time_10_min,
        "range_10_km": range_10_km,
    }


def print_speed_table(title, rows):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(f"{'speed':>7} | {'P/Ph':>7} | {'power W':>9} | {'%20 min':>8} | {'%20 km':>8} | {'%10 min':>8} | {'%10 km':>8}")
    print("-" * 78)
    for row in rows:
        print(f"{row['speed_ms']:7.2f} | {row['power_ratio']:7.3f} | {row['power_w']:9.1f} | "
              f"{row['time_20_min']:8.2f} | {row['range_20_km']:8.2f} | "
              f"{row['time_10_min']:8.2f} | {row['range_10_km']:8.2f}")


def parse_speed_list(raw):
    speeds = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            speeds.append(float(part))
    return speeds


def ask_utip(prop_diameter_inch, default_utip=80.0):
    print("\nUtip bilgisi:")
    print("1) RPM gir, Utip hesaplansin")
    print("2) Utip direkt gir")
    secim = input("Secim [2]: ").strip() or "2"
    if secim == "1":
        rpm = float(input("Hover RPM tahmini: ").strip())
        return tip_speed_from_rpm(prop_diameter_inch, rpm), rpm
    raw = input(f"Utip m/s [{default_utip}]: ").strip()
    return (float(raw) if raw else default_utip), None


def build_speed_model_profile(vehicle_choice, current_mass_kg, current_num_rotors,
                              current_prop_diameter_inch, current_drag_area_cm2,
                              require_theoretical=False):
    if vehicle_choice == "1":
        profile = dict(FIRFIR_SPEED_PRESET)
        cda_pitch = estimate_cda_from_pitch(
            profile["pitch_measurement_speed_ms"],
            profile["pitch_measurement_deg"],
            profile["mass_kg"],
            profile["rho"],
        )
        profile["cda_pitch_m2"] = cda_pitch
        profile["cda_body_m2"] = cda_pitch
        profile["body_area_m2"] = FIRFIR_SPEED_PRESET["body_area_m2"]
        profile["utip_from_rpm_ms"] = tip_speed_from_rpm(
            profile["prop_diameter_inch"],
            profile["hover_rpm_estimate"],
        )
        return profile

    profile = {
        "vehicle_name": "Manual/current drone",
        "mass_kg": current_mass_kg,
        "num_rotors": current_num_rotors,
        "prop_diameter_inch": current_prop_diameter_inch,
        "rho": 1.225,
        "p_endurance_ratio": 0.914,
        "p_range_ratio": 1.092,
        "pitch_measurement_speed_ms": None,
        "pitch_measurement_deg": None,
    }
    print("\nManual/current drone icin sadece eksik Zeng parametreleri sorulacak.")
    profile["utip_ms"], profile["hover_rpm_estimate"] = ask_utip(current_prop_diameter_inch, 80.0)

    if require_theoretical:
        profile["blade_count"] = int(input("Blade count [2]: ").strip() or "2")
        profile["rotor_solidity_s"] = float(input("Rotor solidity s [0.05]: ").strip() or "0.05")
        profile["mean_blade_chord_m"] = (
            profile["rotor_solidity_s"] * math.pi * (current_prop_diameter_inch * 0.0254 / 2.0)
            / profile["blade_count"]
        )
        profile["blade_profile_drag_delta"] = float(input("Blade profile drag delta [0.012]: ").strip() or "0.012")
        profile["induced_correction_k"] = float(input("Induced correction k [0.1]: ").strip() or "0.1")
        profile["eta_propulsion"] = float(input("Eta propulsion [1.0]: ").strip() or "1.0")
        profile["p_hotel_w"] = float(input("Hotel power W [0.0]: ").strip() or "0.0")
        default_cda = current_drag_area_cm2 / 10000.0
        profile["cda_body_m2"] = float(input(f"Body C_DA m2 [{default_cda:.4f}]: ").strip() or default_cda)
        profile["body_area_m2"] = current_drag_area_cm2 / 10000.0
    else:
        profile.update({
            "blade_count": 2,
            "rotor_solidity_s": 0.05,
            "mean_blade_chord_m": 0.029,
            "blade_profile_drag_delta": 0.012,
            "induced_correction_k": 0.1,
            "eta_propulsion": 1.0,
            "p_hotel_w": 0.0,
            "cda_body_m2": current_drag_area_cm2 / 10000.0,
            "body_area_m2": current_drag_area_cm2 / 10000.0,
        })
    return profile


def legacy_ratio_factory(v_endurance, v_range):
    a, b = calculate_poly_coeffs(v_endurance, v_range)
    return lambda v: max(0.01, a * v ** 2 + b * v + 1.0)


def make_speed_sweep(model_functions, hover_power_w, battery_wh, correction_factor):
    speeds = [0.1 + i * (24.9 / 249.0) for i in range(250)]
    sweep = {}
    for name, ratio_fn in model_functions.items():
        sweep[name] = [
            calculate_flight_for_speed(speed, ratio_fn(speed), hover_power_w, battery_wh, correction_factor)
            for speed in speeds
        ]
    return sweep


def plot_range_time_vs_speed(model_functions, hover_power_w, battery_wh, correction_factor,
                             output_path="range_time_vs_speed.png"):
    import matplotlib.pyplot as plt

    sweep = make_speed_sweep(model_functions, hover_power_w, battery_wh, correction_factor)
    fig, (ax_range, ax_time) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    for name, rows in sweep.items():
        speeds = [r["speed_ms"] for r in rows]
        ax_range.plot(speeds, [r["range_10_km"] for r in rows], label=name)
        ax_time.plot(speeds, [r["time_10_min"] for r in rows], label=name)
    ax_range.set_ylabel("%10 rezerv menzil [km]")
    ax_range.grid(True, alpha=0.3)
    ax_range.legend(fontsize=8)
    ax_time.set_xlabel("Hiz [m/s]")
    ax_time.set_ylabel("%10 rezerv sure [dk]")
    ax_time.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


def plot_power_ratio_vs_speed(model_functions, v_endurance, v_range,
                              pitch_speed=None, pitch_deg=None,
                              output_path="power_ratio_vs_speed.png",
                              extra_points=None,
                              show_bauersfeld_points=True):
    import matplotlib.pyplot as plt

    speeds = [0.1 + i * (24.9 / 249.0) for i in range(250)]
    fig, ax = plt.subplots(figsize=(10, 6))
    for name, ratio_fn in model_functions.items():
        ax.plot(speeds, [ratio_fn(s) for s in speeds], label=name)
    ax.scatter([0.0], [1.0], marker="o", color="black", label="hover")
    if show_bauersfeld_points:
        ax.scatter([v_endurance], [0.914], marker="s", color="green", label="Bauersfeld endurance")
        ax.scatter([v_range], [1.092], marker="D", color="red", label="Bauersfeld range")
    if extra_points:
        for point in extra_points:
            ax.scatter(
                [point["speed_ms"]],
                [point["power_ratio"]],
                marker=point.get("marker", "x"),
                color=point.get("color", "purple"),
                label=point.get("label", "extra point"),
            )
    if pitch_speed and pitch_deg:
        ax.axvline(pitch_speed, linestyle="--", color="gray", alpha=0.7)
        ax.annotate(
            f"pitch-derived CdA point: {pitch_speed:.2f} m/s, {pitch_deg:.0f} deg",
            xy=(pitch_speed, 1.0),
            xytext=(pitch_speed + 0.7, 1.25),
            arrowprops={"arrowstyle": "->", "color": "gray"},
            fontsize=8,
        )
    ax.set_xlabel("Hiz [m/s]")
    ax.set_ylabel("P(V) / P_hover")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


# Model secim ozeti:
# 1) legacy_parabola_baseline:
#    Tutar: hover, Bauersfeld endurance ve range noktalarindan gecen eski baseline.
#    Tutmaz: Zeng/rotor fizigi, turev kosullari ve log verisi; sadece kaba karsilastirma.
# 2) bauersfeld_anchored_zeng:
#    Tutar: P(0)=1, P(ve)=0.914, P(vr)=1.092; Zeng benzeri induced/profile/parasite sekli.
#    Tutmaz: attitude log ve stadyum voltaj verisi; 10.7 m/s sonrasi Zeng extrapolation.
# 3) theoretical_zeng_pitch_CDA:
#    Tutar: Zeng'in ham teorik rotor terimleri ve 6.04 m/s, 4 deg pitch'ten gelen C_DA.
#    Tutmaz: datasheet hover gucu; bu yuzden P(0)/P_hover 1 degil. Ana model degil, diagnostik.
# 4) hybrid_calibrated_zeng_fit:
#    Tutar: Bauersfeld anchor'lari + stadyum voltaj anchor'i + log hiz bandi C_DA prior'lari.
#    Tutmaz: power/current olcumu olmayan hizlarda tam dogrulama; yuksek hiz halen extrapolation.
# 5) pure_zeng_flight_fit:
#    Tutar: normalize Zeng formu + log hiz bandi C_DA + stadyum 6 m/s P/Ph anchor'i.
#    Tutmaz: Bauersfeld ve/vr anchor'larini zorla tutmaz; rotor parametrelerini serbest tune etmez.
# 6) faessler_drag_constrained_zeng:
#    Tutar: log tilt direncini body drag + linear rotor drag olarak ayirir.
#    Tutmaz: current/RPM gucu yok; yuksek hiz halen extrapolation.
# 7) kirschstein_component_benchmark:
#    Tutar: Pair + Plift + Pprofile + Pint bilesenlerini ayri hesaplar.
#    Tutmaz: 6 m/s voltaj anchor'ini zorla tutmaz; benchmark olarak kalir.
# 8) datalink_empirical_pv:
#    Tutar: 3 Temmuz DataLink + ArduPilot measured speed bins.
#    Tutmaz: olcum araligi disina deger uydurmaz.
MODEL_SELECTIONS = {
    "1": "legacy_parabola_baseline",
    "2": "bauersfeld_anchored_zeng",
    "3": "theoretical_zeng_pitch_CDA",
    "4": "hybrid_calibrated_zeng_fit",
    "5": "pure_zeng_flight_fit",
    "6": "faessler_drag_constrained_zeng",
    "7": "kirschstein_component_benchmark",
    "8": "datalink_empirical_pv",
}


def parse_model_selection(raw):
    raw = (raw or "4").strip().lower()
    if raw in {"all", "hepsi", "*"}:
        return list(MODEL_SELECTIONS.values())

    selected = []
    for part in raw.replace(";", ",").split(","):
        key = part.strip().lower()
        if not key:
            continue
        model_name = MODEL_SELECTIONS.get(key)
        if model_name is None and key in MODEL_SELECTIONS.values():
            model_name = key
        if model_name and model_name not in selected:
            selected.append(model_name)
    return selected or ["hybrid_calibrated_zeng_fit"]


def model_selection_requires_theoretical(raw):
    selected = parse_model_selection(raw)
    return any(name in {"theoretical_zeng_pitch_CDA", "pure_zeng_flight_fit"}
               for name in selected)


def print_model_descriptions():
    print("\n--- Model Se\u00e7imi ---")
    print("  1) legacy_parabola_baseline")
    print("       Kaynak: eski menzil1 parabola baseline; hover, endurance ve range noktalarindan gecer.")
    print("       Fit: iki parabol katsayisi, yalnizca P(0)=1, P(ve)=0.914, P(vr)=1.092 kosullarina gore.")
    print("       Kullanim: geriye donuk karsilastirma icin; yeni araclarda fiziksel extrapolation kaniti sayilmaz.")
    print("  2) bauersfeld_anchored_zeng")
    print("       Kaynak: Bauersfeld optimum hiz/guc oranlari + Zeng benzeri induced/profile/parasite sekli.")
    print("       Fit: f0=P_profile/Ph ve k_par; Utip, vi,h, kutle, disk alani olcum/giris olarak kalir.")
    print("       Kullanim: anchor tabanli analitik extrapolation; log verisi kullanmaz, dogrulama ayridir.")
    print("  3) theoretical_zeng_pitch_CDA")
    print("       Kaynak: Zeng rotor terimleri + pitch/tilt'ten turetilen body C_DA.")
    print("       Fit: ana serbest fit yok; rotor/geometri/eta/C_DA dogrudan giris veya log-derived.")
    print("       Kullanim: fizik sanity-check; P(0)/P_hover farki buyukse ana menzil modeli olarak guvenilmez.")
    print("  4) hybrid_calibrated_zeng_fit  [\u00d6neri]")
    print("       Kaynak: Bauersfeld anchor + stadyum voltaj turu + attitude log C_DA hiz bantlari.")
    print("       Fit: f0 ve k_par agirlikli least-squares; Utip/vi,h sabit, C_DA logdan prior olarak girer.")
    print("       Kullanim: ana operasyonel extrapolation adayi; residual ve anchor hatalariyla izlenmeli.")
    print("  5) pure_zeng_flight_fit")
    print("       Kaynak: normalize Zeng sekli + attitude-derived C_DA + stadyum 6 m/s anchor'i.")
    print("       Fit: k_par dogrudan C_DA'dan, f0 tek anchor'dan; Bauersfeld endurance/range zorlanmaz.")
    print("       Kullanim: Bauersfeld'den bagimsiz flight-fit bakisi; tek anchor'a fazla guvenmemek gerekir.")
    print("  6) faessler_drag_constrained_zeng")
    print("       Kaynak: Faessler rotor-drag fikri + attitude log tilt kuvveti + Zeng induced/profile sekli.")
    print("       Fit: body C_DA ve lambda logdan; gerekirse f0 ve drag_scale agirlikli fit edilir.")
    print("       Kullanim: body drag ile rotor drag ayrimini test eder; lambda/Cd mantikli aralikta kalmali.")
    print("  7) kirschstein_component_benchmark")
    print("       Kaynak: bilesen tabanli Pair + Plift + Pprofile + hotel power ayrimi.")
    print("       Fit: normal benchmark modunda az/hic fit; DataLink diagnostic modda induced relief ve cubic correction.")
    print("       Kullanim: Zeng ailesine karsi fizik benchmark'i; cok esnek fitlenirse bagimsiz dogrulama sayilmaz.")
    print("  8) datalink_empirical_pv")
    print("       Kaynak: 3 Temmuz DataLink guc/RPM + ArduPilot hiz/attitude zaman eslesmesi.")
    print("       Fit: model fit etmez; stable speed bin medyanlarini ve lineer aralik ici interpolasyonu raporlar.")
    print("       Kullanim: olcum katmani ve model kalibrasyon hedefi. Tek secilirse 4/6/7 analitik extrapolation da eklenir.")
    print("  Birden fazla model icin virgul kullan: 2,4,5,6,7,8 veya all")


def run_custom_speed_models(speeds, profile, model_choice, sonuc, hover_power_w,
                            battery_wh, correction_factor, make_graph,
                            datalink_log_root=None,
                            datalink_date_hint=DATALINK_MEASURED_CURVE_DATE_HINT):
    v_endurance = sonuc['optimal_endurance_speed_ms']
    v_range = sonuc['optimal_speed_ms']
    vi_h = sonuc['vi_h']

    model_functions = {
        "legacy_parabola_baseline": legacy_ratio_factory(v_endurance, v_range),
    }

    anchored_params = fit_bauersfeld_anchored_zeng(
        v_endurance,
        v_range,
        vi_h,
        profile["utip_ms"],
        profile.get("p_endurance_ratio", 0.914),
        profile.get("p_range_ratio", 1.092),
    )
    model_functions["bauersfeld_anchored_zeng"] = (
        lambda v, p=anchored_params: power_ratio_bauersfeld_anchored_zeng(v, p)
    )

    theoretical_params = build_theoretical_zeng_params(profile, hover_power_w)
    model_functions["theoretical_zeng_pitch_CDA"] = (
        lambda v, p=theoretical_params: power_theoretical_zeng(v, p) / hover_power_w
    )

    attitude_fit = estimate_cda_from_attitude_log(profile)
    if profile["vehicle_name"].lower().startswith("fir"):
        voltage_info = estimate_stadium_voltage_anchor(hover_power_w, battery_wh, correction_factor)
    else:
        voltage_info = {"preferred": None, "candidates": []}
    voltage_anchor = voltage_info.get("preferred")
    faessler_fit = estimate_faessler_drag_from_attitude_log(profile)

    hybrid_params = fit_hybrid_calibrated_zeng(
        v_endurance,
        v_range,
        vi_h,
        profile["utip_ms"],
        hover_power_w,
        attitude_fit,
        voltage_anchor,
        profile.get("p_endurance_ratio", 0.914),
        profile.get("p_range_ratio", 1.092),
    )
    model_functions["hybrid_calibrated_zeng_fit"] = (
        lambda v, p=hybrid_params: power_ratio_bauersfeld_anchored_zeng(v, p)
    )

    pure_params = fit_pure_zeng_flight(
        vi_h,
        profile["utip_ms"],
        hover_power_w,
        theoretical_params,
        attitude_fit,
        voltage_anchor,
    )
    model_functions["pure_zeng_flight_fit"] = (
        lambda v, p=pure_params: power_ratio_bauersfeld_anchored_zeng(v, p)
    )

    faessler_params = fit_faessler_drag_constrained_zeng(
        vi_h,
        profile["utip_ms"],
        hover_power_w,
        theoretical_params,
        faessler_fit,
        voltage_anchor,
    )
    model_functions["faessler_drag_constrained_zeng"] = (
        lambda v, p=faessler_params: power_ratio_faessler_drag_constrained_zeng(v, p)
    )

    kirschstein_params = build_kirschstein_params(profile, hover_power_w, faessler_fit=faessler_fit)
    model_functions["kirschstein_component_benchmark"] = (
        lambda v, p=kirschstein_params: power_kirschstein_component(v, p) / hover_power_w
    )

    requested_models = parse_model_selection(model_choice)
    empirical_result = None
    empirical_curve = None
    if "datalink_empirical_pv" in requested_models:
        try:
            empirical_result = run_datalink_measured_curve_analysis(
                profile,
                sonuc,
                hover_power_w,
                battery_wh,
                correction_factor,
                log_root=datalink_log_root,
                date_hint=datalink_date_hint,
                make_graph=False,
            )
            empirical_curve = empirical_result["empirical_curve"]
        except Exception as exc:
            print(f"DataLink empirical P(v) yuklenemedi: {exc}")

    selected = []
    for name in requested_models:
        if name in model_functions:
            selected.append(name)
        elif name == "datalink_empirical_pv" and empirical_curve:
            selected.append(name)
    selected = selected or ["hybrid_calibrated_zeng_fit"]
    analytic_selected = [name for name in selected if name in model_functions]
    if (
        empirical_curve
        and "datalink_empirical_pv" in selected
        and not analytic_selected
    ):
        companion_models = [
            name for name in DATALINK_EMPIRICAL_COMPANION_MODELS
            if name in model_functions
        ]
        selected.extend(companion_models)
        print(
            "\nDataLink empirical P(v) tek basina olcum katmanidir; "
            "extrapolation icin analitik companion modeller eklendi."
        )
        print("Eklenen modeller: " + ", ".join(companion_models))

    print("\nZeng / model parametre ozeti:")
    print(f"Vehicle/profile: {profile['vehicle_name']}")
    print(f"Utip: {profile['utip_ms']:.2f} m/s")
    if profile.get("hover_rpm_estimate"):
        print(f"Utip RPM check: {tip_speed_from_rpm(profile['prop_diameter_inch'], profile['hover_rpm_estimate']):.2f} m/s")
    print("Utip = pi * D * RPM / 60.")
    print("Zeng paper'daki A rotor disk alanidir; govde frontal alani degildir.")
    print("Govde drag icin C_DA_body_m2 ayri kullanilir.")
    print("450 cm2 sadece frontal area baslangic girdisidir; pitch_CDA modelinde Firfir icin 0.38 m2 kullanilir.")
    if profile["vehicle_name"].lower().startswith("fir"):
        cda_pitch = estimate_cda_from_pitch(6.04, 4.0, 12.4, 1.225)
        print(f"Pitch-derived C_DA: {cda_pitch:.3f} m2 (6.04 m/s, 4 deg). theoretical_zeng_pitch_CDA modelinde kullaniliyor.")

    if attitude_fit:
        print("\nFlight attitude fit verisi:")
        print(f"CSV: {attitude_fit['path']}")
        print(f"Ham satir: {attitude_fit.get('raw_count', 0)}, kullanilan satir: {attitude_fit.get('sample_count', 0)}")
        if attitude_fit.get("cda_m2"):
            print(f"Attitude-derived C_DA: {attitude_fit['cda_m2']:.3f} m2 "
                  f"(p25={attitude_fit['cda_p25_m2']:.3f}, p75={attitude_fit['cda_p75_m2']:.3f})")
            print(f"Kullanilan hiz median/p95: {attitude_fit['speed_median_ms']:.2f} / {attitude_fit['speed_p95_ms']:.2f} m/s")
            print(f"Yatay ivme p95 filtresi: {attitude_fit['accel_p95_ms2']:.2f} m/s2")
            if attitude_fit.get("speed_bins"):
                print("Hiz bandi C_DA noktalari:")
                for speed_bin in attitude_fit["speed_bins"]:
                    print(f"  v~{speed_bin['speed_ms']:.2f} m/s: "
                          f"C_DA={speed_bin['cda_m2']:.3f} m2, n={speed_bin['sample_count']}")
        elif attitude_fit.get("error"):
            print(f"Attitude fit kullanilamadi: {attitude_fit['error']}")
    else:
        print("\nFlight attitude fit verisi bulunamadi.")

    if faessler_fit:
        print("\nFaessler rotor-drag fit verisi:")
        print(f"CSV: {faessler_fit['path']}")
        print(f"Ham satir: {faessler_fit.get('raw_count', 0)}, kullanilan satir: {faessler_fit.get('sample_count', 0)}")
        if faessler_fit.get("lambda_n_per_ms") is not None:
            print(f"Body area: {faessler_fit['body_area_m2']:.4f} m2")
            print(f"Log-fit body C_DA: {faessler_fit['body_cda_fit_m2']:.4f} m2")
            if faessler_fit.get("body_cd_fit") is not None:
                print(f"Log-fit effective Cd: {faessler_fit['body_cd_fit']:.3f}")
            print(f"Rotor drag lambda: {faessler_fit['lambda_fit_n_per_ms']:.4f} N/(m/s) "
                  f"(p25={faessler_fit['lambda_p25_n_per_ms']:.4f}, "
                  f"p75={faessler_fit['lambda_p75_n_per_ms']:.4f})")
            print(f"Kullanilan hiz median/p95: {faessler_fit['speed_median_ms']:.2f} / {faessler_fit['speed_p95_ms']:.2f} m/s")
            print(f"Drag median total/body/rotor: "
                  f"{faessler_fit['total_drag_median_n']:.2f} / "
                  f"{faessler_fit['body_drag_median_n']:.2f} / "
                  f"{faessler_fit['rotor_drag_median_n']:.2f} N")
            if faessler_fit.get("speed_bins"):
                print("Hiz bandi lambda noktalari:")
                for speed_bin in faessler_fit["speed_bins"]:
                    print(f"  v~{speed_bin['speed_ms']:.2f} m/s: "
                          f"lambda={speed_bin['lambda_n_per_ms']:.4f} N/(m/s), "
                          f"n={speed_bin['sample_count']}")
        elif faessler_fit.get("error"):
            print(f"Faessler fit kullanilamadi: {faessler_fit['error']}")
    else:
        print("\nFaessler rotor-drag fit verisi bulunamadi.")

    if voltage_anchor:
        print("\nStadyum voltaj tur anchor:")
        print(f"Secilen yorum: {voltage_anchor['span_label']}, sag={voltage_anchor['sag_per_cell']:.2f} V/cell")
        print(f"Mesafe: {voltage_anchor['distance_km']:.2f} km, "
              f"SOC dususu: {voltage_anchor['delta_soc']:.2f} puan")
        print(f"Anchor: p({voltage_anchor['speed_ms']:.1f} m/s) = {voltage_anchor['power_ratio']:.3f}")
        if voltage_info.get("candidates"):
            ratios = [c["power_ratio"] for c in voltage_info["candidates"]]
            print(f"Alternatif yorum araligi: {min(ratios):.3f} - {max(ratios):.3f} P/Ph")

    if "bauersfeld_anchored_zeng" in selected:
        print("\nBauersfeld-anchored Zeng fit:")
        print(f"v0 / vi_h: {anchored_params['v0_ms']:.3f} m/s")
        print(f"f0 = P0/Ph: {anchored_params['f0']:.5f}")
        print(f"induced_fraction = Pi/Ph: {anchored_params['induced_fraction']:.5f}")
        print(f"k_par: {anchored_params['k_par']:.8f} 1/(m/s)^3")
        print(f"p(v_endurance): {power_ratio_bauersfeld_anchored_zeng(v_endurance, anchored_params):.4f} hedef 0.914")
        print(f"p(v_range): {power_ratio_bauersfeld_anchored_zeng(v_range, anchored_params):.4f} hedef 1.092")

    if "theoretical_zeng_pitch_CDA" in selected:
        p_hover_theory = power_theoretical_zeng(0.0, theoretical_params)
        ratio = p_hover_theory / hover_power_w
        print("\nPure theoretical Zeng - pitch-derived CdA:")
        print(f"C_DA_body_m2: {theoretical_params['cda_body_m2']:.4f} m2")
        if profile.get("pitch_measurement_speed_ms") and profile.get("pitch_measurement_deg"):
            print(f"Pitch source: {profile['pitch_measurement_speed_ms']:.2f} m/s, {profile['pitch_measurement_deg']:.1f} deg")
        print(f"Rotor total disk area: {theoretical_params['area_total_m2']:.4f} m2")
        print(f"Equivalent mean chord: {theoretical_params['equivalent_chord_m']:.4f} m")
        print(f"Theoretical hover power: {p_hover_theory:.1f} W")
        print(f"Datasheet/interpolated hover power: {hover_power_w:.1f} W")
        print(f"Theoretical/datasheet hover ratio: {ratio:.3f}")
        if abs(ratio - 1.0) > 0.20:
            print("UYARI: Pure Zeng theoretical hover power ile datasheet hover power arasinda buyuk fark var; "
                  "solidity/chord, delta, eta veya Utip varsayimi hatali olabilir.")

    if "hybrid_calibrated_zeng_fit" in selected:
        print("\nHybrid calibrated Zeng fit:")
        print(f"v0 / vi_h: {hybrid_params['v0_ms']:.3f} m/s")
        print(f"f0 = P0/Ph: {hybrid_params['f0']:.5f}")
        print(f"induced_fraction = Pi/Ph: {hybrid_params['induced_fraction']:.5f}")
        print(f"k_par: {hybrid_params['k_par']:.8f} 1/(m/s)^3")
        if hybrid_params.get("k_prior") is not None:
            print(f"attitude C_DA k prior: {hybrid_params['k_prior']:.8f} 1/(m/s)^3")
        if hybrid_params.get("k_priors"):
            print("attitude hiz bandi k priorlari:")
            for prior in hybrid_params["k_priors"]:
                print(f"  v~{prior['speed_ms']:.2f} m/s: "
                      f"C_DA={prior['cda_m2']:.3f} m2, "
                      f"k={prior['k_par']:.8f}, w={prior['weight']:.2f}, n={prior['sample_count']}")
        for residual in zeng_fit_residuals(hybrid_params, hybrid_params["fit_observations"]):
            print(f"  {residual['label']}: v={residual['speed_ms']:.2f}, "
                  f"target={residual['target']:.4f}, fit={residual['predicted']:.4f}, "
                  f"err={residual['error']:+.4f}")

    if "pure_zeng_flight_fit" in selected:
        print("\nPure Zeng flight fit:")
        print(f"v0 / vi_h: {pure_params['v0_ms']:.3f} m/s")
        print(f"f0 = P0/Ph: {pure_params['f0']:.5f} (source={pure_params['f0_source']})")
        if pure_params.get("f0_raw") is not None and abs(pure_params["f0"] - pure_params["f0_raw"]) > 1e-9:
            print(f"f0 raw clamp oncesi: {pure_params['f0_raw']:.5f}")
        print(f"induced_fraction = Pi/Ph: {pure_params['induced_fraction']:.5f}")
        print(f"C_DA: {pure_params['cda_m2']:.3f} m2 (source={pure_params['cda_source']})")
        print(f"k_par: {pure_params['k_par']:.8f} 1/(m/s)^3")
        if voltage_anchor:
            pure_at_anchor = power_ratio_bauersfeld_anchored_zeng(voltage_anchor["speed_ms"], pure_params)
            print(f"p({voltage_anchor['speed_ms']:.1f} m/s): {pure_at_anchor:.4f} "
                  f"hedef {voltage_anchor['power_ratio']:.4f}")

    if "faessler_drag_constrained_zeng" in selected:
        print("\nFaessler drag-constrained Zeng:")
        print(f"v0 / vi_h: {faessler_params['v0_ms']:.3f} m/s")
        print(f"f0 = P0/Ph: {faessler_params['f0']:.5f} (source={faessler_params['f0_source']})")
        if faessler_params.get("f0_raw") is not None and abs(faessler_params["f0"] - faessler_params["f0_raw"]) > 1e-9:
            print(f"f0 raw clamp oncesi: {faessler_params['f0_raw']:.5f}")
        print(f"body area: {faessler_params['body_area_m2']:.4f} m2")
        print(f"log-fit body C_DA: {faessler_params['body_cda_fit_m2']:.4f} m2")
        if faessler_params.get("body_cd_fit") is not None:
            print(f"log-fit effective Cd: {faessler_params['body_cd_fit']:.3f}")
        print(f"rotor drag lambda: {faessler_params['lambda_n_per_ms']:.4f} N/(m/s) "
              f"(source={faessler_params['lambda_source']})")
        print(f"k_body: {faessler_params['k_body']:.8f} 1/(m/s)^3")
        print(f"k_rotor: {faessler_params['k_rotor']:.8f} 1/(m/s)^2")
        print(f"drag_scale: {faessler_params['drag_scale']:.4f}")
        if faessler_params.get("drag_scale_raw") is not None and abs(faessler_params["drag_scale"] - faessler_params["drag_scale_raw"]) > 1e-9:
            print(f"drag_scale raw clamp oncesi: {faessler_params['drag_scale_raw']:.4f}")
        if voltage_anchor:
            faessler_at_anchor = power_ratio_faessler_drag_constrained_zeng(
                voltage_anchor["speed_ms"], faessler_params
            )
            print(f"p({voltage_anchor['speed_ms']:.1f} m/s): {faessler_at_anchor:.4f} "
                  f"hedef {voltage_anchor['power_ratio']:.4f}")

    if "kirschstein_component_benchmark" in selected:
        print("\nKirschstein component benchmark:")
        print(f"body area: {kirschstein_params['body_area_m2']:.4f} m2")
        print(f"log-fit/body fallback C_DA: {kirschstein_params['body_cda_fit_m2']:.4f} m2")
        if kirschstein_params.get("body_cd_fit") is not None:
            print(f"log-fit effective Cd: {kirschstein_params['body_cd_fit']:.3f}")
        print(f"P_profile_hover: {kirschstein_params['p_profile_hover_w']:.1f} W")
        print(f"lift_power_per_newton: {kirschstein_params['lift_power_per_newton']:.4f} W/N")
        print(f"solidity: {kirschstein_params['rotor_solidity_s']:.4f}")
        print(f"blade drag delta/Cbd: {kirschstein_params['blade_profile_drag_delta']:.4f}")
        if voltage_anchor:
            kirschstein_at_anchor = (
                power_kirschstein_component(voltage_anchor["speed_ms"], kirschstein_params)
                / hover_power_w
            )
            print(f"p({voltage_anchor['speed_ms']:.1f} m/s): {kirschstein_at_anchor:.4f} "
                  f"hedef {voltage_anchor['power_ratio']:.4f} "
                  f"err={kirschstein_at_anchor - voltage_anchor['power_ratio']:+.4f}")

    if "datalink_empirical_pv" in selected and empirical_curve:
        print("\nDataLink empirical P(v):")
        print(
            f"Measured-only range: {empirical_curve['min_speed_ms']:.2f}-"
            f"{empirical_curve['max_speed_ms']:.2f} m/s; "
            f"n={empirical_curve['sample_count_total']} stable samples"
        )
        print(
            "Bu katman olcum araligi disina deger uydurmaz; "
            "olcum disi hizlar icin asagidaki analitik modeller kullanilir."
        )
        for speed in speeds:
            evaluation = evaluate_empirical_datalink_power_ratio(empirical_curve, speed)
            if evaluation["available"]:
                row = calculate_flight_for_speed(
                    speed,
                    evaluation["power_ratio"],
                    hover_power_w,
                    battery_wh,
                    correction_factor,
                )
                print(
                    f"  v={speed:.2f} m/s: P/Ph={evaluation['power_ratio']:.4f} "
                    f"({evaluation['basis']}), P={row['power_w']:.1f} W, "
                    f"%20 sure={row['time_20_min']:.1f} dk, "
                    f"%20 menzil={row['range_20_km']:.2f} km"
                )
            else:
                print(
                    f"  v={speed:.2f} m/s: empirical olcum disi "
                    f"({evaluation.get('min_speed_ms'):.2f}-"
                    f"{evaluation.get('max_speed_ms'):.2f} m/s); fizik model gerekir."
                )

    for model_name in selected:
        if model_name == "datalink_empirical_pv":
            continue
        rows = [
            calculate_flight_for_speed(speed, model_functions[model_name](speed),
                                       hover_power_w, battery_wh, correction_factor)
            for speed in speeds
        ]
        print_speed_table(model_name, rows)

    if make_graph:
        graph_models = {name: model_functions[name] for name in selected if name in model_functions}
        extra_points = []
        if voltage_anchor:
            extra_points.append({
                "speed_ms": voltage_anchor["speed_ms"],
                "power_ratio": voltage_anchor["power_ratio"],
                "marker": "X",
                "color": "purple",
                "label": "stadium voltage anchor",
            })
        if empirical_curve:
            for obs in empirical_curve.get("measured_points", []):
                extra_points.append({
                    "speed_ms": obs["speed_ms"],
                    "power_ratio": obs["power_ratio"],
                    "marker": "o",
                    "color": "blue",
                    "label": f"{obs['label']} n={obs.get('sample_count', 0)}",
                })
        try:
            range_path = None
            power_path = None
            if graph_models:
                range_output_path = "range_time_vs_speed.png"
                power_output_path = "power_ratio_vs_speed.png"
                if "datalink_empirical_pv" in selected and empirical_curve:
                    range_output_path = DATALINK_EMPIRICAL_COMPARISON_RANGE_OUTPUT_PATH
                    power_output_path = DATALINK_EMPIRICAL_COMPARISON_POWER_OUTPUT_PATH
                range_path = plot_range_time_vs_speed(
                    graph_models,
                    hover_power_w,
                    battery_wh,
                    correction_factor,
                    output_path=range_output_path,
                )
                power_path = plot_power_ratio_vs_speed(
                    graph_models,
                    v_endurance,
                    v_range,
                    profile.get("pitch_measurement_speed_ms"),
                    profile.get("pitch_measurement_deg"),
                    output_path=power_output_path,
                    extra_points=extra_points,
                )
            empirical_path = None
            if empirical_curve:
                empirical_path = plot_empirical_datalink_power_curve(empirical_curve)
            print("\nGrafik ciktilari:")
            if range_path:
                print(f"* {range_path}")
            if power_path:
                print(f"* {power_path}")
            if empirical_path:
                print(f"* {empirical_path}")
            import matplotlib.pyplot as plt
            print("plt.show() cagriliyor.")
            plt.show()
        except Exception as exc:
            print(f"Grafik olusturulamadi: {exc}")


def run_independent_model_comparison(speeds, profile, sonuc, hover_power_w,
                                     battery_wh, correction_factor,
                                     make_graph=True,
                                     fit_mode="all_data_with_bauersfeld"):
    v_endurance = sonuc['optimal_endurance_speed_ms']
    v_range = sonuc['optimal_speed_ms']
    vi_h = sonuc['vi_h']

    fit_mode = (fit_mode or "all_data_with_bauersfeld").strip().lower()
    if fit_mode in {"2", "experimental", "experimental_only", "deneysel", "deneysel_only"}:
        fit_mode = "experimental_only"
    elif fit_mode in {"3", "datalink", "datalink_all", "datalink_all_data",
                      "datalink-informed all-data", "datalink_all_data_fit"}:
        fit_mode = "datalink_all_data"
    elif fit_mode in {"4", "datalink_experimental", "datalink_experimental_only",
                      "datalink-informed experimental-only"}:
        fit_mode = "datalink_experimental_only"
    else:
        fit_mode = "all_data_with_bauersfeld"

    attitude_fit = estimate_cda_from_attitude_log(profile)
    faessler_fit = estimate_faessler_drag_from_attitude_log(profile)
    if profile["vehicle_name"].lower().startswith("fir"):
        voltage_info = estimate_stadium_voltage_anchor(hover_power_w, battery_wh, correction_factor)
    else:
        voltage_info = {"preferred": None, "candidates": []}
    voltage_anchor = voltage_info.get("preferred")

    datalink_result = {
        "fit_allowed": False,
        "observations": [],
        "raw_observations": [],
        "qc": {"warnings": ["datalink_not_requested"]},
        "overlaps": [],
        "utip_ms": None,
    }
    datalink_observations = []
    if fit_mode.startswith("datalink"):
        datalink_result = build_datalink_power_observations(
            profile,
            hover_power_w,
            voltage_anchor=voltage_anchor,
        )
        datalink_observations = datalink_result.get("observations", [])
        if datalink_result.get("utip_ms"):
            profile = dict(profile)
            profile["utip_ms"] = datalink_result["utip_ms"]
            profile["utip_source"] = "datalink_rpm"
            profile["hover_rpm_estimate"] = (
                datalink_result["utip_ms"] * 60.0
                / (math.pi * profile["prop_diameter_inch"] * 0.0254)
            )

    theoretical_params = build_theoretical_zeng_params(profile, hover_power_w)

    experimental_observations = []
    if voltage_anchor:
        experimental_observations.append({
            "label": "stadium voltage lap",
            "speed_ms": voltage_anchor["speed_ms"],
            "power_ratio": voltage_anchor["power_ratio"],
            "weight": 8.0,
        })
    experimental_observations.extend(datalink_observations)

    all_data_observations = [
        {"label": "Bauersfeld endurance", "speed_ms": v_endurance,
         "power_ratio": profile.get("p_endurance_ratio", 0.914), "weight": 30.0},
        {"label": "Bauersfeld range", "speed_ms": v_range,
         "power_ratio": profile.get("p_range_ratio", 1.092), "weight": 30.0},
    ]
    all_data_observations.extend(experimental_observations)

    if fit_mode in {"experimental_only", "datalink_experimental_only"}:
        observations = experimental_observations
        if fit_mode.startswith("datalink"):
            zeng_params = fit_observation_weighted_zeng(
                vi_h,
                profile["utip_ms"],
                hover_power_w,
                theoretical_params,
                attitude_fit,
                observations,
            )
        else:
            zeng_params = fit_pure_zeng_flight(
                vi_h,
                profile["utip_ms"],
                hover_power_w,
                theoretical_params,
                attitude_fit,
                voltage_anchor,
            )
        faessler_params = fit_faessler_drag_constrained_zeng(
            vi_h,
            profile["utip_ms"],
            hover_power_w,
            theoretical_params,
            faessler_fit,
            voltage_anchor,
            observations=observations,
        )
        if fit_mode.startswith("datalink"):
            kirschstein_params = fit_kirschstein_all_data(
                profile,
                hover_power_w,
                vi_h,
                observations,
                faessler_fit=faessler_fit,
            )
            model_functions = {
                "zeng_datalink_experimental_fit": (
                    lambda v, p=zeng_params: power_ratio_bauersfeld_anchored_zeng(v, p)
                ),
                "faessler_datalink_experimental_fit": (
                    lambda v, p=faessler_params: power_ratio_faessler_drag_constrained_zeng(v, p)
                ),
                "kirschstein_datalink_experimental_fit": (
                    lambda v, p=kirschstein_params: power_ratio_kirschstein_all_data(v, p)
                ),
            }
            source_lines = [
                "* zeng_datalink_experimental_fit: stadyum + attitude + DataLink power/RPM; Bauersfeld yok.",
                "* faessler_datalink_experimental_fit: Faessler drag + DataLink P/Ph; Bauersfeld yok.",
                "* kirschstein_datalink_experimental_fit: component model + DataLink P/Ph; Bauersfeld yok.",
            ]
            range_output_path = "datalink_experimental_model_comparison_range_time.png"
            power_output_path = "datalink_experimental_model_comparison_power_ratio.png"
            residual_heading = "DataLink deneysel-only anchor residual'lari:"
        else:
            kirschstein_params = fit_kirschstein_experimental_data(
                profile,
                hover_power_w,
                vi_h,
                voltage_anchor,
                faessler_fit=faessler_fit,
            )
            model_functions = {
                "zeng_experimental_fit": (
                    lambda v, p=zeng_params: power_ratio_bauersfeld_anchored_zeng(v, p)
                ),
                "faessler_experimental_fit": (
                    lambda v, p=faessler_params: power_ratio_faessler_drag_constrained_zeng(v, p)
                ),
                "kirschstein_experimental_fit": (
                    lambda v, p=kirschstein_params: power_ratio_kirschstein_all_data(v, p)
                ),
            }
            source_lines = [
                "* zeng_experimental_fit: log-derived drag + stadyum voltaj; Bauersfeld yok.",
                "* faessler_experimental_fit: log-fit body C_DA/lambda + stadyum voltaj; Bauersfeld yok.",
                "* kirschstein_experimental_fit: log-fit body C_DA/lambda + component model + stadyum voltaj; Bauersfeld yok.",
            ]
            range_output_path = "experimental_only_model_comparison_range_time.png"
            power_output_path = "experimental_only_model_comparison_power_ratio.png"
            residual_heading = "Deneysel-only anchor residual'lari:"
        show_bauersfeld_points = False
    else:
        observations = all_data_observations
        if fit_mode.startswith("datalink"):
            zeng_params = fit_observation_weighted_zeng(
                vi_h,
                profile["utip_ms"],
                hover_power_w,
                theoretical_params,
                attitude_fit,
                observations,
            )
        else:
            zeng_params = fit_hybrid_calibrated_zeng(
                v_endurance,
                v_range,
                vi_h,
                profile["utip_ms"],
                hover_power_w,
                attitude_fit,
                voltage_anchor,
                profile.get("p_endurance_ratio", 0.914),
                profile.get("p_range_ratio", 1.092),
            )
        faessler_params = fit_faessler_drag_constrained_zeng(
            vi_h,
            profile["utip_ms"],
            hover_power_w,
            theoretical_params,
            faessler_fit,
            voltage_anchor,
            observations=observations,
        )
        kirschstein_params = fit_kirschstein_all_data(
            profile,
            hover_power_w,
            vi_h,
            observations,
            faessler_fit=faessler_fit,
        )
        if fit_mode.startswith("datalink"):
            model_functions = {
                "zeng_datalink_all_data_fit": (
                    lambda v, p=zeng_params: power_ratio_bauersfeld_anchored_zeng(v, p)
                ),
                "faessler_datalink_all_data_fit": (
                    lambda v, p=faessler_params: power_ratio_faessler_drag_constrained_zeng(v, p)
                ),
                "kirschstein_datalink_all_data_fit": (
                    lambda v, p=kirschstein_params: power_ratio_kirschstein_all_data(v, p)
                ),
            }
            source_lines = [
                "* zeng_datalink_all_data_fit: Bauersfeld + stadyum + attitude + DataLink power/RPM.",
                "* faessler_datalink_all_data_fit: Bauersfeld + Faessler drag + DataLink P/Ph.",
                "* kirschstein_datalink_all_data_fit: Bauersfeld + component model + DataLink P/Ph.",
            ]
            range_output_path = "datalink_all_data_model_comparison_range_time.png"
            power_output_path = "datalink_all_data_model_comparison_power_ratio.png"
            residual_heading = "DataLink all-data anchor residual'lari:"
        else:
            model_functions = {
                "zeng_all_data_fit": (
                    lambda v, p=zeng_params: power_ratio_bauersfeld_anchored_zeng(v, p)
                ),
                "faessler_all_data_fit": (
                    lambda v, p=faessler_params: power_ratio_faessler_drag_constrained_zeng(v, p)
                ),
                "kirschstein_all_data_fit": (
                    lambda v, p=kirschstein_params: power_ratio_kirschstein_all_data(v, p)
                ),
            }
            source_lines = [
                "* zeng_all_data_fit: Bauersfeld + voltaj + log-derived drag prior.",
                "* faessler_all_data_fit: Bauersfeld + voltaj + log-fit body C_DA/lambda.",
                "* kirschstein_all_data_fit: Bauersfeld + voltaj + log-fit body C_DA/lambda + component model.",
            ]
            range_output_path = "independent_model_comparison_range_time.png"
            power_output_path = "independent_model_comparison_power_ratio.png"
            residual_heading = "All-data anchor residual'lari:"
        show_bauersfeld_points = True

    print("\n--- BAGIMSIZ MODEL KARSILASTIRMASI ---")
    if fit_mode == "experimental_only":
        print("Deneysel-only mod: Bauersfeld anchorlari fitte ve grafikte kullanilmiyor.")
    elif fit_mode == "datalink_experimental_only":
        print("DataLink deneysel-only mod: DataLink + stadyum + log, Bauersfeld fitte yok.")
    elif fit_mode == "datalink_all_data":
        print("DataLink all-data mod: Bauersfeld + stadyum + log + DataLink beraber fitleniyor.")
    else:
        print("All-data mod: Bauersfeld anchorlari + loglar + stadyum voltaj beraber fitleniyor.")
    print("Bauersfeld-only ve tek bir karisim/hybrid cizgisi bu karsilastirmaya dahil degil.")
    print(f"Vehicle/profile: {profile['vehicle_name']}")
    print(f"Utip: {profile['utip_ms']:.2f} m/s")
    if profile.get("utip_source") == "datalink_rpm":
        print("Utip source: DataLink RPM kalite kontrolunden gecmis deger.")
    if attitude_fit:
        print(f"Attitude CSV: {attitude_fit['path']}")
        print(f"Attitude fit sample: {attitude_fit.get('sample_count', 0)} / {attitude_fit.get('raw_count', 0)}")
    else:
        print("Attitude CSV: bulunamadi")
    if faessler_fit:
        print(f"Faessler fit sample: {faessler_fit.get('sample_count', 0)} / {faessler_fit.get('raw_count', 0)}")
        if faessler_fit.get("lambda_n_per_ms") is not None:
            print(f"Body area: {faessler_fit['body_area_m2']:.4f} m2")
            print(f"Log-fit body C_DA: {faessler_fit['body_cda_fit_m2']:.4f} m2")
            if faessler_fit.get("body_cd_fit") is not None:
                print(f"Log-fit effective Cd: {faessler_fit['body_cd_fit']:.3f}")
            print(f"Faessler lambda: {faessler_fit['lambda_fit_n_per_ms']:.4f} N/(m/s)")
    else:
        print("Faessler fit: log bulunamadi")
    if voltage_anchor:
        print(f"Stadyum voltaj anchor: p({voltage_anchor['speed_ms']:.1f} m/s)="
              f"{voltage_anchor['power_ratio']:.4f}, "
              f"{voltage_anchor['span_label']}, sag={voltage_anchor['sag_per_cell']:.2f} V/cell")
    else:
        print("Stadyum voltaj anchor: bu profil icin kullanilmadi")

    if fit_mode.startswith("datalink"):
        print("\nDataLink QC:")
        qc = datalink_result.get("qc", {})
        if datalink_result.get("session_date_hint"):
            print(f"DataLink date hint: {datalink_result['session_date_hint']}")
        if datalink_result.get("datalink_hover_power_w"):
            print(f"DataLink measured hover reference: "
                  f"{datalink_result['datalink_hover_power_w']:.1f} W")
        elif datalink_result.get("power_reference_w"):
            print(f"DataLink power reference: {datalink_result['power_reference_w']:.1f} W")
        if qc.get("power_reference_source"):
            print(f"DataLink power reference source: {qc['power_reference_source']}")
        if datalink_result.get("fit_allowed"):
            print(f"DataLink fit observations accepted: {len(datalink_observations)}")
        else:
            print("DataLink fit observations accepted: 0")
        for warning in qc.get("warnings", []):
            print(f"  [QC] {warning}")
        if qc.get("anchor_source"):
            print(f"  P/Ph QC target source: {qc['anchor_source']}")
        for overlap in datalink_result.get("overlaps", []):
            print(
                f"  overlap: session={overlap.get('session')}, bin={overlap.get('bin')}, "
                f"mode={overlap.get('timestamp_mode')}, overlap={overlap.get('overlap_s', 0):.1f}s, "
                f"joined={overlap.get('joined_samples', 0)}"
            )
        nearest_6 = qc.get("nearest_6ms")
        if nearest_6:
            print(
                f"  6 m/s P/Ph check: DataLink={nearest_6['power_ratio']:.4f}, "
                f"target={qc.get('target_power_ratio', 0.0):.4f}, "
                f"tol=+/-{qc.get('tolerance_ratio', 0.0):.2f}"
            )
        for obs in datalink_observations:
            print(
                f"  DataLink obs: {obs['label']}, v={obs['speed_ms']:.2f}, "
                f"P/Ph={obs['power_ratio']:.4f}, n={obs.get('sample_count', 0)}, "
                f"rpm={obs.get('rpm_median', 0):.0f}, Utip={obs.get('utip_ms', 0):.1f}"
            )

    print("\nModel kaynak ozeti:")
    for line in source_lines:
        print(line)
    print(f"Faessler drag_scale: {faessler_params['drag_scale']:.4f}")
    if faessler_params.get("drag_scale_raw") is not None:
        print(f"Faessler raw drag_scale: {faessler_params['drag_scale_raw']:.4f}")
    print(f"Kirschstein induced_relief_scale: {kirschstein_params['induced_relief_scale']:.4f}")
    print(f"Kirschstein extra_cubic_k: {kirschstein_params['extra_cubic_k']:.8f}")

    print(f"\n{residual_heading}")
    for obs in observations:
        print(f"  {obs['label']} hedef: v={obs['speed_ms']:.2f}, P/Ph={obs['power_ratio']:.4f}")
        for name, ratio_fn in model_functions.items():
            predicted = ratio_fn(obs["speed_ms"])
            print(f"    {name}: fit={predicted:.4f}, err={predicted - obs['power_ratio']:+.4f}")

    if voltage_anchor:
        print("\n6 m/s voltaj anchor residual'lari:")
        for name, ratio_fn in model_functions.items():
            predicted = ratio_fn(voltage_anchor["speed_ms"])
            print(f"  {name}: fit={predicted:.4f}, "
                  f"target={voltage_anchor['power_ratio']:.4f}, "
                  f"err={predicted - voltage_anchor['power_ratio']:+.4f}")

    for model_name, ratio_fn in model_functions.items():
        rows = [
            calculate_flight_for_speed(speed, ratio_fn(speed),
                                       hover_power_w, battery_wh, correction_factor)
            for speed in speeds
        ]
        print_speed_table(model_name, rows)

    if make_graph:
        extra_points = []
        if voltage_anchor:
            extra_points.append({
                "speed_ms": voltage_anchor["speed_ms"],
                "power_ratio": voltage_anchor["power_ratio"],
                "marker": "X",
                "color": "purple",
                "label": "stadium voltage anchor",
            })
        for obs in datalink_observations:
            extra_points.append({
                "speed_ms": obs["speed_ms"],
                "power_ratio": obs["power_ratio"],
                "marker": "^",
                "color": "blue",
                "label": obs["label"],
            })
        try:
            range_path = plot_range_time_vs_speed(
                model_functions,
                hover_power_w,
                battery_wh,
                correction_factor,
                output_path=range_output_path,
            )
            power_path = plot_power_ratio_vs_speed(
                model_functions,
                v_endurance,
                v_range,
                profile.get("pitch_measurement_speed_ms"),
                profile.get("pitch_measurement_deg"),
                output_path=power_output_path,
                extra_points=extra_points,
                show_bauersfeld_points=show_bauersfeld_points,
            )
            print("\nBagimsiz karsilastirma grafik ciktilari:")
            print(f"* {range_path}")
            print(f"* {power_path}")
            import matplotlib.pyplot as plt
            print("plt.show() cagriliyor.")
            plt.show()
        except Exception as exc:
            print(f"Bagimsiz karsilastirma grafigi olusturulamadi: {exc}")

    return {
        "fit_mode": fit_mode,
        "profile": profile,
        "model_functions": model_functions,
        "observations": observations,
        "datalink_result": datalink_result,
        "attitude_fit": attitude_fit,
        "faessler_fit": faessler_fit,
        "voltage_anchor": voltage_anchor,
        "zeng_params": zeng_params,
        "faessler_params": faessler_params,
        "kirschstein_params": kirschstein_params,
        "range_output_path": range_output_path,
        "power_output_path": power_output_path,
    }


def calculate_real_energy_wh(total_cells, capacity_mah, battery_type='lihv'):
    if battery_type == 'lihv':
        nominal_voltage = 3.7 * (7.0 / 6.0)
    elif battery_type == 'lipo':
        # LiPo ile LiHV arasında 7/6 kat fark varsayımı
        nominal_voltage = 3.7
    elif battery_type == 'liion':
        # Bu projedeki solid-state Li-ion paket 4.3V'a sarj ediliyor ve nominal 3.7V kabul ediliyor.
        nominal_voltage = 3.7
    else:
        nominal_voltage = 3.7
    return total_cells * nominal_voltage * (capacity_mah / 1000.0)


def drone_simulasyon():
    print("\n--- DRONE UÇUŞ SÜRESİ HESAPLAYICISI ---")

    # [ADIM 1] REFERANS (VIBE - P80)
    ref_agirlik = 19500
    ref_thrust_per_motor = ref_agirlik / 4.0
    ref_total_cells = 24  # 4x 6S
    ref_mah = 17000

    ref_energy_wh = calculate_real_energy_wh(ref_total_cells, ref_mah, 'lihv')
    ref_motor_power = get_power_from_thrust(ref_thrust_per_motor, p80_thrust_power)
    ref_total_power = ref_motor_power * 4
    ref_teorik_sure = (ref_energy_wh / ref_total_power) * 60

    # Referans değerler ve Standart CF hesabı
    ref_gercek_sure = 35.0
    standart_cf = ref_gercek_sure / ref_teorik_sure

    # [ADIM 2] MOD SEÇİMİ
    print("\n--- MOD SEÇİMİ ---")
    print("1) Standart CF ile hesaplama")
    print("2) Özel CF ile hesaplama")
    print("3) Tersine Hesaplama (Hover Süresinden Güç Bulma)")

    mod_secim = input("Seçiminiz (1-3): ").strip()

    is_reverse_mode = False

    if mod_secim == "2":
        while True:
            try:
                cf_input = float(input("Özel CF değerini giriniz (0.0 - 1.0 arası): "))
                if 0.0 <= cf_input <= 1.0:
                    correction_factor = cf_input
                    print(f"--> Correction Factor: {correction_factor} olarak ayarlandı.")
                    break
                else:
                    print("Lütfen 0 ile 1 arasında bir değer giriniz.")
            except ValueError:
                print("Geçersiz değer. Lütfen sayı giriniz.")

    elif mod_secim == "3":
        is_reverse_mode = True
        correction_factor = 1.0  # Placeholder, will be calculated in loop
        print("--> Tersine Hesaplama Modu Seçildi.")
        print("--> Bu modda gireceğiniz 'Hover Süresi' baz alınarak motor güç tüketimi hesaplanacaktır.")

    else:
        correction_factor = standart_cf
        print(f"--> Standart mod seçildi. Hesaplanan Standart CF: {correction_factor:.4f}")

    print(f"\n[REFERANS] Vibe Analizi (P80 Motor):")
    print(f"   * Teorik Süre: {ref_teorik_sure:.2f} dk")
    print(f"   * Gerçek Süre: {ref_gercek_sure} dk")
    if not is_reverse_mode:
        print(f"   * Correction Factor: {correction_factor:.4f} (Gerçeklik Çarpanı)")

    # YENİ DRONE TASARIMI
    while True:
        print("\n--- GÖVDE TİPİ ---")
        print("1. Quadcopter (4 Motor)")
        print("2. Hexacopter (6 Motor)")
        print("3. Octacopter Coaxial (8 Motor)")
        govde_secim = input("Gövde Tipi Seçimi (1-3): ").strip()

        coaxial_loss_factor = 1.0

        # Eğer kullanıcı 2'yi seçerse 6, 3'ü seçerse 8, diğer her durumda 4 yap
        if govde_secim == "2":
            motor_sayisi = 6
        elif govde_secim == "3":
            motor_sayisi = 8
            while True:
                try:
                    loss_input = float(input("Coaxial Verim Kaybı Katsayısı (0.0 - 1.0 arası, örn: 0.7): "))
                    if 0.0 <= loss_input <= 1.0:
                        coaxial_loss_factor = loss_input
                        print(f"--> Coaxial Kayıp Katsayısı: {coaxial_loss_factor} olarak ayarlandı.")
                        break
                    else:
                        print("Lütfen 0 ile 1 arasında bir değer giriniz.")
                except ValueError:
                    print("Geçersiz değer. Lütfen sayı giriniz.")
        else:
            motor_sayisi = 4

        print(f"--> Hesaplama {motor_sayisi} motor üzerinden yapılacak.\n")
        # ----------------------------------------------------
        print("\n" + "=" * 60)
        try:
            print("Motor Seçimi:")
            print("--- SUAS Motorları ---")
            print("0. T-MOTOR P80 KV100 + MF3218 (12S)")
            print("1. MN7005 KV115 24 Pervane " "(Hacim kuralını karşılıyor)")
            print("2. CM-X6-SE 380KV Technical Parameters HF18*6.0\" - (Hacim kuralını karşılıyor)")
            print("3. CM-X6-SE HF22*7.0\" (Hacim kuralını karşılıyor)")
            print("4. M5208 HP/UL 21x6.3 (Hacim kuralını karşılıyor)")
            print("5. MN7005 KV230 P24x7.2 (Hacim kuralını karşılıyor)")
            print("6. U8 Lite KV150 + G29*9.5")
            print("7. M8108 Light 150KV + MSC 28x9.2")
            print("8. M6208 155KV + MSC 21x6.3 (Hacim kuralını karşılıyor)")
            print("9. M8108 Light 150KV + MSC 29x9.5")
            print("10. MN601S KV170 + P21x6.3 (Hacim kuralını karşılıyor)")
            print("11. U10II KV100 (8S) + G32x11\"")
            print("12. U10II KV100 (8S) + G30x10.5\" ")
            print("13. MN6007 II KV320 + P22x6.6\"")
            print("14. MN6007 II KV160 + P21x6.3\"")
            print("15. U8 Lite KV150 + G30x10.5\"")
            print("16. U8 Lite KV190 + G29x9.5\"")
            print("17. U8 Lite KV190 + G28x9.2\"")
            print("18. U8II KV85 + G28x9.2\"")
            print("19. T-MOTOR P60 KV170 + P22x6.6 (12S)")
            print("20. U10II KV100 (12S) + G28x9.2\" ")
            print("21. U8 Lite KV150 (6S) + G29x9.5\" ")
            print("22. U8II-X KV100 (12S) + MF2815 ")
            print("--- Yıldızlar Motorları ---")
            print("23. Yıldızlar 24V (6S LIPO) + HQ9x5x3 (İyi Motor)")
            print("24. Yıldızlar SE 3115 900KV + HQ9x5x3 (6S) (Kötü Motor)")
            print("25. Yıldızlar Geçen Sene + DAL T5045")
            print("27. Yıldızlar Sanal Ortalama (İyi & Kötü Motor)")

            m_secim = input("Seçiminiz (0-27): ").strip()

            required_s = 6
            use_quadratic = False

            if m_secim == "0":
                data, m_name, secilen_prop_inc = mf3218_data, "T-MOTOR P80 KV100 + MF3218 (12S)", 32.0
                required_s = 12
            elif m_secim == "1":
                data, m_name, secilen_prop_inc = mn7005_thrust_power, "MN7005 KV115 (Hacim kuralını karşılıyor)", 24.0
            elif m_secim == "2":
                data, m_name, secilen_prop_inc = cmx6_old_thrust_power, "CM-X6-SE 380KV Technical Parameters HF18*6.0\" -  (Hacim kuralını karşılıyor)", 18.0
            elif m_secim == "3":
                data, m_name, secilen_prop_inc = cmx6_tech_thrust_power, "CM-X6-SE HF22*7.0\" (Hacim kuralını karşılıyor)", 22.0
            elif m_secim == "4":
                data, m_name, secilen_prop_inc = m5208_thrust_power, "M5208 HP/UL (Hacim kuralını karşılıyor)", 21.0
            elif m_secim == "5":
                data, m_name, secilen_prop_inc = mn7005_kv230_thrust_power, "MN7005 KV230 (Hacim kuralını karşılıyor)", 24.0
            elif m_secim == "6":
                data, m_name, secilen_prop_inc = u8lite_kv150_thrust_power, "U8 Lite KV150 + G29*9.5\" (Hacim kuralını karşılamıyor)", 29.0
            elif m_secim == "7":
                data, m_name, secilen_prop_inc = m8108_light_data, "M8108 Light 150KV + MSC 28x9.2 (Hacim kuralını karşılamıyor)", 28.0
            elif m_secim == "8":
                data, m_name, secilen_prop_inc = m6208_12s_data, "M6208 155KV + MSC 21x6.3 (Hacim kuralını karşılıyor)", 21.0
            elif m_secim == "9":
                data, m_name, secilen_prop_inc = m8108_light_29in_data, "M8108 Light 150KV + MSC 29x9.5 (Hacim kuralını karşılamıyor)", 29.0
            elif m_secim == "10":
                data, m_name, secilen_prop_inc = mn601s_kv170_data, "MN601S KV170 + P21x6.3 (Hacim kuralını karşılıyor)", 21.0
            elif m_secim == "11":
                data, m_name, secilen_prop_inc = u10ii_kv100_data, "U10II KV100 (8S) (Hacim kuralını karşılamıyor)", 32.0
                required_s = 8
            elif m_secim == "12":
                data, m_name, secilen_prop_inc = u10ii_kv100_30in_data, "U10II KV100 (8S) + G30x10.5\"", 30.0
                required_s = 8
            elif m_secim == "13":
                data, m_name, secilen_prop_inc = mn6007ii_kv320_data, "MN6007 II KV320", 22.0
            elif m_secim == "14":
                data, m_name, secilen_prop_inc = mn6007ii_kv160_data, "MN6007 II KV160", 21.0
            elif m_secim == "15":
                data, m_name, secilen_prop_inc = u8lite_kv150_g30_data, "U8 Lite KV150 + G30x10.5\"", 30.0
            elif m_secim == "16":
                data, m_name, secilen_prop_inc = u8lite_kv190_g29_data, "U8 Lite KV190 + G29x9.5\"", 29.0
            elif m_secim == "17":
                data, m_name, secilen_prop_inc = u8lite_kv190_data, "U8 Lite KV190 + G28x9.2\"", 28.0
            elif m_secim == "18":
                data, m_name, secilen_prop_inc = u8ii_kv85_data, "U8II KV85 + G28x9.2\"", 28.0
            elif m_secim == "19":
                data, m_name, secilen_prop_inc = p60_kv170_data, "T-MOTOR P60 KV170 + P22x6.6 (12S)", 22.0
                required_s = 12
            elif m_secim == "20":
                data, m_name, secilen_prop_inc = u10ii_kv100_new_data, "U10II KV100 (12S) + G28x9.2\" (YENİ)", 28.0
                required_s = 12
            elif m_secim == "21":
                data, m_name, secilen_prop_inc = u8lite_kv150_new_data, "U8 Lite KV150 (6S) + G29x9.5\" (YENİ)", 29.0
                required_s = 6
            elif m_secim == "22":
                data, m_name, secilen_prop_inc = u8iix_kv100_data, "U8II-X KV100 (12S) + MF2815 (YENİ)", 28.0
                required_s = 12
            elif m_secim == "23":
                data, m_name, secilen_prop_inc = yildizlar_iyi_motor_data, "Yıldızlar 24V (6S LIPO) + HQ9x5x3 (İyi Motor)", 9.0
                required_s = 6
                use_quadratic = True
            elif m_secim == "24":
                data, m_name, secilen_prop_inc = yildizlar_kotu_motor_data, "Yıldızlar SE 3115 900KV + HQ9x5x3 (6S) (Kötü Motor)", 9.0
                required_s = 6
                use_quadratic = True
            elif m_secim == "25":
                data, m_name, secilen_prop_inc = yildizlar_gecen_sene_data, "Yıldızlar Geçen Sene + DAL T5045", 5.0
                required_s = 4
                use_quadratic = True
            elif m_secim == "27":
                data, m_name, secilen_prop_inc = yildizlar_sanal_ortalama_data, "Yıldızlar Sanal Ortalama (İyi & Kötü Motor)", 9.0
                required_s = 6
                use_quadratic = True
            else:
                print("Geçersiz seçim. Varsayılan (1) seçildi.")
                data, m_name, secilen_prop_inc = mn7005_thrust_power, "MN7005 KV115 (Hacim kuralını karşılıyor)", 24.0

            # --- COAXIAL KAYIP KATSAYISINI UYGULA ---
            if coaxial_loss_factor < 1.0:
                # Verileri kopyalayarak modifiye et (Global listeyi bozmamak için)
                # Thrust değerlerini katsayı ile çarp, güç değerlerini sabit bırak
                data = [[row[0] * coaxial_loss_factor, row[1]] for row in data]
                print(f"   [BİLGİ] Coaxial katsayısı ({coaxial_loss_factor}) datasheet verilerine uygulandı.")

            yeni_agirlik = float(input("\nYeni drone ağırlığı (kg)? ")) * 1000

            print("Batarya Bilgileri:")
            bat_tipi = input("   Tip (LiHV/LiPo/LiIon): ").lower()
            if bat_tipi not in ['lihv', 'lipo', 'liion']: bat_tipi = 'lipo'

            p_adet = float(input("   Kaç adet pil (paralel/seri toplam)? "))
            p_mah = float(input("   Tek pil mAh? "))
            p_s = int(input("   Tek pil S değeri (örn: 6, 4, 8)? "))

            if required_s % p_s != 0:
                print("\n" + "!" * 65)
                print(f" [HATA] UYUMSUZ PİL SEÇİMİ!")
                print(f" Seçilen Motor: {required_s}S gerilim istiyor.")
                print(f" Elinizdeki Pil: {p_s}S.")
                print(f" Matematiksel olarak {p_s}S pilleri seri bağlayarak {required_s}S ELDE EDEMEZSİNİZ.")
                print(f" Lütfen {required_s}'in tam böleni olan bir pil kullanın.")
                print("!" * 65 + "\n")
                continue  # Hata verip en başa (menüye) döner

            toplam_hucre = p_adet * p_s
            sistem_voltaji_s = p_s * (1 if p_adet > 1 else 1)

            # Voltaj Uyarısı
            # Kullanıcı 6s motora 8s falan takmaya çalışırsa nazikçe uyaralım
            if (
                    m_secim == "2" or m_secim == "3" or m_secim == "4" or m_secim == "5" or m_secim == "6" or m_secim == "7" or m_secim == "9" or m_secim == "13" or m_secim == "15" or m_secim == "16" or m_secim == "17") and (
                    toplam_hucre / p_adet) > 6:                print(
                "   [!] DİKKAT: Seçilen motor verileri düşük voltaj (6S vb.) içindir. 12S sistem planlıyorsanız KV değerini kontrol edin!")

            # Enerji ve Güç Hesabı
            yeni_enerji = calculate_real_energy_wh(toplam_hucre, p_mah, bat_tipi)
            yeni_thrust = yeni_agirlik / float(motor_sayisi)
            # Limit Kontrolü
            max_thrust = data[-1][0]
            if yeni_thrust > max_thrust:
                print(f"   [!] UYARI: Gereken itki ({yeni_thrust:.0f}g), motor limitini ({max_thrust}g) aşıyor!")

            if use_quadratic:
                yeni_power_motor = get_power_from_thrust_quadratic(yeni_thrust, data)
                if yeni_thrust < data[0][0] or yeni_thrust > data[-1][0]:
                    print(f"   [BİLGİ] İstenen itki veri aralığı ({data[0][0]}g - {data[-1][0]}g) dışında. Kuadratik regresyon ile ekstrapolasyon kullanıldı.")
                else:
                    print(f"   [BİLGİ] İstenen itki veri aralığı ({data[0][0]}g - {data[-1][0]}g) içinde. Lineer interpolasyon kullanıldı.")
            else:
                yeni_power_motor = get_power_from_thrust(yeni_thrust, data)
            yeni_total_power = yeni_power_motor * motor_sayisi

            # TEORİK SÜRE HESABI (%100 Enerji Tüketimi İçin)
            teorik_sure = (yeni_enerji / yeni_total_power) * 60

            if is_reverse_mode:
                # --- MOD 3: TERSİNE HESAPLAMA (Correction Factor Derivation) ---
                print("\n" + "*" * 60)
                try:
                    hover_input = float(input("Hedeflenen/Gerçekleşen Hover Süresi (%20 Batarya Kalana Kadar) [dk]: "))
                    if hover_input <= 0:
                        print("Süre 0'dan büyük olmalı! 20 dk varsayılıyor.")
                        hover_input = 20.0
                except ValueError:
                    hover_input = 20.0
                    print("Geçersiz değer, 20 dk varsayılıyor.")

                correction_factor = hover_input / teorik_sure

                print(f"--> Girilen Süre: {hover_input} dk")
                print(f"--> Teorik Süre (Datasheet): {teorik_sure:.2f} dk")
                print(f"--> HESAPLANAN CORRECTION FACTOR: {correction_factor:.4f}")
                print("*" * 60 + "\n")

            else:
                # Klasik modlarda CF zaten başta seçilmişti (Standard veya Custom)
                pass

            # 1. Standart Süre (Vibe gibi %20 Rezerv)
            tahmini_standart = teorik_sure * correction_factor

            # 2. Yarışma Modu (Agresif %10 Rezerv)
            tahmini_yarisma = tahmini_standart * 1.125

            # 3. Çok Güvenli Mod (%25 Rezerv -> %75 Kullanım)
            # Standart süre %80 kullanım (20% rezerv) olduğu için:
            # 80 birim = standart_sure ise, 75 birim = ?
            tahmini_cok_guvenli = tahmini_standart * (75.0 / 80.0)

            print("-" * 50)
            print(f"SONUÇLAR ({m_name} | {yeni_agirlik / 1000} kg):")
            print(f"   * Motor Başı Güç: {yeni_power_motor:.1f} W (Toplam: {yeni_total_power:.1f} W)")
            print(f"   * Ham Teorik Süre: {teorik_sure:.1f} dk")
            print(f"   * Hesaplanan CF Değeri: {correction_factor:.4f}")
            print("-" * 50)
            print(f"   [ÇOK GÜVENLİ] Tahmini Süre (%25 Rezerv):   **{tahmini_cok_guvenli:.2f} dk**")
            print(f"   [GÜVENLİ]     Tahmini Süre (%20 Rezerv):   **{tahmini_standart:.2f} dk**")
            print(f"   [YARIŞMA]     Tahmini Süre (%10 Rezerv):   **{tahmini_yarisma:.2f} dk**")
            print("-" * 50)

            if m_secim == "25":
                hedef = 10.0
            elif m_secim in ["23", "24", "27"]:
                hedef = 15.0
            else:
                hedef = 40.0
            
            print(f"   [HEDEF SÜRE]   Sistemin hedef uçuş süresi: **{hedef} dk**")
            print("-" * 50)

            # ÖNCE Güvenli modu kontrol et
            if tahmini_standart >= hedef:
                print(f"YORUM: MÜKEMMEL. Güvenli modda bile {hedef} dk hedefini geçiyorsunuz.")
            # Eğer güvenli yetmediyse, Yarışma modunu kontrol et
            elif tahmini_yarisma >= hedef:
                print(f"YORUM: BAŞARILI. Sadece yarışma modunda {hedef} dk hedefini geçiyorsunuz.")
            else:
                fark = hedef - tahmini_yarisma
                print(f"YORUM: Pili %10'a kadar bitirseniz bile {hedef} dk hedefine {fark:.1f} dk eksiğiniz var.")

            # --- MENZİL HESABI EKLEMESİ ---
            try:
                drag_input = input("\nDrone Rüzgar Yiyen Alanı (cm2) [Varsayılan 2000]: ")
                drag_area = float(drag_input) if drag_input.strip() else 2000.0


            except ValueError:
                drag_area = 2000.0
                print("Geçersiz değer, varsayılan 2000 cm2 kullanılıyor.")

            bauersfeld = BauersfeldMenzilHesaplayici(
                hover_power_w=yeni_total_power,  # Senin koddan gelen
                correction_factor=correction_factor,  # Senin koddan gelen
                battery_wh=yeni_enerji,  # Senin hesapladığın enerji
                total_mass_kg=yeni_agirlik / 1000.0,
                drag_area_cm2=drag_area,  # Senin girdin
                prop_diameter_inch=secilen_prop_inc,
                num_rotors=motor_sayisi
            )

            sonuc = bauersfeld.solve()

            print("\n" + "=" * 50)
            print("%20 ÜZERİNDEN BAUERSFELD (2022) ALGORİTMASI SONUÇLARI")
            print("=" * 50)
            print(f"Referans İndüklenen Hız (vi,h): {sonuc['vi_h']:.2f} m/s")
            print("-" * 50)
            print(f"MAKSİMUM MENZİL SENARYOSU:")
            print(
                f"  * Optimal Hız:       {sonuc['optimal_speed_ms']:.2f} m/s ({sonuc['optimal_speed_ms'] * 3.6:.1f} km/h)")
            print(f"  * Tahmini Güç:       {sonuc['power_range_w']:.1f} W (Hover x 1.092)")
            print(f"  * Uçuş Süresi:       {sonuc['flight_time_min_range']:.1f} dk")
            print(f"  * MAKSİMUM MENZİL:   {sonuc['max_range_km']:.2f} km")
            print("-" * 50)
            print(f"MAKSİMUM HAVADA KALMA (ENDURANCE) SENARYOSU:")
            print(f"  * Optimal Hız:       {sonuc['optimal_endurance_speed_ms']:.2f} m/s (İleri sürüklenme)")
            print(f"  * Tahmini Güç:       {sonuc['power_endurance_w']:.1f} W (Hover x 0.914)")
            print(f"  * Uçuş Süresi:       {sonuc['max_endurance_min']:.1f} dk")
            print(f"  * TAHMİNİ MENZİL:    {sonuc['max_range_km_endurance']:.2f} km")
            print("=" * 50)

            print("\n" + "=" * 50)
            print("%10 ÜZERİNDEN (YARIŞMA MODU) SONUÇLARI")
            print("=" * 50)
            print(f"MAKSİMUM MENZİL SENARYOSU:")
            print(f"  * Uçuş Süresi:       {sonuc['flight_time_min_range'] * 1.125:.1f} dk")
            print(f"  * MAKSİMUM MENZİL:   {sonuc['max_range_km'] * 1.125:.2f} km")
            print("-" * 50)
            print(f"MAKSİMUM HAVADA KALMA (ENDURANCE) SENARYOSU:")
            print(f"  * Uçuş Süresi:       {sonuc['max_endurance_min'] * 1.125:.1f} dk")
            print(f"  * TAHMİNİ MENZİL:    {sonuc['max_range_km_endurance'] * 1.125:.2f} km")
            print("=" * 50)

        except ValueError:
            print("Sayısal hata. Lütfen sayı giriniz.")

        # --- KULLANICI ETKİLEŞİMLİ SEÇENEK ---
        print("\nNe yapmak istersiniz?")
        print("   [Enter] Yeni Hesaplama Yap")
        print("   (3)     Belirli Hız(lar) için Bauersfeld / Zeng / Parabol model analizi")
        print("   (4)     Bagimsiz model karsilastirmasi")
        print("   (q)     Çıkış")
        
        son_secim = input("Seçiminiz: ").strip().lower()

        if son_secim == 'q':
            break
        elif son_secim == '3':
            try:
                print("\n--- ÖZEL HIZ MODEL ANALİZİ ---")
                raw_speeds = input("Uçuş hızı/hızları (m/s, virgülle; örn 6,10,15,20) [20]: ").strip()
                speeds = parse_speed_list(raw_speeds) if raw_speeds else [20.0]
                if not speeds:
                    raise ValueError("En az bir hız girilmeli.")

                print("\nAraç profili:")
                print("1) Fırfır preset")
                print("   12.4 kg, 4 rotor, U8 Lite KV190 6S + T-MOTOR G29x9.5 CF, Utip=80 m/s.")
                print("2) Yeni drone / mevcut girişlerden manual")
                vehicle_choice = input("Araç profili seçimi (1/2) [1]: ").strip() or "1"
                if vehicle_choice not in {"1", "2"}:
                    vehicle_choice = "1"

                print_model_descriptions()
                model_choice = input("Model se\u00e7imi (virg\u00fclle; \u00f6rn 2,4,5) [4]: ").strip() or "4"
                selected_preview = parse_model_selection(model_choice)
                print("Se\u00e7ilen modeller: " + ", ".join(selected_preview))
                datalink_log_root = None
                datalink_date_hint = DATALINK_MEASURED_CURVE_DATE_HINT
                if "datalink_empirical_pv" in selected_preview:
                    root_raw = input(
                        "DataLink empirical log klasoru [otomatik: 3 Temmuz Tum Test Loglari]: "
                    ).strip()
                    datalink_log_root = Path(root_raw) if root_raw else None
                    date_hint_raw = input("DataLink tarih hint'i (YYMMDD) [260703]: ").strip()
                    datalink_date_hint = (
                        normalize_datalink_date_hint(date_hint_raw)
                        or DATALINK_MEASURED_CURVE_DATE_HINT
                    )

                require_theoretical = model_selection_requires_theoretical(model_choice)
                profile = build_speed_model_profile(
                    vehicle_choice,
                    yeni_agirlik / 1000.0,
                    motor_sayisi,
                    secilen_prop_inc,
                    drag_area,
                    require_theoretical=require_theoretical,
                )

                graph_raw = input("Se\u00e7ilen modeller i\u00e7in grafik olu\u015fturulsun mu? (e/h) [h]: ").strip().lower()
                make_graph = graph_raw == "e"

                run_custom_speed_models(
                    speeds,
                    profile,
                    model_choice,
                    sonuc,
                    yeni_total_power,
                    yeni_enerji,
                    correction_factor,
                    make_graph,
                    datalink_log_root=datalink_log_root,
                    datalink_date_hint=datalink_date_hint,
                )

                print("\nSonraki adım:")
                print("   [Enter / 1] Ana menüye dön")
                print("   (q / 2)     Çıkış")
                sonraki_adim = input("Seçiminiz: ").strip().lower()
                if sonraki_adim in {"q", "2", "c", "ç", "exit"}:
                    break

            except ValueError:
                print("Lütfen geçerli sayısal değerler giriniz!")
            except Exception as exc:
                print(f"Özel hız model analizi çalıştırılamadı: {exc}")
        elif son_secim == '4':
            try:
                print("\n--- BAGIMSIZ MODEL KARSILASTIRMASI ---")
                raw_speeds = input("Karsilastirma hizlari (m/s, virgul; orn 6,10,15,20,25) [6,10,15,20,25]: ").strip()
                speeds = parse_speed_list(raw_speeds) if raw_speeds else [6.0, 10.0, 15.0, 20.0, 25.0]
                if not speeds:
                    raise ValueError("En az bir hiz girilmeli.")

                print("\nArac profili:")
                print("1) Firfir preset")
                print("   12.4 kg, 4 rotor, U8 Lite KV190 6S + T-MOTOR G29x9.5 CF.")
                print("   DataLink modunda Utip RPM'den guncellenir; DataLink yoksa legacy fallback kullanilir.")
                print("2) Yeni drone / mevcut girislerden manual")
                vehicle_choice = input("Arac profili secimi (1/2) [1]: ").strip() or "1"
                if vehicle_choice not in {"1", "2"}:
                    vehicle_choice = "1"

                profile = build_speed_model_profile(
                    vehicle_choice,
                    yeni_agirlik / 1000.0,
                    motor_sayisi,
                    secilen_prop_inc,
                    drag_area,
                    require_theoretical=False,
                )

                print("\nKarsilastirma modu:")
                print("1) All-data fit: log + stadyum batarya + Bauersfeld")
                print("2) Deneysel-only fit: log + stadyum batarya, Bauersfeld yok")
                print("3) DataLink all-data: DataLink + log + stadyum + Bauersfeld")
                print("4) DataLink deneysel-only: DataLink + log + stadyum, Bauersfeld yok")
                fit_mode_choice = input("Mod secimi (1/2/3/4) [1]: ").strip() or "1"
                if fit_mode_choice == "2":
                    fit_mode = "experimental_only"
                elif fit_mode_choice == "3":
                    fit_mode = "datalink_all_data"
                elif fit_mode_choice == "4":
                    fit_mode = "datalink_experimental_only"
                else:
                    fit_mode = "all_data_with_bauersfeld"

                if fit_mode.startswith("datalink"):
                    date_hint_raw = input(
                        "DataLink tarih hint'i (YYMMDD; orn 260624, bos=otomatik): "
                    ).strip()
                    date_hint = normalize_datalink_date_hint(date_hint_raw)
                    if date_hint:
                        profile["datalink_session_date_hint"] = date_hint
                        print(f"DataLink sadece UART-{date_hint} oturumlarindan aranacak.")
                    elif date_hint_raw:
                        print("Tarih hint'i anlasilamadi; otomatik DataLink aramasi kullanilacak.")

                graph_raw = input("Bagimsiz karsilastirma grafigi olusturulsun mu? (e/h) [e]: ").strip().lower()
                make_graph = graph_raw != "h"

                run_independent_model_comparison(
                    speeds,
                    profile,
                    sonuc,
                    yeni_total_power,
                    yeni_enerji,
                    correction_factor,
                    make_graph,
                    fit_mode,
                )

                print("\nSonraki adim:")
                print("   [Enter / 1] Ana menuye don")
                print("   (q / 2)     Cikis")
                sonraki_adim = input("Seciminiz: ").strip().lower()
                if sonraki_adim in {"q", "2", "c", "exit"}:
                    break

            except ValueError:
                print("Lutfen gecerli sayisal degerler giriniz!")
            except Exception as exc:
                print(f"Bagimsiz model karsilastirmasi calistirilamadi: {exc}")

if __name__ == "__main__":
    drone_simulasyon()
