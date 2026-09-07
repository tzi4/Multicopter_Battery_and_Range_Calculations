"""Multicopter battery-endurance and forward-flight range models.

The module combines a Bauersfeld-based calculator with parsers and fitted
models for the calibration flight data shipped in ``data/calibration``.
"""

import argparse
import csv
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class BauersfeldRangeCalculator:
    def __init__(
        self,
        hover_power_w,  # Hover power
        correction_factor,  # Correction Factor
        battery_wh,  # Battery energy
        total_mass_kg,  # Total mass
        drag_area_cm2,  # A (surface area in the paper)
        prop_diameter_inch,  # Propeller diameter
        num_rotors,
    ):  # Rotor count

        self.P_h_measured = hover_power_w
        self.cf = correction_factor
        self.energy_wh = battery_wh
        self.m = total_mass_kg
        self.A_ref = drag_area_cm2  # The paper's coefficients use cm^2.
        self.Nr = num_rotors

        # Physical constants
        self.g = 9.81
        self.rho = 1.225

        self.r_prop = (prop_diameter_inch * 0.0254) / 2.0

        # Induced hover velocity (vi,h)
        # Eq 4: vi,h = sqrt(mg / 2*rho*pi*r^2*Nr)
        numerator = self.m * self.g
        denominator = 2 * self.rho * math.pi * (self.r_prop**2) * self.Nr
        self.vi_h = math.sqrt(numerator / denominator)

        # Coefficients (Table II)
        # Range coefficients
        self.c0_r = 0.041546
        self.c1_r = 0.041122
        self.c2_r = 0.00053292

        # Endurance coefficients
        self.c0_e = 0.10188
        self.c1_e = 0.071358
        self.c2_e = 0.0007381

    def solve(self):
        # Calculate optimum speeds (Eq. 18).
        # Formula: v_opt = vi,h / (c0 + c1*vi,h + c2*A)

        # 1. Best-range speed (v_range)
        denom_r = self.c0_r + (self.c1_r * self.vi_h) + (self.c2_r * self.A_ref)
        v_range_ms = self.vi_h / denom_r

        # 2. Best-endurance speed (usually slightly faster than hover)
        denom_e = self.c0_e + (self.c1_e * self.vi_h) + (self.c2_e * self.A_ref)
        v_endurance_ms = self.vi_h / denom_e

        # Calculate power consumption (Eq. 17).
        # Makale diyor ki:
        # P_range = 1.092 * P_hover
        # P_endurance = 0.914 * P_hover

        # Use measured, uncorrected hover power as the baseline.
        P_range_w = 1.092 * self.P_h_measured
        P_endurance_w = 0.914 * self.P_h_measured

        # Endurance and range for best-range mode.
        flight_time_hours_r = (self.energy_wh / P_range_w) * self.cf
        max_range_km = (v_range_ms * 3.6) * flight_time_hours_r

        # Best-endurance mode.
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
            "max_range_km_endurance": max_range_km_e,
        }


# DATASHEET DATA SETS

# 1. P80 III KV100 + MF propeller (reference - Vibe)
p80_raw_data = [
    [3505, 47.87, 6.23],
    [3744, 47.87, 6.71],
    [3992, 47.85, 7.43],
    [4267, 47.83, 8.2],
    [4565, 47.82, 8.98],
    [4885, 47.80, 9.75],
    [5248, 47.77, 11],
]
p80_thrust_power = [[row[0], row[1] * row[2]] for row in p80_raw_data]

# 2. MN7005 KV115 + P24x7.2 (12S - 48V Test Verisi)
mn7005_thrust_power = [
    [1322, 97],
    [1408, 105],
    [1513, 117],
    [1606, 126],
    [1707, 138],
    [1807, 150],
    [1947, 168],
    [2068, 183],
    [2164, 194],
    [2280, 210],
    [2398, 226],
    [2507, 243],
    [2627, 260],
    [2756, 278],
    [2888, 299],
    [3014, 320],
    [3346, 377],
    [3605, 421],
    [4224, 537],
    [4783, 669],
]

# 3. CM-X6-SE 380KV Technical Parameters HF18*6.0" - 6S
cmx6_old_thrust_power = [
    [892, 86.3],
    [1042, 103.9],
    [1199, 123.3],
    [1361, 144.3],
    [1659, 186.1],
    [1793, 206.2],
    [1962, 232.8],
    [2235, 278.2],
    [2409, 309.0],
    [2694, 361.9],
    [2841, 390.4],
    [3143, 452.3],
    [3299, 485.8],
    [3582, 548.4],
    [3748, 586.7],
    [4046, 657.3],
    [4348, 731.9],
    [4648, 807.9],
    [4815, 851.3],
    [5090, 923.3],
    [5596, 1057.5],
]

# 4. CM-X6-SE HF22*7.0"
cmx6_tech_thrust_power = [
    [1195, 93.9],
    [1327, 107.9],
    [1460, 123.0],
    [1596, 139.1],
    [1802, 165.2],
    [2013, 193.5],
    [2229, 223.9],
    [2449, 256.3],
    [2673, 290.9],
    [2901, 327.6],
    [3132, 366.6],
    [3365, 407.9],
    [3600, 451.7],
    [3836, 498.0],
    [4071, 546.8],
    [4306, 597.9],
    [4538, 651.3],
    [4768, 706.5],
    [4993, 763.0],
    [5213, 820.3],
    [5427, 877.8],
    [6058, 1051.6],
]

# 5. M5208 HP/UL
m5208_thrust_power = [
    [923, 70.2],
    [1042, 81.3],
    [1164, 94.1],
    [1287, 108.4],
    [1475, 132.3],
    [1666, 158.8],
    [1861, 187.4],
    [2061, 217.8],
    [2265, 250.1],
    [2473, 284.3],
    [2688, 320.5],
    [2907, 359.1],
    [3133, 400.5],
    [3363, 445.0],
    [3598, 493.1],
    [3835, 544.9],
    [4073, 600.2],
    [4308, 658.6],
    [4537, 718.7],
    [4756, 778.7],
    [4957, 836.0],
    [5399, 964.6],
]

# 6. MN7005 KV230 + P24x7.2
mn7005_kv230_thrust_power = [
    [1407, 105],
    [1501, 114],
    [1592, 123],
    [1698, 136],
    [1837, 152],
    [1951, 167],
    [2063, 181],
    [2153, 194],
    [2261, 209],
    [2378, 225],
    [2491, 241],
    [2605, 259],
    [2708, 273],
    [2841, 297],
    [2948, 317],
    [3060, 336],
    [3344, 387],
    [3632, 438],
    [4184, 551],
    [4691, 670],
]

# 7. U8 Lite KV150 (6S - 24V) + G29*9.5" CF
u8lite_kv150_thrust_power = [
    [1296, 77],
    [1416, 86],
    [1509, 94],
    [1654, 106],
    [1728, 113],
    [1833, 125],
    [2006, 139],
    [2128, 151],
    [2243, 166],
    [2357, 182],
    [2486, 192],
    [2612, 206],
    [2707, 218],
    [2862, 235],
    [2995, 252],
    [3142, 276],
    [3469, 317],
    [3774, 365],
    [4536, 475],
    [5378, 629],
]

# 7. M8108 Light 150KV + MSC 28x9.2 (23V - 6S Test Verisi)
m8108_light_data = [
    [871, 47.2],
    [968, 53.7],
    [1070, 61.2],
    [1178, 69.5],
    [1349, 83.6],
    [1529, 99.6],
    [1720, 117.4],
    [1919, 137.0],
    [2127, 158.4],
    [2344, 181.6],
    [2569, 206.7],
    [2802, 234.0],
    [3043, 263.5],
    [3290, 295.3],
    [3542, 329.6],
    [3798, 366.3],
    [4054, 404.9],
    [4307, 445.0],
    [4554, 485.3],
    [4789, 524.7],
    [5005, 561.3],
    [5483, 640.0],
]

# 8. M6208 155KV + MSC 21x6.3 (12S - 46V Test Verisi)
m6208_12s_data = [
    [853, 67.7],
    [953, 77.8],
    [1075, 90.2],
    [1212, 104.6],
    [1440, 129.2],
    [1683, 157.2],
    [1934, 188.1],
    [2185, 221.7],
    [2436, 257.7],
    [2684, 296.1],
    [2931, 336.7],
    [3178, 379.8],
    [3428, 425.8],
    [3684, 475.0],
    [3949, 528.1],
    [4225, 585.5],
    [4512, 647.4],
    [4812, 714.2],
    [5121, 785.7],
    [5435, 861.4],
    [5748, 940.3],
    [6582, 1180.0],
]

# 9. M8108 Light 150KV + MSC 29x9.5 (23V - 6S Test Verisi)
m8108_light_29in_data = [
    [869, 46.1],
    [963, 52.4],
    [1064, 59.6],
    [1171, 67.8],
    [1341, 81.7],
    [1522, 97.6],
    [1712, 115.2],
    [1911, 134.4],
    [2117, 155.4],
    [2332, 178.1],
    [2555, 202.5],
    [2786, 228.9],
    [3026, 257.4],
    [3273, 288.2],
    [3528, 321.4],
    [3788, 356.9],
    [4050, 394.7],
    [4312, 434.1],
    [4569, 474.2],
    [4814, 513.8],
    [5040, 551.1],
    [5517, 629.8],
]

# 10. MN601S KV170 + T-MOTOR P21x6.3 (12S - 48V test data)
mn601s_kv170_data = [
    [1677, 149],
    [1774, 168],
    [1966, 192],
    [2062, 206],
    [2182, 221],
    [2307, 244],
    [2463, 264],
    [2624, 287],
    [2726, 316],
    [2912, 340],
    [3027, 359],
    [3165, 382],
    [3366, 420],
    [3485, 444],
    [3641, 468],
    [3799, 496],
    [4186, 576],
    [4593, 661],
    [5412, 858],
    [6605, 1166],
]

# 11. U10II KV100 + G32x11" (8S - 32V Test Verisi)
u10ii_kv100_data = [
    [1651, 105],
    [1761, 113],
    [1882, 124],
    [2000, 135],
    [2133, 147],
    [2257, 159],
    [2403, 171],
    [2538, 186],
    [2689, 200],
    [2828, 217],
    [2935, 233],
    [2964, 250],
    [3245, 269],
    [3418, 285],
    [3511, 304],
    [3739, 324],
    [4119, 375],
    [4535, 430],
    [5518, 571],
    [6430, 722],
]

# 12. U10II KV100 + G30x10.5" (8S - 32V Test Verisi)
u10ii_kv100_30in_data = [
    [1405, 85],
    [1487, 91],
    [1597, 100],
    [1714, 109],
    [1817, 118],
    [1934, 128],
    [2048, 138],
    [2180, 150],
    [2307, 163],
    [2431, 176],
    [2586, 190],
    [2749, 205],
    [2879, 219],
    [3032, 236],
    [3161, 252],
    [3297, 266],
    [3655, 309],
    [4144, 367],
    [4899, 465],
    [5717, 593],
]

# 13. MN6007 II KV320 + P22x6.6" (6S - 24V Test Verisi)
mn6007ii_kv320_data = [
    [1737, 160],
    [1878, 178],
    [2080, 208],
    [2178, 223],
    [2297, 241],
    [2431, 262],
    [2565, 283],
    [2696, 304],
    [2803, 320],
    [2925, 342],
    [3059, 369],
    [3185, 392],
    [3311, 416],
    [3454, 445],
    [3573, 469],
    [3704, 496],
    [4347, 636],
    [5084, 814],
    [5882, 1041],
]

# 14. MN6007 II KV160 + P21x6.3" (12S - 48V Test Verisi)
mn6007ii_kv160_data = [
    [1444, 126],
    [1563, 141],
    [1760, 161],
    [1875, 180],
    [2006, 199],
    [2125, 215],
    [2249, 233],
    [2355, 251],
    [2488, 270],
    [2624, 293],
    [2762, 314],
    [2892, 338],
    [3030, 362],
    [3160, 390],
    [3243, 402],
    [3388, 426],
    [4118, 569],
    [4889, 738],
    [5838, 978],
]

# 15. U8 Lite KV150 + G30x10.5" (6S - 24V Test Verisi)
u8lite_kv150_g30_data = [
    [1551, 91],
    [1684, 103],
    [1766, 110],
    [1850, 120],
    [1991, 137],
    [2132, 149],
    [2256, 161],
    [2420, 178],
    [2536, 190],
    [2676, 204],
    [2816, 221],
    [2923, 235],
    [3097, 257],
    [3229, 276],
    [3334, 290],
    [3475, 310],
    [3917, 370],
    [4237, 420],
    [5020, 547],
    [5912, 713],
]

# 16. U8 Lite KV190 + G29*9.5" CF (6S - 24V)
u8lite_kv190_g29_data = [
    [2035, 149],
    [2173, 166],
    [2328, 180],
    [2486, 199],
    [2627, 218],
    [2812, 238],
    [2961, 257],
    [3195, 288],
    [3344, 312],
    [3502, 341],
    [3669, 353],
    [3833, 389],
    [4005, 410],
    [4214, 442],
    [4365, 468],
    [4782, 540],
    [5184, 610],
    [6026, 773],
    [7334, 1049],
]

# T-MOTOR datasheet load test ("testParameter_U8 Lite ... KV190.xls"):
# U8 Lite KV190, 6S (24V), [thrust_g, mechanical RPM].
# Note: the raw RPM field in DataLink logs is eRPM/10 (36N42P -> 21 pole pairs).
# The parser converts it to mechanical RPM with DATALINK_RPM_SCALE (=10/21).
# This table anchors validation of that corrected scale (hover ~3100 g -> ~2216 RPM).
u8lite_kv190_g28_thrust_rpm = [
    [1662, 1632],
    [1806, 1709],
    [1951, 1745],
    [2134, 1828],
    [2254, 1892],
    [2401, 1953],
    [2566, 2022],
    [2774, 2093],
    [2892, 2144],
    [3081, 2210],
    [3208, 2252],
    [3389, 2312],
    [3502, 2358],
    [3623, 2394],
    [3801, 2441],
    [3934, 2497],
    [4376, 2620],
    [4816, 2776],
    [5563, 2972],
    [6761, 3248],
]

u8lite_kv190_g29_thrust_rpm = [
    [1879, 1616],
    [2035, 1662],
    [2173, 1722],
    [2328, 1775],
    [2486, 1828],
    [2627, 1899],
    [2812, 1955],
    [2961, 2008],
    [3195, 2073],
    [3344, 2129],
    [3502, 2174],
    [3669, 2223],
    [3833, 2286],
    [4005, 2348],
    [4214, 2400],
    [4365, 2432],
    [4782, 2541],
    [5184, 2662],
    [6026, 2866],
    [7334, 3125],
]

U8LITE_KV190_THRUST_RPM_TABLES = {
    28.0: u8lite_kv190_g28_thrust_rpm,
    29.0: u8lite_kv190_g29_thrust_rpm,
}


# 17. U8 Lite KV190 + G28x9.2" (6S - 24V Test Verisi)
u8lite_kv190_data = [
    [1662, 115],
    [1806, 130],
    [1951, 144],
    [2134, 163],
    [2254, 173],
    [2401, 194],
    [2566, 214],
    [2774, 240],
    [2892, 252],
    [3081, 278],
    [3208, 298],
    [3389, 324],
    [3502, 338],
    [3623, 360],
    [3801, 379],
    [3934, 408],
    [4376, 470],
    [4816, 542],
    [5563, 696],
    [6761, 929],
]

# 17. U8II KV85 + G28x9.2" (12S - 48V Test Verisi)
u8ii_kv85_data = [
    [1465, 86],
    [1572, 96],
    [1717, 110],
    [1852, 125],
    [1997, 139],
    [2140, 154],
    [2256, 163],
    [2378, 178],
    [2528, 197],
    [2757, 221],
    [2957, 245],
    [3027, 254],
    [3171, 274],
    [3307, 298],
    [3448, 317],
    [3662, 341],
    [4043, 394],
    [4468, 456],
    [5248, 586],
    [6352, 792],
]

# 18. T-MOTOR P80 MF3218 (12S - 48V test data)
# Thrust (g) and power (W) values were transcribed from datasheet figures.
mf3218_data = [
    [3505, 298],
    [3744, 321],
    [3992, 356],
    [4267, 392],
    [4565, 429],
    [4885, 466],
    [5248, 525],
    [5592, 570],
    [6039, 632],
    [6510, 699],
    [7018, 777],
    [7408, 843],
    [7803, 911],
    [8227, 979],
    [8732, 1065],
    [9167, 1146],
    [10531, 1414],
    [11825, 1700],
    [13079, 1988],
    [14412, 2312],
    [15849, 2671],
]

# 19. T-MOTOR P60 KV170 + P22x6.6 (12S - 48V test data)
p60_kv170_data = [
    [2801, 316.8],
    [3312, 412.8],
    [3763, 475.2],
    [4356, 595.2],
    [2801, 316.8],
    [3312, 412.8],
    [3763, 475.2],
    [4356, 595.2],
    [5372, 820.8],
    [6582, 1113.6],
    [8414, 1632],
]

# 20. U10II KV100 + G28*9.2" CF (12S - 48V) - NEW
u10ii_kv100_new_data = [
    [2087, 167],
    [2298, 187],
    [2425, 208],
    [2732, 226],
    [3007, 262],
    [3119, 279],
    [3376, 305],
    [3578, 327],
    [3722, 351],
    [3947, 379],
    [4053, 401],
    [4348, 437],
    [4507, 459],
    [4692, 488],
    [4846, 516],
    [5115, 553],
    [5496, 610],
    [6070, 709],
    [7285, 922],
    [8629, 1176],
]

# 21. U8 Lite KV150 + G29*9.5" CF (6S - 24V) - NEW
u8lite_kv150_new_data = [
    [1296, 77],
    [1416, 86],
    [1509, 94],
    [1654, 106],
    [1728, 113],
    [1833, 125],
    [2006, 139],
    [2128, 151],
    [2243, 166],
    [2357, 182],
    [2486, 192],
    [2612, 206],
    [2707, 218],
    [2862, 235],
    [2995, 252],
    [3142, 276],
    [3469, 317],
    [3774, 365],
    [4536, 475],
    [5378, 629],
]

# 22. U8II-X KV100 (Alpha 60A 12S) + MF2815 (12S - 48V) - NEW
u8iix_kv100_data = [
    [2088, 167],
    [2594, 224],
    [3145, 293],
    [3747, 375],
    [4384, 470],
    [5028, 579],
    [5740, 703],
    [6440, 842],
    [7115, 992],
    [7771, 1156],
    [8403, 1331],
    [8903, 1491],
    [9082, 1569],
]

# 23. Yildizlar high-performing motor - 24 V (6S LiPo) + HQ9x5x3
yildizlar_iyi_motor_data = [
    [784, 129],
    [1263, 267],
    [1736, 435],
    [2300, 649],
    [3062, 935],
    [3910, 1304],
    [4279, 1535],
]

# 24. Yildizlar low-performing motor - SE 3115 900KV + HQ9x5x3
yildizlar_kotu_motor_data = [
    [265, 45.36],
    [835, 189.00],
    [1321, 332.64],
    [1987, 599.89],
    [2838, 1012.50],
    [3249, 1289.60],
    [3656, 1530.16],
    [3784, 1596.54],
]

# 25. Previous-year Yildizlar motor - DAL T5045 tri-blade
yildizlar_gecen_sene_data = [
    [96, 16.00],
    [221, 49.60],
    [326, 81.60],
    [407, 113.60],
    [499, 145.60],
    [579, 177.60],
    [645, 209.60],
    [719, 241.60],
    [792, 273.60],
    [855, 305.60],
    [918, 339.20],
    [976, 369.60],
    [1041, 401.60],
    [1103, 433.60],
    [1160, 465.60],
    [1215, 496.00],
    [1281, 537.60],
]

# 26. Virtual average of the two Yildizlar motor data sets
yildizlar_sanal_ortalama_data = [
    [265, 22.68],
    [784, 152.57],
    [835, 166.35],
    [1263, 291.25],
    [1321, 310.12],
    [1736, 467.08],
    [1987, 565.06],
    [2300, 700.32],
    [2838, 931.71],
    [3062, 1049.26],
    [3249, 1152.99],
    [3656, 1361.82],
    [3784, 1422.86],
]


# HELPERS


def interpolate(value, x_list, y_list):
    if value < x_list[0]:
        return y_list[0]
    if value > x_list[-1]:
        return y_list[-1]
    for i in range(len(x_list) - 1):
        if x_list[i] == x_list[i + 1]:
            continue
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
    """Return a 3x3 matrix determinant for Cramer's rule."""
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def quadratic_regression(data_list):
    """Fit ``power = a*thrust^2 + b*thrust + c`` by least squares."""
    n = len(data_list)
    sx = sum(d[0] for d in data_list)
    sy = sum(d[1] for d in data_list)
    sx2 = sum(d[0] ** 2 for d in data_list)
    sx3 = sum(d[0] ** 3 for d in data_list)
    sx4 = sum(d[0] ** 4 for d in data_list)
    sxy = sum(d[0] * d[1] for d in data_list)
    sx2y = sum(d[0] ** 2 * d[1] for d in data_list)

    # Normal denklemler: A·[a,b,c]^T = rhs
    A_mat = [[sx4, sx3, sx2], [sx3, sx2, sx], [sx2, sx, n]]
    det_A = _det3(A_mat)

    if abs(det_A) < 1e-12:
        # Dejenere durum — lineer fallback
        return 0, sy / max(sx, 1e-12), 0

    a = _det3([[sx2y, sx3, sx2], [sxy, sx2, sx], [sy, sx, n]]) / det_A
    b = _det3([[sx4, sx2y, sx2], [sx3, sxy, sx], [sx2, sy, n]]) / det_A
    c = _det3([[sx4, sx3, sx2y], [sx3, sx2, sxy], [sx2, sx, sy]]) / det_A

    return a, b, c


def get_power_from_thrust_quadratic(thrust, data_list):
    """Interpolate linearly in range and extrapolate quadratically outside it."""
    thrusts = [d[0] for d in data_list]

    # Use normal interpolation inside the measured range.
    if thrusts[0] <= thrust <= thrusts[-1]:
        return get_power_from_thrust(thrust, data_list)

    # Extrapolate quadratically outside the measured range.
    a, b, c = quadratic_regression(data_list)
    power = a * (thrust**2) + b * thrust + c
    return max(0, power)  # Negative power is not physically meaningful.


FIRFIR_SPEED_PRESET = {
    "vehicle_name": "Firfir",
    "mass_kg": 12.4,
    "num_rotors": 4,
    "prop_diameter_inch": 28.0,
    "blade_count": 2,
    "rho": 1.225,
    # Raw DataLink hover ~4500 (eRPM/10) * DATALINK_RPM_SCALE = ~2143 mechanical
    # RPM; the datasheet load test gives ~2216 RPM at the same thrust (~3% difference).
    "utip_ms": 79.8,
    "hover_rpm_estimate": 2142.9,
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
    # Firfir's thrust-table theoretical hover power (U8 Lite KV190 + G28x9.2,
    # 12.4 kg / 4 motors). DataLink measured hover / this theoretical value is
    # the reality/efficiency ratio. When the tuned model is applied to a new
    # aircraft, that aircraft's theoretical P_hover is multiplied by this ratio.
    "theoretical_hover_power_w": get_power_from_thrust(12400.0 / 4.0, u8lite_kv190_data)
    * 4.0,
}

CALIBRATION_DATA_ROOT = "data/calibration/2026-07-03"
FIRFIR_ATTITUDE_LOG_CANDIDATES = [
    f"{CALIBRATION_DATA_ROOT}/flight_attitude.csv",
]
FIRFIR_DATALINK_ROOT_CANDIDATES = [
    f"{CALIBRATION_DATA_ROOT}/Datalink",
]
DATALINK_EXPECTED_MOTOR_COUNT = 4
DATALINK_RECORD_HEADER_BYTES = 32
DATALINK_RECORD_BYTES = 160
DATALINK_SLOT_BYTES = 19
DATALINK_DEFAULT_SAMPLE_HZ = 20.0
DATALINK_CURRENT_SCALE = 100.0
# The raw .udat RPM field is eRPM/10, not mechanical RPM (U8 Lite 36N42P ->
# 21 pole pairs): mechanical RPM = raw * 10/21. Datasheet anchor: at Firfir's
# hover thrust (3100 g/rotor, G28x9.2), the load test gives ~2216 mechanical
# RPM; raw ~4500 * 10/21 = ~2143, which is consistent with that loaded point.
# KV times nominal voltage alone is not an absolute RPM bound: a charged 6S
# pack exceeds nominal voltage, so the loaded datasheet point is the anchor.
DATALINK_RPM_SCALE = 10.0 / 21.0
# Mechanical equivalent (~143-5714) of the old raw-field sanity range 300-12000.
DATALINK_RPM_SANITY_RANGE_MECH = (140.0, 5750.0)
DATALINK_SPEED_BIN_WIDTH_MS = 1.0
DATALINK_MIN_BIN_SAMPLES = 80
DATALINK_MEASURED_CURVE_DATE_HINT = "260703"
DATALINK_MEASURED_EXTRAPOLATION_START_MS = 18.0
DATALINK_MEASURED_OUTPUT_PREFIX = "measured_datalink_power_curve"
DATALINK_EMPIRICAL_OUTPUT_PATH = "empirical_datalink_power_curve.png"
DATALINK_DIAGNOSTIC_SURROGATE_OUTPUT_PATH = "diagnostic_datalink_surrogate_fits.png"
DATALINK_SCIENTIFIC_AUDIT_PATH = "scientific_model_fit_audit.md"
DATALINK_FIT_REPORT_PATH = "datalink_fit_method_report.md"
DATALINK_MEASURED_MODEL_NAME_MAP = {
    "zeng_measured_fit": "zeng_datalink_fit",
    "faessler_measured_fit": "faessler_datalink_fit",
    "kirschstein_measured_fit": "kirschstein_datalink_fit",
}
DATALINK_FIT_MODEL_ORDER = (
    "zeng_datalink_fit",
    "faessler_datalink_fit",
    "kirschstein_datalink_fit",
)
DATALINK_FIT_MODEL_SLUGS = {
    "zeng_datalink_fit": "zeng",
    "faessler_datalink_fit": "faessler",
    "kirschstein_datalink_fit": "kirschstein",
}
DATALINK_DATASHEET_UTIP_RANGE_MS = (57.0, 110.0)
DATALINK_FIRFIR_LAMBDA_ACCEPTANCE_N_PER_MS = (0.3, 3.5)
DATALINK_BODY_CD_MAX = 5.0
DATALINK_SESSION_CLOCK_CORRECTION_S = {}

FIRFIR_BATTERY_CELLS = 6
FIRFIR_BATTERY_MEASURED_USABLE_AH = 25.2
FIRFIR_BATTERY_DATASHEET_NOMINAL_AH = 27.0
FIRFIR_BATTERY_NOMINAL_V_PER_CELL = 3.7
# Only 25.2 Ah of the July 3 Firfir battery's datasheet-rated 27 Ah was measured
# as usable. Applying this usable fraction (instead of the old CF) to entered
# batteries gives consistent, model-based behavior.
FIRFIR_BATTERY_USABLE_FRACTION = (
    FIRFIR_BATTERY_MEASURED_USABLE_AH / FIRFIR_BATTERY_DATASHEET_NOMINAL_AH
)
# Firfir's actual battery is 6S2P (12 cells). The current/energy sensor was
# installed on only one parallel branch (6S1P), so hover power measured from
# DataLink (~758 W) and integrated energy (~490 Wh / usable ~559 Wh) are half
# the actual aircraft values. Actual values = measured values multiplied by
# FIRFIR_BATTERY_PARALLEL_ARMS: hover ~1516 W (above the theoretical 1124 W,
# which is physically plausible), full-pack usable energy ~1119 Wh, and hover
# time 40 min (the branch-independent ratio is unchanged). Because P/Ph tuning
# uses a ratio, the branch multiplier cancels there; this constant only maps
# absolute Firfir fit-source values to the physical aircraft.
FIRFIR_BATTERY_PARALLEL_ARMS = 2

# Rest-voltage anchors for the calibrated 6S Li-ion solid-state pack.


def tip_speed_from_rpm(prop_diameter_inch, rpm):
    diameter_m = prop_diameter_inch * 0.0254
    return math.pi * diameter_m * rpm / 60.0


def zeng_induced_ratio(speed_ms, v0_ms):
    if v0_ms <= 0:
        return 1.0
    v = max(0.0, speed_ms)
    inner = math.sqrt(1.0 + (v**4) / (4.0 * v0_ms**4)) - (v**2) / (2.0 * v0_ms**2)
    return math.sqrt(max(inner, 0.0))


def zeng_profile_ratio(speed_ms, utip_ms):
    if utip_ms <= 0:
        raise ValueError("Utip must be positive.")
    return 1.0 + 3.0 * (speed_ms**2) / (utip_ms**2)


def power_ratio_bauersfeld_anchored_zeng(speed_ms, params):
    return (
        params["f0"] * zeng_profile_ratio(speed_ms, params["utip_ms"])
        + params["induced_fraction"] * zeng_induced_ratio(speed_ms, params["v0_ms"])
        + params["k_par"] * speed_ms**3
    )


def build_theoretical_zeng_params(model_profile, hover_power_reference_w):
    rho = model_profile["rho"]
    mass_kg = model_profile["mass_kg"]
    num_rotors = model_profile["num_rotors"]
    diameter_m = model_profile["prop_diameter_inch"] * 0.0254
    radius_m = diameter_m / 2.0
    area_one_m2 = math.pi * radius_m**2
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
    p0_mech = (delta / 8.0) * rho * solidity_s * area_total_m2 * utip_ms**3
    pi_mech = (1.0 + k_induced) * (weight_n**1.5) / math.sqrt(2.0 * rho * area_total_m2)
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
                rows.append(
                    {
                        "time_s": time_s,
                        "vx_ms": vx_ms,
                        "vy_ms": vy_ms,
                        "pitch_deg": pitch_deg,
                        "roll_deg": roll_deg,
                    }
                )
    rows.sort(key=lambda row: row["time_s"])
    return rows


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


def parse_datalink_udat_file(
    path,
    prop_diameter_inch=29.0,
    timestamp_mode="filename_utc",
    current_scale=DATALINK_CURRENT_SCALE,
    expected_motor_count=DATALINK_EXPECTED_MOTOR_COUNT,
):
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

    raw_record_count = (
        len(data) - DATALINK_RECORD_HEADER_BYTES
    ) // DATALINK_RECORD_BYTES
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
        record = data[offset : offset + DATALINK_RECORD_BYTES]
        motors = []
        for slot_idx in range(8):
            slot_offset = slot_idx * DATALINK_SLOT_BYTES
            slot = record[slot_offset : slot_offset + DATALINK_SLOT_BYTES]
            if len(slot) < DATALINK_SLOT_BYTES:
                continue
            motor_id = slot[6]
            voltage_v = int.from_bytes(slot[15:17], "big") / 10.0
            current_a = int.from_bytes(slot[17:19], "big") / current_scale
            rpm = int.from_bytes(slot[13:15], "big") * DATALINK_RPM_SCALE
            if motor_id < 1 or motor_id > expected_motor_count:
                continue
            if not (10.0 <= voltage_v <= 30.0):
                continue
            if not (0.0 <= current_a <= 100.0):
                continue
            if not (
                DATALINK_RPM_SANITY_RANGE_MECH[0]
                <= rpm
                <= DATALINK_RPM_SANITY_RANGE_MECH[1]
            ):
                continue
            motors.append(
                {
                    "motor_id": motor_id,
                    "voltage_v": voltage_v,
                    "current_a": current_a,
                    "rpm": rpm,
                }
            )

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
        samples.append(
            {
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
            }
        )
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
        "active_motor_count_median": int(round(_median(active_counts)))
        if active_counts
        else 0,
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
            raw_records = max(
                0,
                (path.stat().st_size - DATALINK_RECORD_HEADER_BYTES)
                // DATALINK_RECORD_BYTES,
            )
            end_naive = start_naive + timedelta(
                seconds=raw_records / DATALINK_DEFAULT_SAMPLE_HZ
            )
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


def resolve_datalink_session_root(log_root):
    """Return the directory that directly contains the UART sessions.

    Both ``root/Datalink/UART-*`` and ``root/UART-*`` layouts are supported.
    """
    log_root = Path(log_root)
    datalink_sub = log_root / "Datalink"
    if datalink_sub.is_dir() and any(
        child.is_dir() and child.name.startswith("UART-")
        for child in datalink_sub.iterdir()
    ):
        return datalink_sub
    return log_root


def _session_date_hints(session_root):
    hints = set()
    if not Path(session_root).is_dir():
        return []
    for child in Path(session_root).iterdir():
        if not child.is_dir():
            continue
        match = re.match(r"UART-(\d{6})-", child.name)
        if match:
            hints.add(match.group(1))
    return sorted(hints)


def discover_datalink_log_roots():
    """Return bundled and user-added flight-log roots with UART date hints."""
    base_dir = Path(__file__).resolve().parent
    candidates = [base_dir / CALIBRATION_DATA_ROOT]
    for candidate in FIRFIR_DATALINK_ROOT_CANDIDATES:
        path = Path(candidate)
        if not path.is_absolute():
            path = base_dir / path
        if path.is_dir():
            candidates.append(path)
    entries = []
    for root in candidates:
        hints = _session_date_hints(resolve_datalink_session_root(root))
        if hints:
            has_bin = any(
                path.suffix.lower() == ".bin" for path in root.iterdir()
            )
            entries.append(
                {
                    "path": root,
                    "label": root.name if root.parent == base_dir else str(
                        root.relative_to(base_dir)
                    ),
                    "date_hints": hints,
                    "has_bin": has_bin,
                }
            )
    # Keep the bundled calibration set first.
    entries.sort(
        key=lambda entry: (
            entry["path"] != base_dir / CALIBRATION_DATA_ROOT,
            entry["label"].lower(),
        )
    )
    return entries


def prompt_datalink_root_and_hint(default_hint=DATALINK_MEASURED_CURVE_DATE_HINT):
    """Prompt for a discovered flight-log root and a YYMMDD date hint."""
    entries = [
        entry for entry in discover_datalink_log_roots() if entry.get("has_bin")
    ]
    print("\nDataLink/log directory:")
    for idx, entry in enumerate(entries, 1):
        default_marker = " [default]" if idx == 1 else ""
        print(
            f"{idx}) {entry['label']} "
            f"(dates: {', '.join(entry['date_hints'])}){default_marker}"
        )
    print("m) Enter a directory/date manually")
    default_choice = "1" if entries else "m"
    raw = input(f"Selection [{default_choice}]: ").strip().lower() or default_choice
    if raw == "m" or not entries:
        root_raw = input(
            "Log directory [automatic: bundled 2026-07-03 calibration data]: "
        ).strip()
        log_root = Path(root_raw) if root_raw else None
        hint_raw = input(f"Date hint (YYMMDD) [{default_hint}]: ").strip()
        return log_root, normalize_datalink_date_hint(hint_raw) or default_hint
    try:
        idx = int(raw)
    except ValueError:
        idx = 1
    entry = entries[min(max(idx, 1), len(entries)) - 1]
    hints = entry["date_hints"]
    if len(hints) > 1:
        print("Date:")
        for h_idx, hint in enumerate(hints, 1):
            print(f"{h_idx}) {hint}")
        hint_raw = input("Selection [1]: ").strip()
        try:
            h_idx = int(hint_raw) if hint_raw else 1
        except ValueError:
            h_idx = 1
        hint = hints[min(max(h_idx, 1), len(hints)) - 1]
    else:
        hint = hints[0]
    return entry["path"], hint


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
    return datetime(1980, 1, 6, tzinfo=timezone.utc) + timedelta(
        weeks=int(gps_week), milliseconds=float(gps_ms)
    )


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
            session_start, session_end = _datalink_session_utc_bounds(
                session, timestamp_mode
            )
            if session_start is None or session_end is None:
                continue
            for bin_span in bin_spans:
                if bin_span.get("error"):
                    continue
                overlap_start = max(session_start, bin_span["first_utc"])
                overlap_end = min(session_end, bin_span["last_utc"])
                overlap_s = (overlap_end - overlap_start).total_seconds()
                if overlap_s >= min_overlap_s:
                    overlaps.append(
                        {
                            "session": session,
                            "bin_span": bin_span,
                            "timestamp_mode": timestamp_mode,
                            "start_utc": overlap_start,
                            "end_utc": overlap_end,
                            "overlap_s": overlap_s,
                        }
                    )
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
        timestamp_utc = anchor_utc + timedelta(
            seconds=data["TimeUS"] / 1e6 - anchor_timeus_s
        )
        if start_utc and timestamp_utc < start_utc:
            continue
        if end_utc and timestamp_utc > end_utc:
            continue
        vx_ms = data.get("VN", 0.0)
        vy_ms = data.get("VE", 0.0)
        samples.append(
            {
                "timestamp_utc": timestamp_utc,
                "source_bin": bin_path.name,
                "speed_ms": math.hypot(vx_ms, vy_ms),
                "vx_ms": vx_ms,
                "vy_ms": vy_ms,
                "vertical_speed_ms": -data.get("VD", 0.0),
                "altitude_m": -data.get("PD", 0.0),
                "pitch_deg": data.get("Pitch", 0.0),
                "roll_deg": data.get("Roll", 0.0),
            }
        )
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
        samples.extend(
            sample for sample in parsed["samples"] if sample.get("timestamp_utc")
        )
    # Apply an optional per-session correction to each DataLink timestamp.
    correction_s = DATALINK_SESSION_CLOCK_CORRECTION_S.get(session.get("name"), 0.0)
    if correction_s:
        for sample in samples:
            sample["timestamp_utc"] = sample["timestamp_utc"] + timedelta(
                seconds=correction_s
            )
    samples.sort(key=lambda item: item["timestamp_utc"])
    return samples


def join_datalink_and_flight_samples(
    datalink_samples, flight_samples, hover_power_w, max_dt_s=0.35
):
    if not datalink_samples or not flight_samples:
        return []
    joined = []
    idx = 0
    for dl_sample in datalink_samples:
        dl_time = dl_sample["timestamp_utc"]
        while (
            idx + 1 < len(flight_samples)
            and flight_samples[idx + 1]["timestamp_utc"] <= dl_time
        ):
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
        power_ratio = (
            dl_sample["power_w"] / hover_power_w if hover_power_w > 0 else float("nan")
        )
        if not math.isfinite(power_ratio) or power_ratio <= 0:
            continue
        joined.append(
            {
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
            }
        )
    return joined


def annotate_joined_sample_stability(
    joined_samples,
    max_abs_accel_ms2=8.0,
    max_abs_vertical_speed_ms=1.5,
    max_abs_roll_deg=28.0,
    max_abs_pitch_deg=28.0,
):
    if not joined_samples:
        return []
    samples = [
        dict(sample)
        for sample in sorted(joined_samples, key=lambda item: item["timestamp_utc"])
    ]
    for idx, sample in enumerate(samples):
        accel_ms2 = 0.0
        if 0 < idx < len(samples) - 1:
            prev_sample = samples[idx - 1]
            next_sample = samples[idx + 1]
            dt_s = (
                next_sample["timestamp_utc"] - prev_sample["timestamp_utc"]
            ).total_seconds()
            if 0.0 < dt_s <= 1.0:
                accel_ms2 = (
                    abs(next_sample["speed_ms"] - prev_sample["speed_ms"]) / dt_s
                )
        elif idx > 0:
            prev_sample = samples[idx - 1]
            dt_s = (
                sample["timestamp_utc"] - prev_sample["timestamp_utc"]
            ).total_seconds()
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


def estimate_datalink_hover_power(
    joined_samples,
    max_speed_ms=1.5,
    max_abs_pitch_deg=8.0,
    max_abs_roll_deg=8.0,
    min_power_w=100.0,
    min_samples=200,
):
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


def build_datalink_speed_observations(
    joined_samples,
    min_speed_ms=2.0,
    max_speed_ms=25.0,
    bin_width_ms=DATALINK_SPEED_BIN_WIDTH_MS,
    min_samples=DATALINK_MIN_BIN_SAMPLES,
    power_reference_w=None,
    stable_only=False,
    min_stable_fraction=0.5,
    extrapolation_start_ms=None,
):
    bins = {}
    for sample in joined_samples:
        speed_ms = sample["speed_ms"]
        if not (min_speed_ms <= speed_ms <= max_speed_ms):
            continue
        bin_center = round(
            (math.floor(speed_ms / bin_width_ms) + 0.5) * bin_width_ms, 2
        )
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
            ratios = [
                sample["power_w"] / power_reference_w for sample in values_for_stats
            ]
        else:
            ratios = [sample["power_ratio"] for sample in values_for_stats]
        powers = [sample["power_w"] for sample in values_for_stats]
        rpms = [sample["rpm_median"] for sample in values_for_stats]
        utips = [sample["utip_ms"] for sample in values_for_stats]
        speeds = [sample["speed_ms"] for sample in values_for_stats]
        dt_values = [
            sample.get("dt_s")
            for sample in values_for_stats
            if sample.get("dt_s") is not None and math.isfinite(sample.get("dt_s"))
        ]
        speed_ms = _median(speeds)
        extrapolation_region = "measured"
        if extrapolation_start_ms is not None and speed_ms > extrapolation_start_ms:
            extrapolation_region = "extrapolation"
        observations.append(
            {
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
            }
        )
    return observations


def build_empirical_datalink_power_curve(observations):
    measured_points = [
        dict(obs)
        for obs in observations
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
        "sample_count_total": sum(
            obs.get("sample_count", 0) for obs in measured_points
        ),
        "raw_sample_count_total": sum(
            obs.get("raw_sample_count", 0) for obs in measured_points
        ),
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
        power_ratio = lower["power_ratio"] + t * (
            upper["power_ratio"] - lower["power_ratio"]
        )
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


def resolve_fit_power_reference(measured_hover_power_w, profile, entered_hover_power_w):
    """Choose a safe normalization reference for the P(V)/P_hover curve."""
    if measured_hover_power_w:
        return measured_hover_power_w
    theoretical_w = profile.get("theoretical_hover_power_w")
    if theoretical_w:
        print(
            "WARNING: DataLink hover power was unavailable; normalizing P/Ph "
            f"with the fit aircraft's theoretical hover power ({theoretical_w:.1f} W)."
        )
        return theoretical_w
    print(
        "WARNING: DataLink and theoretical fit-aircraft hover power are unavailable; "
        f"normalizing with the entered hover power ({entered_hover_power_w:.1f} W). "
        "Results are unreliable unless the entered aircraft produced the fit data."
    )
    return entered_hover_power_w


def find_measured_curve_log_root(log_root=None):
    if log_root:
        path = Path(log_root).expanduser().resolve()
        if path.is_dir():
            return path
        raise FileNotFoundError(f"DataLink measured log root not found: {path}")

    default_root = Path(__file__).resolve().parent / CALIBRATION_DATA_ROOT
    if default_root.is_dir():
        return default_root
    raise FileNotFoundError(
        "Calibration data is distributed in the source repository, not the wheel. "
        "Pass --data-root /path/to/repository/data/calibration/2026-07-03 "
        f"(default directory not found: {default_root})."
    )


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
        timestamp_utc = anchor_utc + timedelta(
            seconds=data["TimeUS"] / 1e6 - anchor_timeus_s
        )
        if start_utc and timestamp_utc < start_utc:
            continue
        if end_utc and timestamp_utc > end_utc:
            continue
        rows.append(
            {
                "timestamp_utc": timestamp_utc,
                "bin": Path(bin_path).name,
                "volt_v": data.get("Volt"),
                "voltr_v": data.get("VoltR"),
                "curr_a": data.get("Curr"),
                "currtot_ah": data.get("CurrTot"),
                "enrgtot_raw": data.get("EnrgTot"),
                "rempct": data.get("RemPct"),
                "res_mohm": data.get("Res"),
            }
        )
    rows.sort(key=lambda row: row["timestamp_utc"])
    return rows


def integrate_joined_energy_wh(joined_samples, max_dt_s=1.0):
    samples = sorted(joined_samples, key=lambda sample: sample["timestamp_utc"])
    chunks = []
    current_chunk = []
    energy_wh = 0.0
    for sample in samples:
        if current_chunk:
            dt_s = (
                sample["timestamp_utc"] - current_chunk[-1]["timestamp_utc"]
            ).total_seconds()
            if 0.0 < dt_s <= max_dt_s:
                energy_wh += (
                    0.5
                    * (current_chunk[-1]["power_w"] + sample["power_w"])
                    * dt_s
                    / 3600.0
                )
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
        duration_s = (
            chunk[-1]["timestamp_utc"] - chunk[0]["timestamp_utc"]
        ).total_seconds()
        chunk_energy_wh = 0.0
        for prev_sample, sample in zip(chunk, chunk[1:]):
            dt_s = (
                sample["timestamp_utc"] - prev_sample["timestamp_utc"]
            ).total_seconds()
            if 0.0 < dt_s <= max_dt_s:
                chunk_energy_wh += (
                    0.5 * (prev_sample["power_w"] + sample["power_w"]) * dt_s / 3600.0
                )
        speeds = [sample["speed_ms"] for sample in chunk]
        chunk_summaries.append(
            {
                "start_utc": chunk[0]["timestamp_utc"],
                "end_utc": chunk[-1]["timestamp_utc"],
                "duration_s": duration_s,
                "energy_wh": chunk_energy_wh,
                "avg_power_w": chunk_energy_wh * 3600.0 / duration_s
                if duration_s > 0
                else 0.0,
                "median_speed_ms": _median(speeds),
                "sample_count": len(chunk),
            }
        )
    return energy_wh, chunk_summaries


def build_battery_qc_report(bin_paths, joined_samples):
    battery_rows = []
    energy_delta_raw = 0.0
    currtot_delta_ah = 0.0
    for bin_path in bin_paths:
        rows = read_battery_monitor_rows(bin_path)
        battery_rows.extend(rows)
        if len(rows) >= 2:
            if (
                rows[0].get("enrgtot_raw") is not None
                and rows[-1].get("enrgtot_raw") is not None
            ):
                energy_delta_raw += rows[-1]["enrgtot_raw"] - rows[0]["enrgtot_raw"]
            if (
                rows[0].get("currtot_ah") is not None
                and rows[-1].get("currtot_ah") is not None
            ):
                currtot_delta_ah += rows[-1]["currtot_ah"] - rows[0]["currtot_ah"]

    battery_rows.sort(key=lambda row: row["timestamp_utc"])
    datalink_energy_wh, chunks = integrate_joined_energy_wh(joined_samples)
    currents = [
        row["curr_a"]
        for row in battery_rows
        if row.get("curr_a") is not None and math.isfinite(row["curr_a"])
    ]
    voltr_values = [
        row["voltr_v"]
        for row in battery_rows
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
        warnings.append(
            "battery_energy_scale_suspect: BAT.EnrgTot disagrees with DataLink energy"
        )

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


def build_measured_curve_model_fit(
    profile, calculation_result, hover_power_reference_w, observations, faessler_fit=None
):
    vi_h = calculation_result["vi_h"]
    measured_profile = dict(profile)
    utip_values = [obs["utip_ms"] for obs in observations if obs.get("utip_ms")]
    if utip_values:
        measured_profile["utip_ms"] = _median(utip_values)
        measured_profile["utip_source"] = "datalink_rpm"
        measured_profile["hover_rpm_estimate"] = (
            measured_profile["utip_ms"]
            * 60.0
            / (math.pi * measured_profile["prop_diameter_inch"] * 0.0254)
        )
    theoretical_params = build_theoretical_zeng_params(
        measured_profile, hover_power_reference_w
    )
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
            lambda v, p=faessler_params: power_ratio_faessler_drag_constrained_zeng(
                v, p
            )
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
            rows.append(
                {
                    "label": obs["label"],
                    "speed_ms": obs["speed_ms"],
                    "target": obs["power_ratio"],
                    "fit": predicted,
                    "error": predicted - obs["power_ratio"],
                    "sample_count": obs["sample_count"],
                }
            )
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


def plot_measured_power_curve(
    observations,
    model_functions=None,
    output_path=DATALINK_DIAGNOSTIC_SURROGATE_OUTPUT_PATH,
    extrapolation_start_ms=DATALINK_MEASURED_EXTRAPOLATION_START_MS,
):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    measured = [
        obs for obs in observations if obs["extrapolation_region"] == "measured"
    ]
    extrapolated = [
        obs for obs in observations if obs["extrapolation_region"] == "extrapolation"
    ]
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
        support_min = min((obs["speed_ms"] for obs in measured), default=float("inf"))
        support_max = min(
            max((obs["speed_ms"] for obs in measured), default=-float("inf")),
            extrapolation_start_ms,
        )
        if support_min <= support_max:
            speeds = sorted(set(speeds + [support_min, support_max]))
            ax.axvspan(
                support_min, support_max, color="gray", alpha=0.1,
                label="Measured-bin interval (solid fits)",
            )
        for name, ratio_fn in model_functions.items():
            solid_speeds = [
                speed for speed in speeds if support_min <= speed <= support_max
            ]
            line, = ax.plot(
                solid_speeds, [ratio_fn(speed) for speed in solid_speeds], label=name
            )
            outside_intervals = (
                [[speed for speed in speeds if speed <= support_min],
                 [speed for speed in speeds if speed >= support_max]]
                if support_min <= support_max else [speeds]
            )
            for dashed_speeds in outside_intervals:
                ax.plot(
                    dashed_speeds,
                    [ratio_fn(speed) for speed in dashed_speeds],
                    linestyle="--", color=line.get_color(),
                )
    ax.set_xlabel("Speed [m/s]")
    ax.set_ylabel("P(V) / P_hover_measured")
    ax.set_title("Diagnostic surrogate fits; dashed outside measured-bin support")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


def plot_empirical_datalink_power_curve(
    empirical_curve, output_path=DATALINK_EMPIRICAL_OUTPUT_PATH
):
    import matplotlib.pyplot as plt

    points = empirical_curve.get("measured_points", [])
    fig, ax = plt.subplots(figsize=(12, 7))
    if points:
        speeds = [obs["speed_ms"] for obs in points]
        ratios = [obs["power_ratio"] for obs in points]
        ax.plot(
            speeds, ratios, color="black", linewidth=1.5, label="linear interpolation"
        )
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
    ax.set_xlabel("Speed [m/s]")
    ax.set_ylabel("P(V) / P_hover_measured")
    ax.set_title("DataLink empirical P(v): measured range only")
    ax.margins(y=0.18)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


def plot_battery_voltage_timeline(
    battery_rows, sync_report, output_path="measured_datalink_battery_voltage.png"
):
    import matplotlib.pyplot as plt

    rows = [row for row in battery_rows if row.get("voltr_v") is not None]
    fig, ax = plt.subplots(figsize=(11, 5))
    if rows:
        start = rows[0]["timestamp_utc"]
        times_min = [
            (row["timestamp_utc"] - start).total_seconds() / 60.0 for row in rows
        ]
        ax.plot(
            times_min,
            [row["voltr_v"] for row in rows],
            color="green",
            label="BAT VoltR",
        )
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


def run_datalink_measured_curve_analysis(
    profile,
    calculation_result,
    hover_power_w,
    battery_wh,
    correction_factor,
    log_root=None,
    date_hint=DATALINK_MEASURED_CURVE_DATE_HINT,
    make_graph=True,
    timestamp_mode="filename_trt",
):
    log_root = find_measured_curve_log_root(log_root)
    # Keep the attitude prior with the selected telemetry, including when this
    # module is installed in site-packages. An explicit profile path wins.
    attitude_path = log_root / "flight_attitude.csv"
    if not profile.get("attitude_log_csv") and attitude_path.is_file():
        profile = dict(profile, attitude_log_csv=str(attitude_path.resolve()))
    datalink_root = resolve_datalink_session_root(log_root)
    bin_paths = sorted(
        path for path in log_root.iterdir() if path.suffix.lower() == ".bin"
    )
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
            sample
            for sample in parsed_session_cache[cache_key]
            if overlap["start_utc"] <= sample["timestamp_utc"] <= overlap["end_utc"]
        ]
        flight_samples = read_ardupilot_flight_samples(
            overlap["bin_span"]["path"],
            overlap["start_utc"],
            overlap["end_utc"],
        )
        joined = join_datalink_and_flight_samples(
            datalink_samples, flight_samples, hover_power_w
        )
        accepted = bool(joined) and overlap["timestamp_mode"] == timestamp_mode
        reject_reason = None
        if not joined:
            reject_reason = "no_joined_samples"
        elif overlap["timestamp_mode"] != timestamp_mode:
            reject_reason = f"non_preferred_timestamp_mode:{overlap['timestamp_mode']}"
        if accepted:
            joined_for_fit.extend(joined)
        sync_report.append(
            {
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
            }
        )

    joined_for_fit = annotate_joined_sample_stability(joined_for_fit)
    measured_hover_power_w = estimate_datalink_hover_power(joined_for_fit)
    power_reference_w = resolve_fit_power_reference(
        measured_hover_power_w, profile, hover_power_w
    )
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
    model_fit = build_measured_curve_model_fit(
        profile, calculation_result, power_reference_w, observations
    )
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
        "model_params": {
            "zeng_measured_fit": model_fit["zeng_params"],
            "faessler_measured_fit": model_fit["faessler_params"],
            "kirschstein_measured_fit": model_fit["kirschstein_params"],
        },
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
        graph_paths["audit"] = write_scientific_fit_audit(result)

    return result


def build_battery_reserve_report(
    power_reference_w, legacy_battery_wh, legacy_correction_factor, battery_basis
):
    if not power_reference_w:
        return {
            "battery_basis": battery_basis,
            "legacy_input_battery_wh": legacy_battery_wh,
            "legacy_correction_factor": legacy_correction_factor,
        }

    usable_wh = battery_basis["usable_energy_wh"]
    hover_100_min = usable_wh / power_reference_w * 60.0
    hover_20_min = hover_100_min * _reserve_fraction_from_basis(battery_basis, 20)
    hover_10_min = hover_100_min * _reserve_fraction_from_basis(battery_basis, 10)
    hover_5_min = hover_100_min * _reserve_fraction_from_basis(battery_basis, 5)
    hover_0_min = hover_100_min * _reserve_fraction_from_basis(battery_basis, 0)

    legacy_hover_100_min = legacy_battery_wh / power_reference_w * 60.0
    legacy_hover_configured_min = legacy_hover_100_min * legacy_correction_factor
    return {
        "battery_basis": battery_basis,
        "hover_100_min": hover_100_min,
        "hover_20_reserve_min": hover_20_min,
        "hover_10_reserve_min": hover_10_min,
        "hover_5_reserve_min": hover_5_min,
        "hover_0_practical_min": hover_0_min,
        "hover_configured_reserve_min": hover_20_min,
        "correction_factor": _reserve_fraction_from_basis(battery_basis, 20),
        "legacy_input_battery_wh": legacy_battery_wh,
        "legacy_correction_factor": legacy_correction_factor,
        "legacy_hover_100_min": legacy_hover_100_min,
        "legacy_hover_configured_reserve_min": legacy_hover_configured_min,
        "legacy_hover_10_reserve_min": legacy_hover_configured_min * 1.125,
        "legacy_effective_energy_wh": legacy_battery_wh * legacy_correction_factor,
    }


def build_datalink_fitted_model_suite(
    profile,
    calculation_result,
    hover_power_w,
    battery_wh,
    correction_factor,
    log_root=None,
    date_hint=DATALINK_MEASURED_CURVE_DATE_HINT,
):
    result = run_datalink_measured_curve_analysis(
        profile,
        calculation_result,
        hover_power_w,
        battery_wh,
        correction_factor,
        log_root=log_root,
        date_hint=date_hint,
        make_graph=False,
    )
    model_functions = {}
    model_params = {}
    model_audit = {}
    for measured_name, public_name in DATALINK_MEASURED_MODEL_NAME_MAP.items():
        if measured_name in result.get("model_functions", {}):
            model_functions[public_name] = result["model_functions"][measured_name]
        if measured_name in result.get("model_params", {}):
            params = dict(result["model_params"][measured_name])
            params["public_model_name"] = public_name
            params["source_model_name"] = measured_name
            model_params[public_name] = params
        audit = result.get("fit_audit", {}).get("models", {}).get(measured_name)
        if audit:
            model_audit[public_name] = audit

    power_reference_w = result.get("power_reference_w") or hover_power_w
    battery_basis = build_july3_firfir_battery_basis()
    battery_reserve_report = build_battery_reserve_report(
        power_reference_w,
        battery_wh,
        correction_factor,
        battery_basis,
    )
    # Because the sensor was on one parallel branch (6S1P), measured hover power
    # is half the actual aircraft power. Scale absolute Firfir fit-source values
    # to aircraft level with the branch multiplier. The reserve report and P/Ph
    # ratio remain branch-consistent, so the 40-minute baseline is unchanged.
    measured_hover_power_w = result.get("measured_hover_power_w")
    theoretical_hover_power_w = profile.get("theoretical_hover_power_w")
    vehicle_measured_hover_power_w = (
        measured_hover_power_w * FIRFIR_BATTERY_PARALLEL_ARMS
        if measured_hover_power_w
        else None
    )
    full_pack_usable_energy_wh = (
        battery_basis.get("usable_energy_wh", 0.0) * FIRFIR_BATTERY_PARALLEL_ARMS
    )
    # Reality/efficiency ratio at aircraft level: actual / theoretical hover.
    # The former one-branch value was below theory and physically impossible.
    if vehicle_measured_hover_power_w and theoretical_hover_power_w:
        datalink_efficiency_ratio = (
            vehicle_measured_hover_power_w / theoretical_hover_power_w
        )
    else:
        datalink_efficiency_ratio = None
    range_time_basis = {
        "label": "6S 25.2Ah measured usable capacity / July3 calibrated hover",
        "source": "3 July DataLink hover + 25.2 Ah measured usable capacity",
        "power_reference_w": power_reference_w,
        "battery_basis": battery_basis,
        "usable_energy_wh": battery_basis.get("usable_energy_wh", 0.0),
        "reserve_fractions": battery_basis.get("reserve_fractions", {}),
    }
    if vehicle_measured_hover_power_w and full_pack_usable_energy_wh:
        range_time_basis["equivalent_full_pack"] = {
            "power_reference_w": vehicle_measured_hover_power_w,
            "usable_energy_wh": full_pack_usable_energy_wh,
            "parallel_arms": FIRFIR_BATTERY_PARALLEL_ARMS,
            "note": "Equivalent only: energy and power are both multiplied by the same parallel-arm count.",
        }

    return {
        "source_result": result,
        "empirical_curve": result.get("empirical_curve", {}),
        "observations": result.get("speed_bin_observations", []),
        "power_reference_w": power_reference_w,
        "measured_hover_power_w": measured_hover_power_w,
        "vehicle_measured_hover_power_w": vehicle_measured_hover_power_w,
        "full_pack_usable_energy_wh": full_pack_usable_energy_wh,
        "battery_parallel_arms": FIRFIR_BATTERY_PARALLEL_ARMS,
        "fit_theoretical_hover_power_w": theoretical_hover_power_w,
        "datalink_efficiency_ratio": datalink_efficiency_ratio,
        "utip_ms": result.get("utip_ms"),
        "model_profile": result.get("model_profile", profile),
        "model_functions": model_functions,
        "model_params": model_params,
        "model_audit": model_audit,
        "battery_qc_report": result.get("battery_qc_report", {}),
        "battery_basis": battery_basis,
        "battery_reserve_report": battery_reserve_report,
        "range_time_basis": range_time_basis,
        "sync_report": result.get("sync_report", []),
    }


def print_datalink_fit_suite_summary(suite):
    empirical_curve = suite.get("empirical_curve", {})
    battery = suite.get("battery_qc_report", {})
    reserve = suite.get("battery_reserve_report", {})
    print("\nDataLink fit suite:")
    print(
        f"  P_hover(DataLink, measured branch)={suite.get('power_reference_w', 0.0):.1f} W"
    )
    if suite.get("vehicle_measured_hover_power_w"):
        arms = suite.get("battery_parallel_arms", FIRFIR_BATTERY_PARALLEL_ARMS)
        print(
            f"  P_hover(full aircraft, 6S{arms}P = {arms} branches)"
            f"={suite['vehicle_measured_hover_power_w']:.1f} W"
            f"  [sensor measured one of {arms} branches; scaled x{arms}]"
        )
    if suite.get("full_pack_usable_energy_wh"):
        print(
            f"  Full-pack usable energy (6S2P)={suite['full_pack_usable_energy_wh']:.1f} Wh"
            "  [one-branch measurement x2]"
        )
    if suite.get("utip_ms") is not None:
        print(f"  Utip(DataLink RPM)={suite['utip_ms']:.1f} m/s")
    if empirical_curve.get("measured_points"):
        print(
            "  Fit target: stable DataLink speed bins "
            f"{empirical_curve['min_speed_ms']:.2f}-{empirical_curve['max_speed_ms']:.2f} m/s, "
            f"n={empirical_curve.get('sample_count_total', 0)}"
        )
    print("  Stadium voltage and the 6.04 m/s pitch anchor are not fit targets.")

    print("\nBATT QC:")
    print(f"  BAT rows: {battery.get('bat_rows', 0)}")
    if battery.get("voltr_start_v") is not None:
        print(
            f"  VoltR: {battery['voltr_start_v']:.2f} -> "
            f"{battery.get('voltr_end_v', battery['voltr_start_v']):.2f} V"
        )
    print(f"  Direct current fit enabled: {battery.get('direct_current_fit_enabled')}")
    if battery.get("datalink_energy_wh") is not None:
        print(f"  DataLink integrated energy: {battery['datalink_energy_wh']:.1f} Wh")
    if battery.get("battery_energy_delta_raw") is not None:
        print(f"  BAT EnrgTot delta raw: {battery['battery_energy_delta_raw']:.4f}")
    for warning in battery.get("warnings", []):
        print(f"  [QC] {warning}")
    basis = reserve.get("battery_basis") or suite.get("battery_basis") or {}
    if reserve.get("hover_10_reserve_min") is not None:
        print("\nFlight time/range battery basis:")
        print(
            f"  {basis.get('label', 'battery usable capacity')}: "
            f"{basis.get('usable_energy_wh', 0.0):.1f} Wh "
            f"({basis.get('source', 'source not recorded')})"
        )
        print(
            "  Hover check (DataLink battery basis): "
            f"%20={reserve['hover_20_reserve_min']:.1f} dk, "
            f"%10={reserve['hover_10_reserve_min']:.1f} dk, "
            f"%5={reserve['hover_5_reserve_min']:.1f} dk, "
            f"practical 0%={reserve['hover_0_practical_min']:.1f} min"
        )
        print(
            "  Legacy input audit (not plotted): "
            f"{reserve['legacy_input_battery_wh']:.1f} Wh * "
            f"CF {reserve['legacy_correction_factor']:.3f}; "
            "the DataLink battery basis above is used for graph/table durations."
        )


def format_datalink_fit_method_report(
    suite, selected_models, range_time_basis_override=None
):
    result = suite.get("source_result", {})
    empirical = suite.get("empirical_curve", {})
    battery = suite.get("battery_qc_report", {})
    range_time_basis = range_time_basis_override or suite.get("range_time_basis", {})
    reserve = range_time_basis.get("reserve_report") or suite.get(
        "battery_reserve_report", {}
    )
    battery_basis = (
        range_time_basis.get("battery_basis")
        or suite.get("battery_basis")
        or reserve.get("battery_basis", {})
    )
    range_time_power_w = (
        range_time_basis.get("power_reference_w")
        or suite.get("power_reference_w")
        or 0.0
    )
    lines = [
        "# DataLink Fit Method Report",
        "",
        "## Data Sources",
        "",
        f"- DataLink/ArduPilot joined samples: `{result.get('joined_sample_count', 0)}`",
        f"- Fit power reference (one sensed branch): `{suite.get('power_reference_w', 0.0):.1f} W`",
        f"- Mechanical-RPM Utip: `{suite.get('utip_ms', 0.0):.1f} m/s`",
        f"- RPM conversion: raw eRPM/10 multiplied by `10/21 = {DATALINK_RPM_SCALE:.9f}`",
        f"- Measured speed range: `{empirical.get('min_speed_ms')}` - `{empirical.get('max_speed_ms')}` m/s",
        f"- Stable measured-bin samples: `{empirical.get('sample_count_total', 0)}`",
        f"- BATT rows: `{battery.get('bat_rows', 0)}`",
        f"- BATT direct-current fit enabled: `{battery.get('direct_current_fit_enabled')}`",
        f"- Range/time basis: `{range_time_basis.get('label', battery_basis.get('label', 'not recorded'))}`",
        f"- Range/time hover basis: `{range_time_power_w:.1f} W`",
        f"- Usable battery energy: `{battery_basis.get('usable_energy_wh', 0.0):.1f} Wh`",
        "",
        "BATT log is used as voltage/energy sanity evidence. Direct BATT current is not used as a fit target unless QC enables it.",
        "",
        "## Battery Basis for Flight Time",
        "",
        range_time_basis.get(
            "description",
            "The fitted P(v) curves are converted to endurance/range with the recorded range/time basis, not the legacy menu `battery_wh * CF` value.",
        ),
        "",
        f"- Source: `{battery_basis.get('source', 'not recorded')}`",
        f"- Measured usable capacity: `{battery_basis.get('usable_capacity_ah', 0.0):.1f} Ah`",
        f"- Measured usable energy: `{battery_basis.get('usable_energy_wh', 0.0):.1f} Wh`",
        f"- Datasheet nominal energy: `{battery_basis.get('datasheet_nominal_energy_wh', 0.0):.1f} Wh`",
        f"- Calibrated hover power: `{range_time_power_w:.1f} W`",
        f"- Hover %20 reserve: `{reserve.get('hover_20_reserve_min', 0.0):.1f} min`",
        f"- Hover %10 reserve: `{reserve.get('hover_10_reserve_min', 0.0):.1f} min`",
        f"- Hover %5 reserve: `{reserve.get('hover_5_reserve_min', 0.0):.1f} min`",
        f"- Hover practical 0%: `{reserve.get('hover_0_practical_min', 0.0):.1f} min`",
        f"- Legacy menu audit, not used for these graphs: `{reserve.get('legacy_input_battery_wh', 0.0):.1f} Wh * CF {reserve.get('legacy_correction_factor', 0.0):.3f}`",
        "",
        "## Fit Equations",
        "",
        "Common terms:",
        "",
        "```text",
        "profile(v) = 1 + 3 v^2 / U_tip^2",
        "induced(v) = sqrt(sqrt(1 + v^4/(4 v0^4)) - v^2/(2 v0^2))",
        "```",
        "",
        "Zeng DataLink fit:",
        "",
        "```text",
        "P(v)/P_h = f0*profile(v) + (1-f0)*induced(v) + k_par*v^3",
        "fit parameters: f0, k_par",
        "```",
        "",
        "Faessler drag-constrained DataLink fit:",
        "",
        "```text",
        "F_drag = 0.5*rho*C_DA_body*v^2 + lambda*v",
        "P(v)/P_h = f0*profile(v) + (1-f0)*induced(v)",
        "          + drag_scale*(k_body*v^3 + k_rotor*v^2)",
        "fit parameters: f0, drag_scale",
        "```",
        "",
        "Kirschstein component DataLink fit:",
        "",
        "```text",
        "P_base = P_air + P_lift + P_profile + P_hotel",
        "P(v)/P_h = P_base/P_h + induced_relief_scale*(induced(v)-1) + extra_cubic_k*v^3",
        "fit parameters: induced_relief_scale, extra_cubic_k",
        "```",
        "",
        "## Selected Model Parameters",
        "",
        "| model | parameters |",
        "|---|---|",
    ]
    keys = [
        "v0_ms",
        "utip_ms",
        "f0",
        "induced_fraction",
        "k_par",
        "body_cda_fit_m2",
        "lambda_n_per_ms",
        "drag_scale",
        "induced_relief_scale",
        "extra_cubic_k",
        "p_profile_hover_w",
        "lift_power_per_newton",
    ]
    for model_name in selected_models:
        params = suite.get("model_params", {}).get(model_name, {})
        parts = []
        for key in keys:
            if key not in params:
                continue
            value = params[key]
            if isinstance(value, float):
                parts.append(f"{key}={value:.6g}")
            else:
                parts.append(f"{key}={value}")
        lines.append(f"| {model_name} | {'; '.join(parts)} |")
    lines.extend(
        [
            "",
            "## Graph Interpretation",
            "",
            "- `*_empirical_interpolation.png` shows measured DataLink bins and within-range interpolation only.",
            "- `*_power_ratio.png` shows selected fitted model curves with DataLink measured points and Bauersfeld reference markers.",
            f"- `*_range_time.png` converts those same power ratios into range/endurance using `{range_time_basis.get('label', battery_basis.get('label', 'the selected range/time basis'))}`.",
            "- Speeds beyond the measured range are analytic extrapolation, not new measurements.",
            "",
        ]
    )
    if battery.get("warnings"):
        lines.extend(
            [
                "## Battery QC Warnings",
                "",
            ]
        )
        for warning in battery["warnings"]:
            lines.append(f"- `{warning}`")
        lines.append("")
    return "\n".join(lines)


def write_datalink_fit_method_report(
    suite,
    selected_models,
    output_path=DATALINK_FIT_REPORT_PATH,
    range_time_basis_override=None,
):
    path = Path(output_path)
    path.write_text(
        format_datalink_fit_method_report(
            suite,
            selected_models,
            range_time_basis_override=range_time_basis_override,
        ),
        encoding="utf-8",
    )
    return path.resolve()


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
        lines.append(
            "Measured DataLink hover reference (one sensed branch): "
            f"`{result['measured_hover_power_w']:.1f} W`"
        )
    if result.get("power_reference_w"):
        lines.append(f"Power reference used: `{result['power_reference_w']:.1f} W`")
    if result.get("utip_ms"):
        lines.append(f"Mechanical-RPM Utip: `{result['utip_ms']:.1f} m/s`")
        lines.append(
            "RPM conversion: raw eRPM/10 multiplied by "
            f"`10/21 = {DATALINK_RPM_SCALE:.9f}`."
        )

    empirical_curve = result.get("empirical_curve", {})
    lines.extend(
        [
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
        ]
    )
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
    lines.extend(
        [
            "",
            "## Diagnostic Surrogate Fits",
            "",
            fit_audit.get("scope", ""),
            "",
            "| model | status | MAE | reasons | warnings |",
            "|---|---|---:|---|---|",
        ]
    )
    residuals = result.get("model_fit_residuals", {})
    for model_name, audit in fit_audit.get("models", {}).items():
        mae = _mean_abs_error(residuals.get(model_name, []))
        mae_text = f"{mae:.5f}" if mae is not None else ""
        lines.append(
            f"| {model_name} | {audit.get('status')} | {mae_text} | "
            f"{', '.join(audit.get('reasons', []))} | "
            f"{', '.join(audit.get('warnings', []))} |"
        )
    lines.extend(
        [
            "",
            "### Key fitted and derived parameters",
            "",
            "| model | parameters |",
            "|---|---|",
        ]
    )
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
    return profile - induced, speed_ms**3, power_ratio - induced, weight


def fit_weighted_zeng_ratio(
    v0_ms,
    utip_ms,
    observations,
    k_prior=None,
    k_prior_speed_ms=6.0,
    k_prior_weight=1.0,
    k_priors=None,
):
    rows = [
        _zeng_linear_row(
            obs["speed_ms"], obs["power_ratio"], v0_ms, utip_ms, obs["weight"]
        )
        for obs in observations
    ]
    if k_prior is not None and k_prior_weight > 0:
        rows.append(
            (0.0, k_prior_speed_ms**3, k_prior * k_prior_speed_ms**3, k_prior_weight)
        )
    if k_priors:
        for prior in k_priors:
            speed_ms = prior["speed_ms"]
            weight = prior.get("weight", 1.0)
            if speed_ms > 0 and weight > 0:
                rows.append((0.0, speed_ms**3, prior["k_par"] * speed_ms**3, weight))

    f0, k_par = _fit_two_parameter_weighted(rows)
    return {
        "v0_ms": v0_ms,
        "utip_ms": utip_ms,
        "f0": f0,
        "induced_fraction": 1.0 - f0,
        "k_par": k_par,
    }


def fit_observation_weighted_zeng(
    v0_ms, utip_ms, hover_power_w, theoretical_params, attitude_fit, observations
):
    k_prior = None
    k_prior_weight = 0.0
    k_priors = []
    if attitude_fit and attitude_fit.get("cda_m2"):
        rho = attitude_fit.get("rho", 1.225)
        for speed_bin in attitude_fit.get("speed_bins", []):
            k_bin = 0.5 * rho * speed_bin["cda_m2"] / hover_power_w
            k_priors.append(
                {
                    "speed_ms": speed_bin["speed_ms"],
                    "k_par": k_bin,
                    "weight": min(3.0, max(0.5, speed_bin["sample_count"] / 500.0)),
                    "sample_count": speed_bin["sample_count"],
                    "cda_m2": speed_bin["cda_m2"],
                }
            )
        if not k_priors:
            k_prior = 0.5 * rho * attitude_fit["cda_m2"] / hover_power_w
            k_prior_weight = 6.0

    if not observations:
        hover_split = theoretical_params["p0_mech"] / (
            theoretical_params["p0_mech"] + theoretical_params["pi_mech"]
        )
        # build_theoretical_zeng_params does not produce a k_par key. With no
        # observations, derive the parasite coefficient from the attitude-log
        # prior or, if absent, theoretical CdA (k = 0.5*rho*CdA / P_hover_ref).
        theoretical_k_par = (
            0.5
            * theoretical_params["rho"]
            * theoretical_params["cda_body_m2"]
            / theoretical_params["hover_power_reference_w"]
        )
        return {
            "v0_ms": v0_ms,
            "utip_ms": utip_ms,
            "f0": hover_split,
            "induced_fraction": 1.0 - hover_split,
            "k_par": k_prior if k_prior is not None else theoretical_k_par,
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
    params.update(
        {
            "fit_observations": observations,
            "k_prior": k_prior,
            "k_priors": k_priors,
            "attitude_fit": attitude_fit,
        }
    )
    return params


def estimate_faessler_drag_from_attitude_log(
    profile, min_speed_ms=3.0, max_speed_ms=7.2, max_accel_ms2=0.8, max_tilt_deg=25.0
):
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
        x_body = 0.5 * rho * speed_ms**2
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
        body_drag_n = 0.5 * rho * cda_fit_m2 * speed_ms**2
        rotor_drag_n = max(0.0, total_drag_n - body_drag_n)
        lambda_n_per_ms = rotor_drag_n / speed_ms if speed_ms > 0 else 0.0
        lambda_values.append(lambda_n_per_ms)
        total_drag_values.append(total_drag_n)
        body_drag_values.append(body_drag_n)
        rotor_drag_values.append(rotor_drag_n)
        bin_center = round(
            (math.floor(speed_ms / bin_width_ms) + 0.5) * bin_width_ms, 2
        )
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
        speed_bins.append(
            {
                "speed_ms": bin_center,
                "sample_count": len(values),
                "lambda_n_per_ms": _median(btrim),
                "lambda_p25_n_per_ms": _percentile(sorted_values, 0.25),
                "lambda_p75_n_per_ms": _percentile(sorted_values, 0.75),
            }
        )

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


def fit_faessler_drag_constrained_zeng(
    v0_ms,
    utip_ms,
    hover_power_w,
    theoretical_params,
    faessler_fit,
    voltage_anchor,
    observations=None,
):
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

    if len(observations) >= 2:
        rows = []
        for obs in observations:
            speed_ms = obs["speed_ms"]
            induced = zeng_induced_ratio(speed_ms, v0_ms)
            profile = zeng_profile_ratio(speed_ms, utip_ms)
            drag_shape = k_body * speed_ms**3 + k_rotor * speed_ms**2
            rows.append(
                (
                    profile - induced,
                    drag_shape,
                    obs["power_ratio"] - induced,
                    obs.get("weight", 1.0),
                )
            )
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
                - k_body * speed_ms**3
                - k_rotor * speed_ms**2
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
        + drag_scale * (params["k_body"] * v**3 + params["k_rotor"] * v**2)
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
    # Kirschstein (2020), Eq. (5) and Appendix A: R is total rotor disc area,
    # pi*r^2*n_rotor, not rotor radius (doi:10.1016/j.trd.2019.102209).
    # The 2022 corrigendum retains this area and specifies the factor 3 in
    # the forward-speed term below (doi:10.1016/j.trd.2022.103457).
    area_total_m2 = num_rotors * math.pi * radius_m**2
    p_profile_hover_w = (
        rho * area_total_m2 * utip_ms**3 * solidity_s * blade_drag / 8.0
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
    body_drag_n = 0.5 * rho * params["body_cda_fit_m2"] * v**2
    p_air_w = body_drag_n * v
    thrust_n = math.sqrt(params["weight_n"] ** 2 + body_drag_n**2)
    p_lift_w = params["lift_power_per_newton"] * thrust_n
    p_profile_w = params["p_profile_hover_w"] * (
        1.0 + 3.0 * v**2 / params["utip_ms"] ** 2
    )
    return p_air_w + p_lift_w + p_profile_w + params["p_hotel_w"]


def fit_kirschstein_all_data(
    profile, hover_power_reference_w, v0_ms, observations, faessler_fit=None
):
    params = build_kirschstein_params(profile, hover_power_reference_w, faessler_fit)
    rows = []
    for obs in observations:
        speed_ms = obs["speed_ms"]
        base_ratio = (
            power_kirschstein_component(speed_ms, params) / hover_power_reference_w
        )
        induced_relief_shape = zeng_induced_ratio(speed_ms, v0_ms) - 1.0
        cubic_shape = speed_ms**3
        rows.append(
            (
                induced_relief_shape,
                cubic_shape,
                obs["power_ratio"] - base_ratio,
                obs.get("weight", 1.0),
            )
        )

    try:
        induced_relief_scale, extra_cubic_k = _fit_two_parameter_weighted(rows)
    except ValueError:
        induced_relief_scale = 0.0
        extra_cubic_k = 0.0

    params.update(
        {
            "v0_ms": v0_ms,
            "induced_relief_scale": induced_relief_scale,
            "extra_cubic_k": extra_cubic_k,
            "fit_observations": observations,
        }
    )
    return params


def power_ratio_kirschstein_all_data(speed_ms, params):
    v = max(0.0, speed_ms)
    base_ratio = (
        power_kirschstein_component(v, params) / params["hover_power_reference_w"]
    )
    correction = (
        params.get("induced_relief_scale", 0.0)
        * (zeng_induced_ratio(v, params["v0_ms"]) - 1.0)
        + params.get("extra_cubic_k", 0.0) * v**3
    )
    return max(0.01, base_ratio + correction)


def estimate_cda_from_pitch(speed_ms, pitch_deg, mass_kg, rho=1.225):
    weight_n = mass_kg * 9.81
    drag_n = weight_n * math.tan(math.radians(abs(pitch_deg)))
    return 2.0 * drag_n / (rho * speed_ms**2)


# --- PHASE 4: PHYSICAL PARAMETER TRANSFER ---------------------------------
# Instead of copying the frozen Firfir P/Ph shape, solve dimensionless
# aerodynamic coefficients (delta*sigma, 1+k_induced, CdA, lambda/W, lift/N)
# from the fit, then rebuild all three model ratios using the entered aircraft's
# mass, disc area, and Utip. The transferable quantities between aircraft are
# the dimensionless coefficients, not the ratio curve itself.


def _disc_area_total_m2(profile):
    radius_m = profile["prop_diameter_inch"] * 0.0254 / 2.0
    return profile["num_rotors"] * math.pi * radius_m**2


def _decompose_hover_split_to_physical(f0, hover_power_vehicle_w, fit_dims, rho):
    """Convert the fitted hover split into dimensionless physical terms."""
    area_m2 = _disc_area_total_m2(fit_dims)
    weight_n = fit_dims["mass_kg"] * 9.81
    utip_ms = fit_dims["utip_ms"]
    p_profile_w = f0 * hover_power_vehicle_w
    p_induced_w = (1.0 - f0) * hover_power_vehicle_w
    delta_sigma_eff = 8.0 * p_profile_w / (rho * area_m2 * utip_ms**3)
    one_plus_k_induced = p_induced_w * math.sqrt(2.0 * rho * area_m2) / weight_n**1.5
    return delta_sigma_eff, one_plus_k_induced


def _rebuild_hover_components(
    delta_sigma_eff, one_plus_k_induced, apply_profile, utip_ms, rho
):
    area_m2 = _disc_area_total_m2(apply_profile)
    weight_n = apply_profile["mass_kg"] * 9.81
    p_profile_w = (delta_sigma_eff / 8.0) * rho * area_m2 * utip_ms**3
    p_induced_w = one_plus_k_induced * weight_n**1.5 / math.sqrt(2.0 * rho * area_m2)
    v0_ms = math.sqrt(weight_n / (2.0 * rho * area_m2))
    return p_profile_w, p_induced_w, v0_ms


def transfer_zeng_params_to_vehicle(
    zeng_params, fit_profile, hover_power_vehicle_w, apply_profile, apply_utip_ms
):
    rho = fit_profile.get("rho", 1.225)
    fit_dims = dict(fit_profile)
    fit_dims["utip_ms"] = zeng_params["utip_ms"]
    delta_sigma_eff, one_plus_k_induced = _decompose_hover_split_to_physical(
        zeng_params["f0"], hover_power_vehicle_w, fit_dims, rho
    )
    cda_parasite_m2 = 2.0 * zeng_params["k_par"] * hover_power_vehicle_w / rho
    p_profile_w, p_induced_w, v0_ms = _rebuild_hover_components(
        delta_sigma_eff, one_plus_k_induced, apply_profile, apply_utip_ms, rho
    )
    hover_pred_w = p_profile_w + p_induced_w
    return {
        "v0_ms": v0_ms,
        "utip_ms": apply_utip_ms,
        "f0": p_profile_w / hover_pred_w,
        "induced_fraction": p_induced_w / hover_pred_w,
        "k_par": 0.5 * rho * cda_parasite_m2 / hover_pred_w,
        "transfer": {
            "delta_sigma_eff": delta_sigma_eff,
            "one_plus_k_induced_eff": one_plus_k_induced,
            "cda_parasite_m2": cda_parasite_m2,
            "hover_power_pred_w": hover_pred_w,
        },
    }


def transfer_faessler_params_to_vehicle(
    faessler_params, fit_profile, hover_power_vehicle_w, apply_profile, apply_utip_ms
):
    rho = fit_profile.get("rho", 1.225)
    fit_dims = dict(fit_profile)
    fit_dims["utip_ms"] = faessler_params["utip_ms"]
    delta_sigma_eff, one_plus_k_induced = _decompose_hover_split_to_physical(
        faessler_params["f0"], hover_power_vehicle_w, fit_dims, rho
    )
    drag_scale = faessler_params.get("drag_scale", 1.0)
    cda_body_m2 = (
        2.0 * drag_scale * faessler_params["k_body"] * hover_power_vehicle_w / rho
    )
    lambda_vehicle_n_per_ms = (
        drag_scale * faessler_params["k_rotor"] * hover_power_vehicle_w
    )
    p_profile_w, p_induced_w, v0_ms = _rebuild_hover_components(
        delta_sigma_eff, one_plus_k_induced, apply_profile, apply_utip_ms, rho
    )
    hover_pred_w = p_profile_w + p_induced_w
    fit_weight_n = fit_profile["mass_kg"] * 9.81
    apply_weight_n = apply_profile["mass_kg"] * 9.81
    # Rotor huzursuzluk suruklenmesi (lambda*v) itki/agirlikla olceklenir.
    lambda_new_n_per_ms = lambda_vehicle_n_per_ms * apply_weight_n / fit_weight_n
    return {
        "v0_ms": v0_ms,
        "utip_ms": apply_utip_ms,
        "f0": p_profile_w / hover_pred_w,
        "induced_fraction": p_induced_w / hover_pred_w,
        "k_body": 0.5 * rho * cda_body_m2 / hover_pred_w,
        "k_rotor": lambda_new_n_per_ms / hover_pred_w,
        "drag_scale": 1.0,
        "transfer": {
            "delta_sigma_eff": delta_sigma_eff,
            "one_plus_k_induced_eff": one_plus_k_induced,
            "cda_body_m2": cda_body_m2,
            "lambda_n_per_ms": lambda_new_n_per_ms,
            "hover_power_pred_w": hover_pred_w,
        },
    }


def transfer_kirschstein_params_to_vehicle(
    kirschstein_params, hover_power_vehicle_w, apply_profile, apply_utip_ms
):
    kp = kirschstein_params
    rho = kp.get("rho", 1.225)
    p_hotel_w = kp.get("p_hotel_w", 0.0)
    # 1) Make the Firfir basis aircraft-level consistent. The original parameters
    #    mix a one-branch electrical reference (P_ref) with aircraft-level profile
    #    power; derive lift/N from full-aircraft hover power here.
    lift_power_per_newton = max(
        0.0,
        (hover_power_vehicle_w - kp["p_profile_hover_w"] - p_hotel_w) / kp["weight_n"],
    )
    base_fit = dict(kp)
    base_fit["lift_power_per_newton"] = lift_power_per_newton
    # 2) Rebase correction coefficients to the aircraft-level basis while keeping
    #    the original frozen calibration relationship.
    #    Refit against the Firfir ratio as the target.
    rows = []
    for i in range(101):
        v = 0.25 * i
        target = power_ratio_kirschstein_all_data(v, kp)
        base_ratio = power_kirschstein_component(v, base_fit) / hover_power_vehicle_w
        rows.append(
            (zeng_induced_ratio(v, kp["v0_ms"]) - 1.0, v**3, target - base_ratio, 1.0)
        )
    induced_relief_scale, extra_cubic_k = _fit_two_parameter_weighted(rows)

    # 3) Rebuild the components with the new aircraft geometry.
    apply_radius_m = apply_profile["prop_diameter_inch"] * 0.0254 / 2.0
    apply_weight_n = apply_profile["mass_kg"] * 9.81
    apply_area_m2 = _disc_area_total_m2(apply_profile)
    # Profile power scales with total disc area and tip speed cubed. Density,
    # solidity and blade drag retain the fitted configuration's values.
    geometry_ratio = (
        apply_profile["num_rotors"] * apply_radius_m**2 * apply_utip_ms**3
    ) / (kp["num_rotors"] * kp["radius_m"]**2 * kp["utip_ms"] ** 3)
    p_profile_new_w = kp["p_profile_hover_w"] * geometry_ratio
    params_new = {
        "rho": rho,
        "mass_kg": apply_profile["mass_kg"],
        "weight_n": apply_weight_n,
        "num_rotors": apply_profile["num_rotors"],
        "radius_m": apply_radius_m,
        "utip_ms": apply_utip_ms,
        "rotor_solidity_s": kp.get("rotor_solidity_s"),
        "blade_profile_drag_delta": kp.get("blade_profile_drag_delta"),
        "p_hotel_w": p_hotel_w,
        "body_area_m2": kp.get("body_area_m2"),
        "body_cda_fit_m2": kp["body_cda_fit_m2"],
        "body_cd_fit": kp.get("body_cd_fit"),
        "p_profile_hover_w": p_profile_new_w,
        "lift_power_per_newton": lift_power_per_newton,
    }
    hover_reference_new_w = power_kirschstein_component(0.0, params_new)
    cda_extra_m2 = 2.0 * extra_cubic_k * hover_power_vehicle_w / rho
    params_new.update(
        {
            "hover_power_reference_w": hover_reference_new_w,
            "v0_ms": math.sqrt(apply_weight_n / (2.0 * rho * apply_area_m2)),
            "induced_relief_scale": induced_relief_scale,
            "extra_cubic_k": 0.5 * rho * cda_extra_m2 / hover_reference_new_w,
            "transfer": {
                "lift_power_per_newton": lift_power_per_newton,
                "p_profile_hover_new_w": p_profile_new_w,
                "cda_extra_m2": cda_extra_m2,
                "hover_power_pred_w": hover_reference_new_w,
            },
        }
    )
    return params_new


def estimate_theoretical_utip_similarity(
    apply_mass_kg,
    apply_num_rotors,
    apply_prop_diameter_inch,
    fit_mass_kg,
    fit_num_rotors,
    fit_prop_diameter_inch,
    fit_utip_ms,
):
    """Estimate hover tip speed by scaling within a similar propeller family.

    The fit aircraft's measured per-rotor thrust and tip speed form the anchor;
    level-hover thrust is assumed to equal weight divided by rotor count.
    """
    if apply_mass_kg <= 0 or fit_mass_kg <= 0:
        raise ValueError("Mass values must be positive for tip-speed estimation.")
    thrust_per_rotor_kgf = apply_mass_kg / apply_num_rotors
    fit_thrust_per_rotor_kgf = fit_mass_kg / fit_num_rotors
    utip_ms = (
        fit_utip_ms
        * math.sqrt(thrust_per_rotor_kgf / fit_thrust_per_rotor_kgf)
        * (fit_prop_diameter_inch / apply_prop_diameter_inch)
    )
    rpm = utip_ms * 60.0 / (math.pi * apply_prop_diameter_inch * 0.0254)
    return {
        "utip_ms": utip_ms,
        "rpm": rpm,
        "thrust_per_rotor_g": thrust_per_rotor_kgf * 1000.0,
        "fit_thrust_per_rotor_g": fit_thrust_per_rotor_kgf * 1000.0,
        "prop_diameter_inch": apply_prop_diameter_inch,
        "fit_utip_ms": fit_utip_ms,
        "pct_diff_vs_fit": (utip_ms - fit_utip_ms) / fit_utip_ms * 100.0,
    }


def datasheet_rpm_from_thrust(prop_diameter_inch, thrust_g):
    """Map thrust to mechanical RPM using the KV190 28/29-inch load-test tables."""
    table = U8LITE_KV190_THRUST_RPM_TABLES.get(round(float(prop_diameter_inch), 1))
    if table is None:
        raise ValueError(
            f"No KV190 datasheet RPM table exists for a {prop_diameter_inch}\" propeller "
            "(currently supported: 28.0 and 29.0 inches)."
        )
    thrusts = [row[0] for row in table]
    rpms = [row[1] for row in table]
    return interpolate(thrust_g, thrusts, rpms), (thrusts[0], thrusts[-1])


def estimate_theoretical_utip_datasheet(
    apply_mass_kg,
    apply_num_rotors,
    apply_prop_diameter_inch,
    fit_mass_kg,
    fit_num_rotors,
    fit_prop_diameter_inch,
    fit_utip_ms,
):
    """Estimate fit-anchored hover tip speed from the KV190 RPM datasheet.

    Per-rotor thrust selects a mechanical RPM from the G28x9.2/G29x9.5 table.
    The resulting ratio is anchored to the measured fit-aircraft tip speed so
    an identity transfer returns that measurement exactly.
    """
    if apply_mass_kg <= 0 or fit_mass_kg <= 0:
        raise ValueError("Mass values must be positive for tip-speed estimation.")
    thrust_per_rotor_g = apply_mass_kg / apply_num_rotors * 1000.0
    fit_thrust_per_rotor_g = fit_mass_kg / fit_num_rotors * 1000.0
    rpm_datasheet, thrust_table_range_g = datasheet_rpm_from_thrust(
        apply_prop_diameter_inch, thrust_per_rotor_g
    )
    fit_rpm_datasheet, _ = datasheet_rpm_from_thrust(
        fit_prop_diameter_inch, fit_thrust_per_rotor_g
    )
    utip_datasheet_ms = tip_speed_from_rpm(apply_prop_diameter_inch, rpm_datasheet)
    fit_utip_datasheet_ms = tip_speed_from_rpm(
        fit_prop_diameter_inch, fit_rpm_datasheet
    )
    if fit_utip_datasheet_ms <= 0:
        raise ValueError("Could not calculate the datasheet fit-point tip speed.")
    datalink_scale = fit_utip_ms / fit_utip_datasheet_ms
    utip_ms = utip_datasheet_ms * datalink_scale
    return {
        "utip_ms": utip_ms,
        "utip_datasheet_ms": utip_datasheet_ms,
        "rpm_datasheet": rpm_datasheet,
        "fit_utip_datasheet_ms": fit_utip_datasheet_ms,
        "fit_rpm_datasheet": fit_rpm_datasheet,
        "datalink_scale": datalink_scale,
        "thrust_per_rotor_g": thrust_per_rotor_g,
        "fit_thrust_per_rotor_g": fit_thrust_per_rotor_g,
        "thrust_table_range_g": thrust_table_range_g,
        "prop_diameter_inch": apply_prop_diameter_inch,
        "fit_utip_ms": fit_utip_ms,
        "pct_diff_vs_fit": (utip_ms - fit_utip_ms) / fit_utip_ms * 100.0,
    }


def build_transferred_model_suite(suite, apply_profile, apply_utip_ms=None):
    """Transfer the Firfir fit to another aircraft using physical parameters.

    Matching geometry and tip speed recover Zeng/Faessler curves analytically;
    Kirschstein retains a small refit residual (tested below 0.02 in P/Ph).
    Battery
    capacity does not change P/Ph shape, but battery-induced mass changes must
    be reflected in ``apply_profile``.
    """
    fit_profile = suite.get("model_profile") or {}
    model_params = suite.get("model_params", {})
    power_reference_w = suite.get("power_reference_w")
    if not power_reference_w:
        raise ValueError("Transfer requires a fitted hover reference (power_reference_w).")
    arms = suite.get("battery_parallel_arms") or 1
    hover_power_vehicle_w = power_reference_w * arms
    fit_utip_ms = suite.get("utip_ms") or fit_profile.get("utip_ms")
    utip_ms = apply_utip_ms or apply_profile.get("utip_ms") or fit_utip_ms
    if not utip_ms or utip_ms <= 0:
        raise ValueError("Transfer requires a valid Utip value.")

    model_functions = {}
    transferred_params = {}
    zeng_source = model_params.get("zeng_datalink_fit")
    if zeng_source:
        params = transfer_zeng_params_to_vehicle(
            zeng_source, fit_profile, hover_power_vehicle_w, apply_profile, utip_ms
        )
        model_functions["zeng_datalink_fit"] = (
            lambda v, p=params: power_ratio_bauersfeld_anchored_zeng(v, p)
        )
        transferred_params["zeng_datalink_fit"] = params
    faessler_source = model_params.get("faessler_datalink_fit")
    if faessler_source:
        params = transfer_faessler_params_to_vehicle(
            faessler_source, fit_profile, hover_power_vehicle_w, apply_profile, utip_ms
        )
        model_functions["faessler_datalink_fit"] = (
            lambda v, p=params: power_ratio_faessler_drag_constrained_zeng(v, p)
        )
        transferred_params["faessler_datalink_fit"] = params
    kirschstein_source = model_params.get("kirschstein_datalink_fit")
    if kirschstein_source:
        params = transfer_kirschstein_params_to_vehicle(
            kirschstein_source, hover_power_vehicle_w, apply_profile, utip_ms
        )
        model_functions["kirschstein_datalink_fit"] = (
            lambda v, p=params: power_ratio_kirschstein_all_data(v, p)
        )
        transferred_params["kirschstein_datalink_fit"] = params

    if not model_functions:
        raise ValueError(
            "No fitted parameters (model_params) are available for transfer; "
            "the suite must come from a real DataLink fit."
        )

    return {
        "model_functions": model_functions,
        "model_params": transferred_params,
        "apply_profile": apply_profile,
        "apply_utip_ms": utip_ms,
        "fit_utip_ms": fit_utip_ms,
        "fit_hover_power_vehicle_w": hover_power_vehicle_w,
        "battery_parallel_arms": arms,
    }


def print_transfer_summary(transfer):
    apply_profile = transfer.get("apply_profile", {})
    print("\n--- PHYSICAL PARAMETER TRANSFER (Phase 4) ---")
    print(
        "  The ratio curves were rebuilt from fitted dimensionless coefficients "
        "and the entered aircraft geometry."
    )
    print(
        f"  Applied aircraft: {apply_profile.get('vehicle_name', '?')}, "
        f"{apply_profile.get('mass_kg', 0.0):.2f} kg, "
        f"{apply_profile.get('num_rotors', 0)} rotor x "
        f"{apply_profile.get('prop_diameter_inch', 0.0):.1f}\" propeller, "
        f"Utip={transfer.get('apply_utip_ms', 0.0):.1f} m/s"
    )
    for name, params in transfer.get("model_params", {}).items():
        info = params.get("transfer", {})
        line = (
            f"  {name}: v0={params.get('v0_ms', 0.0):.2f} m/s, "
            f"P_hover(pred)={info.get('hover_power_pred_w', 0.0):.0f} W"
        )
        if "cda_parasite_m2" in info:
            line += (
                f", delta*sigma={info['delta_sigma_eff']:.5f}, "
                f"1+k_ind={info['one_plus_k_induced_eff']:.3f}, "
                f"CdA={info['cda_parasite_m2']:.4f} m2"
            )
        elif "cda_body_m2" in info:
            line += (
                f", CdA_body={info['cda_body_m2']:.4f} m2, "
                f"lambda={info['lambda_n_per_ms']:.3f} N/(m/s)"
            )
        elif "lift_power_per_newton" in info:
            line += (
                f", lift/N={info['lift_power_per_newton']:.3f} W/N, "
                f"P_profil={info['p_profile_hover_new_w']:.0f} W"
            )
        print(line)
    print(
        "  Note: P_hover(pred) is a cross-check; absolute endurance and range still "
        "use the entered hover power and battery."
    )


def build_july3_firfir_battery_basis():
    # This basis represents the single sensed branch (6S1P). Measured hover power
    # (~758 W) also comes from that branch, so their ratio correctly gives the
    # 40-minute baseline. The actual pack is 6S2P: full usable energy is this
    # value times FIRFIR_BATTERY_PARALLEL_ARMS (~1119 Wh). Using full-pack energy
    # requires doubling measured hover power too, or endurance would double.
    usable_energy_wh = (
        FIRFIR_BATTERY_CELLS
        * FIRFIR_BATTERY_NOMINAL_V_PER_CELL
        * FIRFIR_BATTERY_MEASURED_USABLE_AH
    )
    nominal_energy_wh = (
        FIRFIR_BATTERY_CELLS
        * FIRFIR_BATTERY_NOMINAL_V_PER_CELL
        * FIRFIR_BATTERY_DATASHEET_NOMINAL_AH
    )
    return {
        "label": "6S1P sensed branch, 25.2 Ah measured usable; full 6S2P pack x2",
        "source": "3 July 2026 battery analysis and bundled flight logs",
        "cells": FIRFIR_BATTERY_CELLS,
        "nominal_v_per_cell": FIRFIR_BATTERY_NOMINAL_V_PER_CELL,
        "usable_capacity_ah": FIRFIR_BATTERY_MEASURED_USABLE_AH,
        "usable_energy_wh": usable_energy_wh,
        "datasheet_nominal_capacity_ah": FIRFIR_BATTERY_DATASHEET_NOMINAL_AH,
        "datasheet_nominal_energy_wh": nominal_energy_wh,
        "reserve_fractions": {
            "20": 0.80,
            "10": 0.90,
            "5": 0.95,
            "0_practical": 1.00,
        },
    }


def build_applied_battery_basis(nominal_energy_wh, label=None):
    """Scale nominal energy by the measured 3 July usable-capacity fraction."""
    usable_energy_wh = nominal_energy_wh * FIRFIR_BATTERY_USABLE_FRACTION
    return {
        "label": label
        or f"Entered usable battery ({FIRFIR_BATTERY_USABLE_FRACTION * 100:.1f}% of nominal)",
        "source": "3 July Firfir usable fraction applied to the entered battery",
        "usable_energy_wh": usable_energy_wh,
        "datasheet_nominal_energy_wh": nominal_energy_wh,
        "usable_fraction_of_nominal": FIRFIR_BATTERY_USABLE_FRACTION,
        "reserve_fractions": {
            "20": 0.80,
            "10": 0.90,
            "5": 0.95,
            "0_practical": 1.00,
        },
    }


def _reserve_fraction_from_basis(battery_basis, reserve_percent):
    reserve_fractions = battery_basis.get("reserve_fractions", {})
    key = str(int(reserve_percent))
    if key in reserve_fractions:
        return reserve_fractions[key]
    return max(0.0, 1.0 - reserve_percent / 100.0)


def calculate_flight_for_speed(
    speed_ms,
    power_ratio,
    hover_power_w,
    battery_wh,
    correction_factor,
    battery_basis=None,
):
    power_w = hover_power_w * power_ratio
    if battery_basis:
        energy_basis_wh = battery_basis["usable_energy_wh"]
        fraction_20 = _reserve_fraction_from_basis(battery_basis, 20)
        fraction_10 = _reserve_fraction_from_basis(battery_basis, 10)
        battery_basis_label = battery_basis.get("label", "battery usable capacity")
    else:
        energy_basis_wh = battery_wh
        fraction_20 = correction_factor
        fraction_10 = correction_factor * 1.125
        battery_basis_label = "legacy battery_wh * correction_factor"
    time_100_min = energy_basis_wh / power_w * 60.0
    time_20_min = time_100_min * fraction_20
    range_20_km = speed_ms * 3.6 * time_20_min / 60.0
    time_10_min = time_100_min * fraction_10
    range_10_km = speed_ms * 3.6 * time_10_min / 60.0
    return {
        "speed_ms": speed_ms,
        "power_ratio": power_ratio,
        "power_w": power_w,
        "battery_basis_label": battery_basis_label,
        "energy_basis_wh": energy_basis_wh,
        "reserve_20_fraction": fraction_20,
        "reserve_10_fraction": fraction_10,
        "time_100_min": time_100_min,
        "time_20_min": time_20_min,
        "range_20_km": range_20_km,
        "time_10_min": time_10_min,
        "range_10_km": range_10_km,
    }


def print_speed_table(title, rows):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(
        f"{'speed':>7} | {'P/Ph':>7} | {'power W':>9} | {'%20 min':>8} | {'%20 km':>8} | {'%10 min':>8} | {'%10 km':>8}"
    )
    print("-" * 78)
    for row in rows:
        print(
            f"{row['speed_ms']:7.2f} | {row['power_ratio']:7.3f} | {row['power_w']:9.1f} | "
            f"{row['time_20_min']:8.2f} | {row['range_20_km']:8.2f} | "
            f"{row['time_10_min']:8.2f} | {row['range_10_km']:8.2f}"
        )


def parse_speed_list(raw):
    speeds = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            speeds.append(float(part))
    return speeds


def ask_utip(prop_diameter_inch, default_utip=80.0):
    print("\nPropeller tip-speed input:")
    print("1) Enter RPM and calculate tip speed")
    print("2) Enter tip speed directly")
    selection = input("Selection [2]: ").strip() or "2"
    if selection == "1":
        rpm = float(input("Estimated hover RPM: ").strip())
        return tip_speed_from_rpm(prop_diameter_inch, rpm), rpm
    raw = input(f"Utip m/s [{default_utip}]: ").strip()
    return (float(raw) if raw else default_utip), None


def build_speed_model_profile(
    vehicle_choice,
    current_mass_kg,
    current_num_rotors,
    current_prop_diameter_inch,
    current_drag_area_cm2,
    require_theoretical=False,
):
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
    print("\nEnter the missing Zeng parameters for the current aircraft.")
    profile["utip_ms"], profile["hover_rpm_estimate"] = ask_utip(
        current_prop_diameter_inch, 80.0
    )

    if require_theoretical:
        profile["blade_count"] = int(input("Blade count [2]: ").strip() or "2")
        profile["rotor_solidity_s"] = float(
            input("Rotor solidity s [0.05]: ").strip() or "0.05"
        )
        profile["mean_blade_chord_m"] = (
            profile["rotor_solidity_s"]
            * math.pi
            * (current_prop_diameter_inch * 0.0254 / 2.0)
            / profile["blade_count"]
        )
        profile["blade_profile_drag_delta"] = float(
            input("Blade profile drag delta [0.012]: ").strip() or "0.012"
        )
        profile["induced_correction_k"] = float(
            input("Induced correction k [0.1]: ").strip() or "0.1"
        )
        profile["eta_propulsion"] = float(
            input("Eta propulsion [1.0]: ").strip() or "1.0"
        )
        profile["p_hotel_w"] = float(input("Hotel power W [0.0]: ").strip() or "0.0")
        default_cda = current_drag_area_cm2 / 10000.0
        profile["cda_body_m2"] = float(
            input(f"Body C_DA m2 [{default_cda:.4f}]: ").strip() or default_cda
        )
        profile["body_area_m2"] = current_drag_area_cm2 / 10000.0
    else:
        profile.update(
            {
                "blade_count": 2,
                "rotor_solidity_s": 0.05,
                "mean_blade_chord_m": 0.029,
                "blade_profile_drag_delta": 0.012,
                "induced_correction_k": 0.1,
                "eta_propulsion": 1.0,
                "p_hotel_w": 0.0,
                "cda_body_m2": current_drag_area_cm2 / 10000.0,
                "body_area_m2": current_drag_area_cm2 / 10000.0,
            }
        )
    return profile


def make_speed_sweep(
    model_functions, hover_power_w, battery_wh, correction_factor, battery_basis=None
):
    speeds = [0.1 + i * (24.9 / 249.0) for i in range(250)]
    sweep = {}
    for name, ratio_fn in model_functions.items():
        sweep[name] = [
            calculate_flight_for_speed(
                speed,
                ratio_fn(speed),
                hover_power_w,
                battery_wh,
                correction_factor,
                battery_basis=battery_basis,
            )
            for speed in speeds
        ]
    return sweep


def build_bauersfeld_reference_points(v_endurance, v_range):
    return [
        {
            "label": "Bauersfeld endurance reference",
            "speed_ms": v_endurance,
            "power_ratio": 0.914,
            "marker": "s",
            "color": "green",
        },
        {
            "label": "Bauersfeld range reference",
            "speed_ms": v_range,
            "power_ratio": 1.092,
            "marker": "D",
            "color": "red",
        },
    ]


def datalink_selection_slug(selected_models):
    selected = list(selected_models)
    if selected == list(DATALINK_FIT_MODEL_ORDER):
        return "all"
    if len(selected) == 1:
        return DATALINK_FIT_MODEL_SLUGS.get(selected[0], selected[0])
    return "selected"


def datalink_graph_output_paths(selected_models):
    # The empirical interpolation plot is intentionally omitted here. It is
    # produced only by the raw-data viewer (raw_datalink_empirical_interpolation.png).
    slug = datalink_selection_slug(selected_models)
    return {
        "power": f"datalink_{slug}_power_ratio.png",
        "range": f"datalink_{slug}_range_time.png",
    }


def _short_source_bins(obs):
    short_bins = [
        Path(name).stem.lstrip("0") or Path(name).stem
        for name in obs.get("source_bins", [])[:2]
    ]
    text = ",".join(short_bins)
    if len(obs.get("source_bins", [])) > 2:
        text += ",..."
    return text or "source?"


def plot_datalink_empirical_interpolation(
    empirical_curve, output_path, bauersfeld_points=None
):
    import matplotlib.pyplot as plt

    points = empirical_curve.get("measured_points", [])
    fig, ax = plt.subplots(figsize=(12, 7))
    if points:
        speeds = [obs["speed_ms"] for obs in points]
        ratios = [obs["power_ratio"] for obs in points]
        ax.plot(
            speeds,
            ratios,
            color="black",
            linewidth=1.5,
            label="DataLink linear interpolation",
        )
        ax.scatter(speeds, ratios, color="blue", label="DataLink measured stable bins")
        for idx, obs in enumerate(points):
            label = (
                f"n={obs.get('sample_count', 0)}, sf={obs.get('stable_fraction', 0.0):.2f}\n"
                f"BIN {_short_source_bins(obs)}"
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
    for point in bauersfeld_points or []:
        ax.scatter(
            [point["speed_ms"]],
            [point["power_ratio"]],
            marker=point.get("marker", "s"),
            color=point.get("color", "gray"),
            label=point["label"],
        )
    ax.set_xlabel("Speed [m/s]")
    ax.set_ylabel("P(V) / P_hover(DataLink)")
    ax.set_title("DataLink empirical interpolation with Bauersfeld references")
    ax.margins(y=0.18)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


def plot_datalink_power_ratio_comparison(
    model_functions, empirical_curve, bauersfeld_points, output_path
):
    import matplotlib.pyplot as plt

    speeds = [0.1 + i * (24.9 / 249.0) for i in range(250)]
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for name, ratio_fn in model_functions.items():
        ax.plot(speeds, [ratio_fn(speed) for speed in speeds], label=name)
    ax.scatter([0.0], [1.0], marker="o", color="black", label="hover reference")
    for obs in empirical_curve.get("measured_points", []):
        ax.scatter(
            [obs["speed_ms"]],
            [obs["power_ratio"]],
            marker="o",
            color="blue",
            alpha=0.85,
            label="DataLink measured bins"
            if obs is empirical_curve.get("measured_points", [None])[0]
            else None,
        )
        ax.annotate(
            f"n={obs.get('sample_count', 0)}, sf={obs.get('stable_fraction', 0.0):.2f}",
            (obs["speed_ms"], obs["power_ratio"]),
            textcoords="offset points",
            xytext=(5, 8),
            fontsize=7,
        )
    for point in bauersfeld_points:
        ax.scatter(
            [point["speed_ms"]],
            [point["power_ratio"]],
            marker=point.get("marker", "s"),
            color=point.get("color", "gray"),
            label=point["label"],
        )
    ax.set_xlabel("Speed [m/s]")
    ax.set_ylabel("P(V) / P_hover(DataLink)")
    ax.set_title("DataLink-fitted model P(V) comparison")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


def plot_datalink_range_time_comparison(
    model_functions,
    empirical_curve,
    bauersfeld_points,
    hover_power_w,
    battery_wh,
    correction_factor,
    output_path,
    battery_basis=None,
):
    import matplotlib.pyplot as plt

    sweep = make_speed_sweep(
        model_functions,
        hover_power_w,
        battery_wh,
        correction_factor,
        battery_basis=battery_basis,
    )
    fig, (ax_range, ax_time) = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
    for name, rows in sweep.items():
        speeds = [row["speed_ms"] for row in rows]
        ax_range.plot(speeds, [row["range_10_km"] for row in rows], label=name)
        ax_time.plot(speeds, [row["time_10_min"] for row in rows], label=name)

    measured_points = empirical_curve.get("measured_points", [])
    for obs in measured_points:
        row = calculate_flight_for_speed(
            obs["speed_ms"],
            obs["power_ratio"],
            hover_power_w,
            battery_wh,
            correction_factor,
            battery_basis=battery_basis,
        )
        label = "DataLink measured bins" if obs is measured_points[0] else None
        ax_range.scatter(
            [row["speed_ms"]],
            [row["range_10_km"]],
            color="blue",
            marker="o",
            label=label,
        )
        ax_time.scatter(
            [row["speed_ms"]],
            [row["time_10_min"]],
            color="blue",
            marker="o",
            label=label,
        )

    for point in bauersfeld_points:
        row = calculate_flight_for_speed(
            point["speed_ms"],
            point["power_ratio"],
            hover_power_w,
            battery_wh,
            correction_factor,
            battery_basis=battery_basis,
        )
        ax_range.scatter(
            [row["speed_ms"]],
            [row["range_10_km"]],
            marker=point.get("marker", "s"),
            color=point.get("color", "gray"),
            label=point["label"],
        )
        ax_time.scatter(
            [row["speed_ms"]],
            [row["time_10_min"]],
            marker=point.get("marker", "s"),
            color=point.get("color", "gray"),
            label=point["label"],
        )

    ax_range.set_ylabel("Range at 10% reserve [km]")
    if battery_basis:
        ax_range.set_title(
            f"Range/time basis: {battery_basis.get('label', 'battery usable capacity')} / "
            f"P_hover={hover_power_w:.1f} W"
        )
    ax_range.grid(True, alpha=0.3)
    ax_range.legend(fontsize=8)
    ax_time.set_xlabel("Speed [m/s]")
    ax_time.set_ylabel("Endurance at 10% reserve [min]")
    ax_time.grid(True, alpha=0.3)
    ax_time.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    return Path(output_path).resolve()


# Model-selection summary:
# 1) legacy_parabola_baseline:
#    Includes: old baseline through hover and Bauersfeld endurance/range points.
#    Excludes: Zeng/rotor physics, derivative constraints, and log data; rough comparison only.
# 2) bauersfeld_anchored_zeng:
#    Includes: P(0)=1, P(ve)=0.914, P(vr)=1.092 and a Zeng-like induced/profile/parasite shape.
#    Excludes: attitude logs and stadium voltage data; Zeng extrapolation above 10.7 m/s.
# 3) theoretical_zeng_pitch_CDA:
#    Includes: raw theoretical Zeng rotor terms and CDA from 6.04 m/s at 4 degrees pitch.
#    Excludes: datasheet hover power, so P(0)/P_hover is not 1. Diagnostic, not primary.
# 4) hybrid_calibrated_zeng_fit:
#    Includes: Bauersfeld and stadium-voltage anchors plus log-band CDA priors.
#    Excludes: full validation where power/current is unmeasured; high speed is extrapolated.
# 5) pure_zeng_flight_fit:
#    Includes: normalized Zeng form, log-band CDA, and the stadium 6 m/s P/Ph anchor.
#    Excludes: forced Bauersfeld ve/vr anchors and free tuning of rotor parameters.
# 6) faessler_drag_constrained_zeng:
#    Includes: separates log-derived tilt resistance into body and linear rotor drag.
#    Excludes: current/RPM power; high speed remains extrapolated.
# 7) kirschstein_component_benchmark:
#    Includes: separate Pair, Plift, Pprofile, and Pint components.
#    Excludes: forcing the 6 m/s voltage anchor; retained as a benchmark.
# 8) datalink_empirical_pv:
#    Includes: July 3 DataLink and ArduPilot measured speed bins.
#    Excludes: no values are inferred outside the measured range.


def parse_datalink_model_selection(raw):
    raw = (raw or "4").strip().lower()
    all_models = list(DATALINK_FIT_MODEL_ORDER)
    if raw in {"4", "all", "*"}:
        return all_models

    aliases = {
        "1": "zeng_datalink_fit",
        "zeng": "zeng_datalink_fit",
        "zeng_datalink_fit": "zeng_datalink_fit",
        "2": "faessler_datalink_fit",
        "faessler": "faessler_datalink_fit",
        "faessler_datalink_fit": "faessler_datalink_fit",
        "3": "kirschstein_datalink_fit",
        "kirschstein": "kirschstein_datalink_fit",
        "kirschstein_datalink_fit": "kirschstein_datalink_fit",
    }
    selected = []
    for part in raw.replace(";", ",").split(","):
        key = part.strip().lower()
        if not key:
            continue
        model_name = aliases.get(key)
        if model_name and model_name not in selected:
            selected.append(model_name)
    return selected or all_models


def print_datalink_model_descriptions():
    print("\n--- DataLink-fitted model selection ---")
    print("  1) Zeng DataLink fit")
    print("       Source: 3 July DataLink V*I/RPM and stable ArduPilot speed bins.")
    print(
        "       Fit: f0 and k_par; P_hover and U_tip come from DataLink, v0 from physics."
    )
    print(
        "       Use: analytical extrapolation with Zeng induced/profile/parasite terms."
    )
    print("  2) Faessler drag-constrained DataLink fit")
    print(
        "       Source: DataLink power bins plus body C_DA and rotor-drag lambda from attitude."
    )
    print(
        "       Fit: f0 and drag_scale; measured body drag/lambda are held fixed."
    )
    print(
        "       Use: carries the measured tilt/drag effect into higher speeds."
    )
    print("  3) Kirschstein component DataLink fit")
    print(
        "       Source: component model, DataLink power bins, and attitude-derived drag split."
    )
    print(
        "       Fit: induced_relief_scale and extra_cubic_k; base components are reported."
    )
    print(
        "       Use: component benchmark against Zeng; correction terms are audited separately."
    )
    print("  4) All DataLink-fitted models")
    print(
        "       Plots all three models; their spread indicates extrapolation uncertainty."
    )
    print(
        "  Each selection can produce interpolation, P(V)/P_hover, and range/endurance plots."
    )
    print("  Bauersfeld is a reference marker, not a fit target.")


def run_preset_fit_apply_to_vehicle(
    speeds,
    fit_profile,
    fit_result,
    model_choice,
    apply_hover_power_w,
    apply_battery_wh,
    apply_correction_factor,
    make_graph,
    datalink_log_root=None,
    datalink_date_hint=DATALINK_MEASURED_CURVE_DATE_HINT,
    apply_result=None,
    apply_profile=None,
    apply_utip_ms=None,
    apply_utip_mode=None,
):
    # The model is always fitted to Firfir DataLink data through fit_profile.
    # When apply_profile is provided, the dimensionless aerodynamic coefficients
    # are rebuilt with the entered aircraft's physics so the ratio curves respond
    # to that aircraft. Otherwise the frozen Firfir shape is retained. In both
    # cases, absolute power, time, and range use the entered aircraft's own hover
    # power and battery. The calibrated July 3 Firfir basis is reported only as
    # calibration-source information, not as the application result.
    apply_result = apply_result or fit_result
    v_endurance = apply_result["optimal_endurance_speed_ms"]
    v_range = apply_result["optimal_speed_ms"]

    selected = parse_datalink_model_selection(model_choice)
    suite = build_datalink_fitted_model_suite(
        fit_profile,
        fit_result,
        apply_hover_power_w,
        apply_battery_wh,
        apply_correction_factor,
        log_root=datalink_log_root,
        date_hint=datalink_date_hint,
    )
    model_functions = suite["model_functions"]
    transfer = None
    if apply_profile and apply_utip_mode == "theoretical_datasheet":
        # Option: derive Utip for the entered mass from the KV190 datasheet
        # load-test RPM curve (G28x9.2 or G29x9.5, matching the propeller).
        fit_measured_utip = suite.get("utip_ms") or fit_profile.get("utip_ms")
        apply_prop_inch = apply_profile.get("prop_diameter_inch", 29.0)
        theo = None
        try:
            theo = estimate_theoretical_utip_datasheet(
                apply_profile["mass_kg"],
                apply_profile["num_rotors"],
                apply_prop_inch,
                fit_profile["mass_kg"],
                fit_profile["num_rotors"],
                fit_profile["prop_diameter_inch"],
                fit_measured_utip,
            )
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            print(
                f"WARNING: Could not calculate datasheet tip speed ({exc}); "
                "trying the propeller-similarity fallback."
            )
            try:
                theo = estimate_theoretical_utip_similarity(
                    apply_profile["mass_kg"],
                    apply_profile["num_rotors"],
                    apply_prop_inch,
                    fit_profile["mass_kg"],
                    fit_profile["num_rotors"],
                    fit_profile["prop_diameter_inch"],
                    fit_measured_utip,
                )
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc2:
                print(
                    f"WARNING: Could not calculate theoretical tip speed ({exc2}); "
                    "using the fit aircraft's measured value."
                )
        if theo:
            apply_utip_ms = theo["utip_ms"]
            print(
                "\n--- THEORETICAL TIP SPEED (U8 Lite KV190 datasheet, "
                f"{apply_prop_inch:.0f}\" propeller) ---"
            )
            print(
                f"  Hover thrust per rotor: {theo['thrust_per_rotor_g']:.0f} g "
                f"(fit aircraft: {theo['fit_thrust_per_rotor_g']:.0f} g)"
            )
            if "rpm_datasheet" in theo:
                print(
                    f"  Datasheet mechanical RPM: {theo['rpm_datasheet']:.0f} "
                    f"-> absolute tip speed {theo['utip_datasheet_ms']:.1f} m/s"
                )
            print(
                f"  Applied fit-anchored tip speed = {theo['utip_ms']:.1f} m/s"
            )
            print(
                f"  Difference from the Firfir measurement ({theo['fit_utip_ms']:.1f} m/s, "
                f"{fit_profile['prop_diameter_inch']:.0f}\" @ "
                f"{fit_profile['mass_kg']:.1f} kg): "
                f"%{theo['pct_diff_vs_fit']:+.1f}"
            )
            table_range = theo.get("thrust_table_range_g")
            if table_range and not (
                table_range[0] <= theo["thrust_per_rotor_g"] <= table_range[1]
            ):
                print(
                    "  WARNING: Per-rotor thrust is outside the datasheet range "
                    f"({table_range[0]:.0f}-{table_range[1]:.0f} g); RPM was clamped."
                )
            datalink_scale = theo.get("datalink_scale")
            if datalink_scale and not (0.8 <= datalink_scale <= 1.25):
                print(
                    "  WARNING: DataLink tip speed is "
                    f"{datalink_scale:.2f} times the datasheet mechanical value. "
                    "After DATALINK_RPM_SCALE correction this should be near 1.0; "
                    "a large difference indicates inconsistent fit-aircraft inputs "
                    "or parser scaling. Datasheet expectation: "
                    f"~{theo['fit_rpm_datasheet']:.0f} RPM, "
                    f"tip speed ~{theo['fit_utip_datasheet_ms']:.1f} m/s. The "
                    "theoretical value remains anchored to the fit scale."
                )
    if apply_profile:
        try:
            transfer = build_transferred_model_suite(
                suite, apply_profile, apply_utip_ms=apply_utip_ms
            )
        except (KeyError, ValueError, ZeroDivisionError) as exc:
            print(
                f"WARNING: Physical parameter transfer failed ({exc}); "
                "using the frozen Firfir ratio curves."
            )
        else:
            model_functions = transfer["model_functions"]
    graph_models = {
        name: model_functions[name] for name in selected if name in model_functions
    }
    fit_reference_hover_w = suite.get("power_reference_w") or apply_hover_power_w
    empirical_curve = suite.get("empirical_curve", {})

    typed_battery_basis = build_applied_battery_basis(
        apply_battery_wh,
        label="Entered aircraft usable energy",
    )
    range_time_basis = suite.get("range_time_basis", {})
    calibrated_battery_basis = (
        range_time_basis.get("battery_basis")
        or suite.get("battery_basis")
        or typed_battery_basis
    )
    calibrated_hover_power_w = (
        range_time_basis.get("power_reference_w")
        or suite.get("power_reference_w")
        or apply_hover_power_w
    )

    hover_scale = suite.get("datalink_efficiency_ratio")
    if not hover_scale or not math.isfinite(hover_scale) or hover_scale <= 0.0:
        hover_scale = 1.0
    result_hover_power_w = apply_hover_power_w * hover_scale
    result_battery_basis = typed_battery_basis
    if abs(hover_scale - 1.0) > 1e-6:
        result_mode = "datalink_calibrated_application"
        result_basis_label = "DataLink-calibrated entered vehicle basis"
        result_basis_source = (
            f"Entered theoretical hover power {apply_hover_power_w:.1f} W was "
            f"calibrated to {result_hover_power_w:.1f} W using Firfir's DataLink "
            f"measured/theoretical hover scale of {hover_scale:.3f}."
        )
    else:
        result_mode = "entered_vehicle_application"
        result_basis_label = "Entered-aircraft application basis"
        result_basis_source = (
            "No DataLink measured/theoretical hover scale was available; "
            "entered hover power was used directly."
        )
    result_reserve_report = build_battery_reserve_report(
        result_hover_power_w,
        apply_battery_wh,
        apply_correction_factor,
        result_battery_basis,
    )
    result_range_time_basis = {
        "mode": result_mode,
        "label": result_basis_label,
        "source": result_basis_source,
        "power_reference_w": result_hover_power_w,
        "battery_basis": result_battery_basis,
        "reserve_report": result_reserve_report,
        "description": (
            "The fitted P(v) ratios are converted to endurance/range with "
            f"`{result_basis_label}`. This is the same basis used by the "
            "console tables and range/time graph."
        ),
    }
    bauersfeld_points = build_bauersfeld_reference_points(v_endurance, v_range)

    print_datalink_fit_suite_summary(suite)

    # Calibration source (reported for information, not as the application result).
    print("\n--- MODEL CALIBRATION SOURCE (Firfir DataLink) ---")
    print(
        "The model was calibrated from Firfir flight data; the P/Ph curve comes from "
        f"these measurements (the {fit_reference_hover_w:.1f} W reference only normalizes it)."
    )
    if empirical_curve.get("measured_points"):
        print(
            "  Fit target: stable DataLink bins "
            f"{empirical_curve['min_speed_ms']:.2f}-{empirical_curve['max_speed_ms']:.2f} m/s, "
            f"n={empirical_curve.get('sample_count_total', 0)}"
        )
    print(
        "  Endurance/range uses the entered battery and the DataLink "
        f"measured/theoretical hover scale ({hover_scale:.3f})."
    )
    if transfer:
        print_transfer_summary(transfer)
        print(
            "  Note: The empirical interpolation belongs to the fit aircraft; "
            "transferred model curves are expected to depart from those points."
        )

    result_usable_wh = result_battery_basis["usable_energy_wh"]
    result_nominal_wh = result_battery_basis.get(
        "datasheet_nominal_energy_wh", apply_battery_wh
    )
    print(f"\n--- PRIMARY RESULT BASIS ({result_basis_label}) ---")
    print(f"  P_hover = {result_hover_power_w:.1f} W")
    print(
        f"  Battery = {result_battery_basis.get('label', 'entered usable battery')}: "
        f"{result_usable_wh:.1f} Wh usable ({result_nominal_wh:.1f} Wh nominal/equivalent)"
    )
    if result_reserve_report.get("hover_20_reserve_min") is not None:
        print(
            "  Hover check: "
            f"20%={result_reserve_report['hover_20_reserve_min']:.1f} min, "
            f"10%={result_reserve_report['hover_10_reserve_min']:.1f} min, "
            f"5%={result_reserve_report['hover_5_reserve_min']:.1f} min, "
            f"practical 0%={result_reserve_report['hover_0_practical_min']:.1f} min"
        )
    calibrated_usable_wh = calibrated_battery_basis["usable_energy_wh"]
    print("\n--- MODEL CALIBRATION BASIS (Firfir, 3 July; information only) ---")
    print(f"  P_hover(Firfir calibrated) = {calibrated_hover_power_w:.1f} W")
    print(
        f"  Battery(Firfir) = {calibrated_battery_basis.get('label', '3 July calibrated usable')}: "
        f"{calibrated_usable_wh:.1f} Wh usable"
    )
    print("\nSelected DataLink-fitted models: " + ", ".join(selected))

    print(f"\nDataLink empirical interpolation check ({result_basis_label}):")
    for speed in speeds:
        evaluation = evaluate_empirical_datalink_power_ratio(empirical_curve, speed)
        if evaluation["available"]:
            row = calculate_flight_for_speed(
                speed,
                evaluation["power_ratio"],
                result_hover_power_w,
                apply_battery_wh,
                apply_correction_factor,
                battery_basis=result_battery_basis,
            )
            print(
                f"  v={speed:.2f} m/s: P/Ph={evaluation['power_ratio']:.4f} "
                f"({evaluation['basis']}), P={row['power_w']:.1f} W, "
                f"20% time={row['time_20_min']:.1f} min, "
                f"20% range={row['range_20_km']:.2f} km"
            )
        else:
            min_speed_ms = evaluation.get("min_speed_ms")
            max_speed_ms = evaluation.get("max_speed_ms")
            if min_speed_ms is not None and max_speed_ms is not None:
                print(
                    f"  v={speed:.2f} m/s: outside measured interpolation "
                    f"({min_speed_ms:.2f}-{max_speed_ms:.2f} m/s); "
                    "using model extrapolation."
                )
            else:
                print(
                    f"  v={speed:.2f} m/s: no measured interpolation data; "
                    "using model extrapolation."
                )

    for model_name in selected:
        if model_name not in model_functions:
            continue
        rows = [
            calculate_flight_for_speed(
                speed,
                model_functions[model_name](speed),
                result_hover_power_w,
                apply_battery_wh,
                apply_correction_factor,
                battery_basis=result_battery_basis,
            )
            for speed in speeds
        ]
        print_speed_table(model_name, rows)

    report_path = write_datalink_fit_method_report(
        suite,
        selected,
        range_time_basis_override=result_range_time_basis,
    )

    graph_paths = {}
    if make_graph:
        output_paths = datalink_graph_output_paths(selected)
        try:
            graph_paths["power"] = plot_datalink_power_ratio_comparison(
                graph_models,
                empirical_curve,
                bauersfeld_points,
                output_paths["power"],
            )
            graph_paths["range"] = plot_datalink_range_time_comparison(
                graph_models,
                empirical_curve,
                bauersfeld_points,
                result_hover_power_w,
                apply_battery_wh,
                apply_correction_factor,
                output_paths["range"],
                battery_basis=result_battery_basis,
            )
            print("\nGraph outputs:")
            for path in graph_paths.values():
                print(f"* {path}")
            import matplotlib.pyplot as plt

            print("Opening plots with plt.show().")
            plt.show()
        except Exception as exc:
            print(f"Could not create graphs: {exc}")

    print(f"\nFit-method report: {report_path}")
    return {
        "selected_models": selected,
        "suite": suite,
        "transfer": transfer,
        "result_range_time_basis": result_range_time_basis,
        "graph_paths": graph_paths,
        "report_path": report_path,
    }


def calculate_real_energy_wh(total_cells, capacity_mah, battery_type="lihv"):
    if battery_type == "lihv":
        # Empirical LiHV energy adjustment established from this project's tests.
        nominal_voltage = 3.7 * 7.0 / 6.0
    elif battery_type == "lipo":
        nominal_voltage = 3.7
    elif battery_type == "liion":
        # This project's solid-state Li-ion pack charges to 4.3 V and uses 3.7 V nominal.
        nominal_voltage = 3.7
    else:
        nominal_voltage = 3.7
    return total_cells * nominal_voltage * (capacity_mah / 1000.0)


def run_datalink_raw_data_viewer(log_root, date_hint):
    import matplotlib.pyplot as plt

    print("\n--- Raw DataLink data viewer ---")
    try:
        # The analysis expects result["vi_h"]. Derive induced hover speed from
        # the preset physics (the old empty dictionary caused a KeyError).
        preset = dict(FIRFIR_SPEED_PRESET)
        vi_h = math.sqrt(
            preset["mass_kg"]
            * 9.81
            / (2.0 * preset.get("rho", 1.225) * _disc_area_total_m2(preset))
        )
        result = run_datalink_measured_curve_analysis(
            preset,
            {"vi_h": vi_h},
            1000.0,
            1000.0,
            1.0,
            log_root=log_root,
            date_hint=date_hint,
            make_graph=False,
        )
        if not result:
            print("Raw data could not be read or analyzed.")
            return

        empirical_curve = result.get("empirical_curve", {})

        plot_datalink_empirical_interpolation(
            empirical_curve,
            "raw_datalink_empirical_interpolation.png",
            bauersfeld_points=None,
        )

        plot_battery_voltage_timeline(
            result.get("battery_qc_report", {}).get("rows", []),
            result.get("sync_report", []),
            output_path="raw_datalink_battery_voltage.png",
        )

        print("\nCreated raw-data graphs (empirical curve and battery voltage).")
        print("Opening plots with plt.show().")
        plt.show()

    except Exception as exc:
        print(f"Raw-data viewer error: {exc}")


def _print_calculation(result):
    """Print the stable, public calculator output in a script-friendly form."""
    fields = (
        ("Induced hover velocity", "vi_h", "m/s"),
        ("Best-range speed", "optimal_speed_ms", "m/s"),
        ("Best-range flight time", "flight_time_min_range", "min"),
        ("Maximum range", "max_range_km", "km"),
        ("Best-endurance speed", "optimal_endurance_speed_ms", "m/s"),
        ("Maximum endurance", "max_endurance_min", "min"),
    )
    for label, key, unit in fields:
        print(f"{label}: {result[key]:.3f} {unit}")


def _run_calibration_analysis(make_graphs=False, data_root=None):
    """Run the source repository's 3 July calibration through the fit pipeline."""
    log_root = find_measured_curve_log_root(data_root)
    attitude_path = log_root / "flight_attitude.csv"
    if not attitude_path.is_file():
        raise FileNotFoundError(
            f"Calibration attitude CSV not found: {attitude_path}. "
            "Use the complete data/calibration/2026-07-03 directory from the repository."
        )
    has_bin_logs = any(
        path.is_file() and path.suffix.lower() == ".bin" for path in log_root.iterdir()
    )
    sessions = filter_datalink_sessions_by_date_hint(
        find_datalink_session_dirs(resolve_datalink_session_root(log_root)),
        DATALINK_MEASURED_CURVE_DATE_HINT,
    )
    if not has_bin_logs or not sessions:
        raise ValueError(
            "No usable July 3 calibration telemetry found. Check that --data-root "
            "contains the original .BIN logs and Datalink/UART-260703-* sessions."
        )
    profile = build_speed_model_profile("1", 12.4, 4, 28.0, 450.0)
    profile["attitude_log_csv"] = str(attitude_path.resolve())
    hover_power_w = (
        get_power_from_thrust(12400.0 / 4.0, u8lite_kv190_g29_data) * 4.0
    )
    battery_wh = calculate_real_energy_wh(12, 27000, "liion")
    correction_factor = 0.72
    reference = BauersfeldRangeCalculator(
        hover_power_w,
        correction_factor,
        battery_wh,
        profile["mass_kg"],
        450.0,
        profile["prop_diameter_inch"],
        profile["num_rotors"],
    ).solve()
    result = run_datalink_measured_curve_analysis(
        profile,
        reference,
        hover_power_w,
        battery_wh,
        correction_factor,
        log_root=log_root,
        make_graph=make_graphs,
    )
    if not result["measured_hover_power_w"] or not result["speed_bin_observations"]:
        raise ValueError(
            "No usable July 3 calibration samples found. Check that --data-root "
            "contains the original .BIN logs, Datalink sessions, and flight_attitude.csv."
        )
    print("Calibration analysis completed.")
    print(f"Joined samples: {result['joined_sample_count']}")
    print(f"Measured hover power (one sensed branch): {result['measured_hover_power_w']:.2f} W")
    print(f"Median propeller tip speed: {result['utip_ms']:.2f} m/s")
    print(f"Stable speed bins: {len(result['speed_bin_observations'])}")
    if make_graphs:
        print(f"Empirical curve: {Path(DATALINK_EMPIRICAL_OUTPUT_PATH).resolve()}")
        print(
            "Diagnostic fits: "
            f"{Path(DATALINK_DIAGNOSTIC_SURROGATE_OUTPUT_PATH).resolve()}"
        )


def main(argv=None):
    """Command-line entry point for public use."""
    parser = argparse.ArgumentParser(
        description="Estimate multicopter endurance/range or reproduce the July 3 calibration fits."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    calculate = subparsers.add_parser(
        "calculate", help="calculate range and endurance from aircraft inputs"
    )
    calculate.add_argument("--hover-power", type=float, required=True, help="whole-aircraft measured hover power in W")
    calculate.add_argument("--battery-energy", type=float, required=True, help="whole-pack energy basis in Wh")
    calculate.add_argument("--mass", type=float, required=True, help="total takeoff mass in kg")
    calculate.add_argument("--drag-area", type=float, required=True, help="Bauersfeld projected reference area in cm^2 (not CdA)")
    calculate.add_argument("--prop-diameter", type=float, required=True, help="propeller diameter in inches")
    calculate.add_argument("--rotors", type=int, required=True, help="number of rotors")
    calculate.add_argument(
        "--correction-factor",
        type=float,
        default=1.0,
        help="usable-energy multiplier; use 1.0 for an already-usable energy input (default: 1.0)",
    )

    analyze = subparsers.add_parser(
        "analyze-calibration",
        help="rebuild fitted models from the July 3 calibration logs",
    )
    analyze.add_argument(
        "--graphs", action="store_true", help="write empirical and diagnostic PNG files"
    )
    analyze.add_argument(
        "--data-root",
        type=Path,
        help="July 3 directory containing .BIN logs, Datalink/, and flight_attitude.csv; required for wheel installs",
    )

    args = parser.parse_args(argv)
    if args.command == "calculate":
        if not all(
            math.isfinite(value)
            for value in (
                args.hover_power,
                args.battery_energy,
                args.mass,
                args.drag_area,
                args.prop_diameter,
                args.correction_factor,
            )
        ):
            parser.error("all physical inputs must be finite")
        if min(
            args.hover_power,
            args.battery_energy,
            args.mass,
            args.prop_diameter,
            args.rotors,
        ) <= 0:
            parser.error("power, energy, mass, propeller diameter, and rotor count must be positive")
        if args.drag_area < 0 or args.correction_factor <= 0:
            parser.error("drag area must be non-negative and correction factor must be positive")
        result = BauersfeldRangeCalculator(
            args.hover_power,
            args.correction_factor,
            args.battery_energy,
            args.mass,
            args.drag_area,
            args.prop_diameter,
            args.rotors,
        ).solve()
        _print_calculation(result)
    else:
        try:
            _run_calibration_analysis(make_graphs=args.graphs, data_root=args.data_root)
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))


if __name__ == "__main__":
    main()
