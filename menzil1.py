# TARIK ZİYA İNCİ VE FURKAN DEMİRYÜREK TARAFINDAN ÖZENLE HAZIRLANDI

import math


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

        # --- ADIM 1: Hover İndüklenen Hız (vi,h) ---
        # Eq 4: vi,h = sqrt(mg / 2*rho*pi*r^2*Nr)
        numerator = self.m * self.g
        denominator = 2 * self.rho * math.pi * (self.r_prop ** 2) * self.Nr
        self.vi_h = math.sqrt(numerator / denominator)

        # --- KATSAYILAR (Tablo II)  ---
        # Range (Menzil) Katsayıları
        self.c0_r = 0.041546
        self.c1_r = 0.041122
        self.c2_r = 0.00053292

        # Endurance (Dayanım) Katsayıları
        self.c0_e = 0.10188
        self.c1_e = 0.071358
        self.c2_e = 0.0007381

    def solve(self):
        # --- ADIM 2: Optimal Hızları Hesapla (Eq 18)  ---
        # Formül: v_opt = vi,h / (c0 + c1*vi,h + c2*A)

        # 1. Maksimum Menzil Hızı (v_range)
        denom_r = self.c0_r + (self.c1_r * self.vi_h) + (self.c2_r * self.A_ref)
        v_range_ms = self.vi_h / denom_r

        # 2. Maksimum Dayanım Hızı (v_endurance) - (Genelde hover'dan biraz hızlıdır)
        denom_e = self.c0_e + (self.c1_e * self.vi_h) + (self.c2_e * self.A_ref)
        v_endurance_ms = self.vi_h / denom_e

        # --- ADIM 3: Güç Tüketimlerini Hesapla (Eq 17)  ---
        # Makale diyor ki:
        # P_range = 1.092 * P_hover
        # P_endurance = 0.914 * P_hover

        # Burada ölçülen P_hover'ı baz alıyoruz (Correction Factor uygulanmamış ham güç)
        P_range_w = 1.092 * self.P_h_measured
        P_endurance_w = 0.914 * self.P_h_measured

        # --- ADIM 4: Süre ve Menzil Hesabı ---
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


# --- VERİ SETLERİ (DATASHEETS) ---

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



def calculate_real_energy_wh(total_cells, capacity_mah, battery_type='lihv'):
    if battery_type == 'lihv':
        nominal_voltage = 3.7 * (7.0 / 6.0)
    elif battery_type == 'lipo':
        # LiPo ile LiHV arasında 7/6 kat fark varsayımı
        nominal_voltage = 3.7
    elif battery_type == 'liion':
        nominal_voltage = 3.6
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

    # [ADIM 3] YENİ DRONE TASARIMI
    while True:
        # --- BURAYI EKLE (While döngüsünün hemen içine) ---
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
        print("   (3)     Belirli Hız ve Güç Çarpanı ile Menzil Hesapla")
        print("   (q)     Çıkış")
        
        son_secim = input("Seçiminiz: ").strip().lower()

        if son_secim == 'q':
            break
        elif son_secim == '3':
            try:
                print("\n--- ÖZEL HIZ ve POLİNOM GÜÇ ANALİZİ ---")
                
                # Mevcut optimum hızları al
                v_opt_range = sonuc['optimal_speed_ms']
                v_opt_endurance = sonuc['optimal_endurance_speed_ms']
                
                # Katsayıları hesapla
                pa, pb = calculate_poly_coeffs(v_opt_endurance, v_opt_range)
                
                hiz_ms = float(input("Uçuş Hızı (m/s): "))
                
                # Polinomdan güç katsayısını bul: ax^2 + bx + 1
                guc_katsayisi = (pa * (hiz_ms ** 2)) + (pb * hiz_ms) + 1.0
                
                print(f"   -> Hesaplanan Güç Çarpanı: {guc_katsayisi:.4f} kat P (Polinom)")

                # 1. Güç Tüketimi
                tuketilen_guc = yeni_total_power * guc_katsayisi
                
                # 2. %100 Teorik Kapasite Süresi (Hiçbir kayıp olmadan)
                # (Enerji Wh / Güç W) * 60 -> Dakika
                teorik_100_dk = (yeni_enerji / tuketilen_guc) * 60
                
                # %20 Rezerv (CF = batarya rezervi + gerçek dünya kayıpları)
                ucus_suresi_dk_20 = teorik_100_dk * correction_factor
                menzil_km_20 = (hiz_ms * 3.6) * (ucus_suresi_dk_20 / 60.0)
                
                # %10 Rezerv (CF üzerinden 1.125 oranı)
                ucus_suresi_dk_10 = ucus_suresi_dk_20 * 1.125
                menzil_km_10 = (hiz_ms * 3.6) * (ucus_suresi_dk_10 / 60.0)

                print(f"\nSONUÇLAR ({hiz_ms} m/s @ {guc_katsayisi}x Hover Gücü):")
                print(f"   * %100 Teorik Süre: {teorik_100_dk:.2f} dk")
                print("-" * 50)
                print(f"[%20 REZERV] (Standart - %80 Kullanım)")
                print(f"   * Uçuş Süresi: {ucus_suresi_dk_20:.2f} dk")
                print(f"   * Menzil:      {menzil_km_20:.2f} km")
                print("-" * 50)
                print(f"[%10 REZERV] (Yarışma - %90 Kullanım)")
                print(f"   * Uçuş Süresi: {ucus_suresi_dk_10:.2f} dk")
                print(f"   * Menzil:      {menzil_km_10:.2f} km")
                print("-" * 50)
                
                input("\nAna menüye dönmek için Enter'a basınız...")

            except ValueError:
                print("Lütfen geçerli sayısal değerler giriniz!")


if __name__ == "__main__":
    drone_simulasyon()

