# =============================================================================
# CF (CORRECTION FACTOR) HESAPLAYICISI
# Tarık Ziya İnci tarafından geliştirildi
# =============================================================================
# Tek motor + 3S1P cell statik thrust stand testi verisiyle
# 3 farklı üretici tablosunu karşılaştırarak CF hesaplar.
# =============================================================================

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('TkAgg')

# ╔═══════════════════════════════════════════════════════════════════════╗
# ║              ÜRETİCİ MOTOR VERİLERİ — 3 TABLO                      ║
# ╚═══════════════════════════════════════════════════════════════════════╝

# TABLO 1: Orijinal üretici verisi — 23.6V
# [Voltaj, Akım, Kuvvet(gr), Güç(W), Verimlilik(gr/W)]
tablo1_data = [
    [23.6,  2.1,   500,   49.42,  10.1188],
    [23.6,  3.6,   750,   84.68,   8.8570],
    [23.6,  5.35, 1000,  125.91,   7.9434],
    [23.6,  7.25, 1250,  170.61,   7.3276],
    [23.6,  9.35, 1500,  219.89,   6.8216],
    [23.6, 11.7,  1750,  275.14,   6.3604],
    [23.6, 14.15, 2000,  332.75,   6.0105],
    [23.6, 17.7,  2300,  416.74,   5.5212],
    [23.6, 21.15, 2600,  497.81,   5.2240],
    [23.6, 26.1,  3000,  614.42,   4.8841],
    [23.6, 33.5,  3500,  787.66,   4.4436],
]
tablo1_isim = "Orijinal Üretici — 23.6V"

# TABLO 2: APC13*6.5 — 25V
tablo2_data = [
    [25,  2.0,   500,   50.0,   10.0],
    [25,  3.4,   750,   85.0,    8.8235],
    [25,  5.1,  1000,  127.5,    7.8431],
    [25,  6.9,  1250,  172.5,    7.2464],
    [25,  8.8,  1500,  220.0,    6.8182],
    [25, 11.0,  1750,  275.0,    6.3636],
    [25, 13.3,  2000,  332.5,    6.0150],
    [25, 17.0,  2300,  425.0,    5.4118],
    [25, 20.2,  2600,  505.0,    5.1485],
    [25, 25.0,  3000,  625.0,    4.8],
    [25, 31.4,  3500,  785.0,    4.4586],
    [25, 39.5,  4000,  987.5,    4.0506],
    [25, 48.8,  4690, 1220.0,    3.8443],
]
tablo2_isim = "APC13*6.5 — 25V"

# TABLO 3: 22.2V tablosu
tablo3_data = [
    [22.2,  2.2,   500,   48.84,  10.2375],
    [22.2,  3.8,   750,   84.36,   8.8905],
    [22.2,  5.6,  1000,  124.32,   8.0438],
    [22.2,  7.6,  1250,  168.72,   7.4087],
    [22.2,  9.9,  1500,  219.78,   6.8250],
    [22.2, 12.4,  1750,  275.28,   6.3572],
    [22.2, 15.0,  2000,  333.0,    6.0060],
    [22.2, 18.4,  2300,  408.48,   5.6306],
    [22.2, 22.1,  2600,  490.62,   5.2994],
    [22.2, 27.2,  3000,  603.84,   4.9682],
    [22.2, 35.6,  3500,  790.32,   4.4286],
    [22.2, 39.4,  3800,  874.68,   4.3444],
]
tablo3_isim = "22.2V Tablosu"

# Tüm tablolar listesi
TUM_TABLOLAR = [
    (tablo1_data, tablo1_isim),
    (tablo2_data, tablo2_isim),
    (tablo3_data, tablo3_isim),
]

# ╔═══════════════════════════════════════════════════════════════════════╗
# ║              TEST VERİLERİ (TEK MOTOR + 3S1P CELL)                  ║
# ╚═══════════════════════════════════════════════════════════════════════╝

test_zaman_str = ["00s", "24s", "49s", "1:15", "1:41", "2:08", "2:32", "3:01", "3:26", "3:52", "4:18", "4:44"]
test_zaman_sn  = [0, 24, 49, 75, 101, 128, 152, 181, 206, 232, 258, 284]

test_wh_kumulatif = [5.8, 8.1, 10.5, 13.0, 15.5, 18.0, 20.5, 23.1, 25.5, 28.0, 30.4, 32.9]
test_kuvvet = [2148, 2173, 2159, 2195, 2190, 2174, 2176, 2176, 2173, 2166, 2171, 2178]
test_akim   = [15.12, 15.25, 15.8, 15.74, 15.75, 15.73, 15.69, 15.55, 15.59, 15.54, 15.62, 15.81]
test_voltaj = [23.73, 23.68, 23.62, 23.58, 23.84, 23.81, 23.49, 23.46, 23.43, 23.4, 23.36, 23.31]

GERCEK_WH      = 27.1   # 32.9 - 5.8
TEST_SURESI_SN  = 284    # 4 dk 44 sn
ORT_KUVVET      = 2173.25
ORT_AKIM        = 15.6
ORT_VOLTAJ      = 23.6425


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                    HESAPLAMA FONKSİYONLARI                          ║
# ╚═══════════════════════════════════════════════════════════════════════╝

def lineer_interpolasyon(value, x_list, y_list):
    if value <= x_list[0]:
        if len(x_list) >= 2 and x_list[1] != x_list[0]:
            slope = (y_list[1] - y_list[0]) / (x_list[1] - x_list[0])
            return y_list[0] + slope * (value - x_list[0])
        return y_list[0]
    if value >= x_list[-1]:
        if len(x_list) >= 2 and x_list[-1] != x_list[-2]:
            slope = (y_list[-1] - y_list[-2]) / (x_list[-1] - x_list[-2])
            return y_list[-1] + slope * (value - x_list[-1])
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


def kuvvetten_guc_bul(kuvvet_gr, tablo_data):
    """Verilen kuvvet için tablodaki güç değerini interpolasyon ile bulur."""
    thrusts = [row[2] for row in tablo_data]
    powers  = [row[3] for row in tablo_data]
    return lineer_interpolasyon(kuvvet_gr, thrusts, powers)


def kuvvetten_akim_bul(kuvvet_gr, tablo_data):
    """Verilen kuvvet için tablodaki akım değerini interpolasyon ile bulur."""
    thrusts = [row[2] for row in tablo_data]
    akims   = [row[1] for row in tablo_data]
    return lineer_interpolasyon(kuvvet_gr, thrusts, akims)


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║              4 YÖNTEMLE CF HESAPLAMA (TEK TABLO İÇİN)               ║
# ╚═══════════════════════════════════════════════════════════════════════╝

def hesapla_ortalama(tablo_data):
    """Yöntem 1: Ortalama kuvvet ile sabit güç varsayımı."""
    guc = kuvvetten_guc_bul(ORT_KUVVET, tablo_data)
    teorik_wh = guc * (TEST_SURESI_SN / 3600.0)
    cf = teorik_wh / GERCEK_WH
    return teorik_wh, cf


def hesapla_lineer(tablo_data):
    """Yöntem 2A: Lineer interpolasyon ile parçalı hesaplama."""
    toplam_wh = 0.0
    for i in range(len(test_zaman_sn) - 1):
        dt = test_zaman_sn[i + 1] - test_zaman_sn[i]
        f1, f2 = test_kuvvet[i], test_kuvvet[i + 1]
        n = 100
        total_p = sum(kuvvetten_guc_bul(f1 + (f2 - f1) * (j / n), tablo_data) for j in range(n))
        ort_guc = total_p / n
        toplam_wh += ort_guc * (dt / 3600.0)
    cf = toplam_wh / GERCEK_WH
    return toplam_wh, cf


def hesapla_sabit(tablo_data):
    """Yöntem 2B: Sabit kuvvet (başlangıç değeri) ile parçalı hesaplama."""
    toplam_wh = 0.0
    for i in range(len(test_zaman_sn) - 1):
        dt = test_zaman_sn[i + 1] - test_zaman_sn[i]
        guc = kuvvetten_guc_bul(test_kuvvet[i], tablo_data)
        toplam_wh += guc * (dt / 3600.0)
    cf = toplam_wh / GERCEK_WH
    return toplam_wh, cf


def hesapla_parcali_ort(tablo_data):
    """Yöntem 2C: İki ucun ortalaması ile parçalı hesaplama."""
    toplam_wh = 0.0
    for i in range(len(test_zaman_sn) - 1):
        dt = test_zaman_sn[i + 1] - test_zaman_sn[i]
        f_ort = (test_kuvvet[i] + test_kuvvet[i + 1]) / 2.0
        guc = kuvvetten_guc_bul(f_ort, tablo_data)
        toplam_wh += guc * (dt / 3600.0)
    cf = toplam_wh / GERCEK_WH
    return toplam_wh, cf


def tum_yontemler(tablo_data):
    """4 yöntemi çalıştırıp sonuçları dict olarak döndürür."""
    sonuclar = {}
    wh, cf = hesapla_ortalama(tablo_data)
    sonuclar['Ortalama'] = {'wh': wh, 'cf': cf}
    wh, cf = hesapla_lineer(tablo_data)
    sonuclar['Lineer İnterp.'] = {'wh': wh, 'cf': cf}
    wh, cf = hesapla_sabit(tablo_data)
    sonuclar['Sabit Kuvvet'] = {'wh': wh, 'cf': cf}
    wh, cf = hesapla_parcali_ort(tablo_data)
    sonuclar['Parçalı Ort.'] = {'wh': wh, 'cf': cf}
    return sonuclar


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                    GRAFİK FONKSİYONU (FİGÜR 3)                     ║
# ╚═══════════════════════════════════════════════════════════════════════╝

def grafik_cf_karsilastirma(sonuclar, tablo_isim, figur_no):
    """CF bar chart — Teorik vs Gerçek Wh + CF değerleri."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    yontemler = list(sonuclar.keys())
    teorik_whler = [sonuclar[y]['wh'] for y in yontemler]
    cf_degerler  = [sonuclar[y]['cf'] for y in yontemler]

    colors = ['#e74c3c', '#2ecc71', '#3498db', '#f39c12']
    kisaltmalar = ['Ortalama', 'Lineer\nİnterp.', 'Sabit\nKuvvet', 'Parçalı\nOrtalama']

    # --- Sol: Wh karşılaştırma ---
    ax1 = axes[0]
    bars = ax1.bar(range(len(yontemler)), teorik_whler, color=colors,
                   edgecolor='black', linewidth=0.5, alpha=0.85)
    ax1.axhline(y=GERCEK_WH, color='black', linestyle='--', linewidth=2,
                label=f'Gerçek: {GERCEK_WH} Wh')

    for bar, wh in zip(bars, teorik_whler):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                 f'{wh:.2f} Wh', ha='center', va='bottom', fontsize=11, fontweight='bold')

    ax1.set_xticks(range(len(yontemler)))
    ax1.set_xticklabels(kisaltmalar, fontsize=11)
    ax1.set_ylabel('Enerji (Wh)', fontsize=13)
    ax1.set_title(f'Teorik vs Gerçek Enerji\n{tablo_isim}', fontsize=13, fontweight='bold')
    ax1.legend(fontsize=12)
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.set_facecolor('#f8f9fa')

    # --- Sağ: CF değerleri ---
    ax2 = axes[1]
    bars2 = ax2.bar(range(len(yontemler)), cf_degerler, color=colors,
                    edgecolor='black', linewidth=0.5, alpha=0.85)

    for bar, cf in zip(bars2, cf_degerler):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                 f'{cf:.4f}', ha='center', va='bottom', fontsize=12, fontweight='bold')

    ax2.axhline(y=1.0, color='gray', linestyle=':', linewidth=1.5, alpha=0.5,
                label='CF = 1.0 (Mükemmel eşleşme)')

    ax2.set_xticks(range(len(yontemler)))
    ax2.set_xticklabels(kisaltmalar, fontsize=11)
    ax2.set_ylabel('CF (Correction Factor)', fontsize=13)
    ax2.set_title(f'Hesaplanan CF Değerleri\n{tablo_isim}', fontsize=13, fontweight='bold')
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.set_facecolor('#f8f9fa')
    ax2.set_ylim([0, max(max(cf_degerler) * 1.15, 1.2)])

    fig.patch.set_facecolor('#ffffff')
    fig.suptitle(f'Figür {figur_no}: {tablo_isim}', fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()

    dosya = f'/home/tzi4/tarik/CF_figur_{figur_no}.png'
    plt.savefig(dosya, dpi=150, bbox_inches='tight')
    print(f"  [FİGÜR {figur_no}] Kaydedildi: CF_figur_{figur_no}.png")


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                           ANA PROGRAM                              ║
# ╚═══════════════════════════════════════════════════════════════════════╝

def main():
    print("╔" + "═" * 68 + "╗")
    print("║" + " CF (CORRECTION FACTOR) HESAPLAYICISI ".center(68) + "║")
    print("║" + " Tek Motor Testi — 3 Farklı Üretici Tablosu ".center(68) + "║")
    print("╚" + "═" * 68 + "╝")

    gercek_guc = ORT_AKIM * ORT_VOLTAJ
    print(f"\n  Test Koşulları          : TEK MOTOR + 3S1P Cell")
    print(f"  Toplam Test Süresi      : {TEST_SURESI_SN} sn ({TEST_SURESI_SN/60:.2f} dk)")
    print(f"  Gerçek Harcanan Enerji  : {GERCEK_WH} Wh")
    print(f"  Ortalama Kuvvet         : {ORT_KUVVET} gr")
    print(f"  Ortalama Akım           : {ORT_AKIM} A")
    print(f"  Ortalama Voltaj         : {ORT_VOLTAJ} V")
    print(f"  Ortalama Gerçek Güç     : {gercek_guc:.2f} W")

    tum_sonuclar = {}

    for idx, (tablo_data, tablo_isim) in enumerate(TUM_TABLOLAR, 1):
        print("\n" + "█" * 70)
        print(f"  TABLO {idx}: {tablo_isim}")
        print("█" * 70)

        voltaj = tablo_data[0][0]
        uretici_guc = kuvvetten_guc_bul(ORT_KUVVET, tablo_data)
        uretici_akim = kuvvetten_akim_bul(ORT_KUVVET, tablo_data)

        print(f"  Tablo Voltajı             : {voltaj} V")
        print(f"  Üretici Güç ({ORT_KUVVET:.0f}gr için) : {uretici_guc:.2f} W")
        print(f"  Üretici Akım              : {uretici_akim:.2f} A")
        print(f"  Gerçek Güç (V×A)          : {gercek_guc:.2f} W")
        print(f"  Fark                      : {gercek_guc - uretici_guc:+.2f} W ({(gercek_guc/uretici_guc - 1)*100:+.1f}%)")

        sonuclar = tum_yontemler(tablo_data)
        tum_sonuclar[tablo_isim] = sonuclar

        # Tablo yazdır
        print(f"\n  {'Yöntem':>20} | {'Teorik Wh':>12} | {'Gerçek Wh':>12} | {'CF':>10} | {'Sapma %':>10}")
        print("  " + "-" * 70)
        for yontem, deger in sonuclar.items():
            sapma = (deger['wh'] - GERCEK_WH) / GERCEK_WH * 100
            print(f"  {yontem:>20} | {deger['wh']:>12.4f} | {GERCEK_WH:>12.1f} | {deger['cf']:>10.6f} | {sapma:>+10.2f}%")

        cf_ort = np.mean([v['cf'] for v in sonuclar.values()])
        print(f"\n  ► Ortalama CF = {cf_ort:.6f}")

        if cf_ort > 1.0:
            print(f"  → Motor bu tabloya göre %{(cf_ort - 1) * 100:.2f} DAHA VERİMLİ çalışıyor")
        else:
            print(f"  → Motor bu tabloya göre %{(1 - cf_ort) * 100:.2f} DAHA AZ VERİMLİ çalışıyor")

    # --- TÜM TABLOLARIN KARŞILAŞTIRMASI ---
    print("\n" + "═" * 70)
    print("  TÜM TABLOLARIN CF KARŞILAŞTIRMASI")
    print("═" * 70)
    print(f"\n  {'Tablo':>30} | {'Ort. CF':>10} | {'Yorum':>30}")
    print("  " + "-" * 75)
    for tablo_isim, sonuclar in tum_sonuclar.items():
        cf_ort = np.mean([v['cf'] for v in sonuclar.values()])
        if cf_ort > 1.0:
            yorum = f"Motor %{(cf_ort-1)*100:.1f} daha verimli"
        else:
            yorum = f"Motor %{(1-cf_ort)*100:.1f} daha az verimli"
        print(f"  {tablo_isim:>30} | {cf_ort:>10.4f} | {yorum:>30}")

    # --- GRAFİKLER ---
    print("\n" + "=" * 70)
    print("  FİGÜRLER ÜRETİLİYOR...")
    print("=" * 70)

    for idx, (tablo_data, tablo_isim) in enumerate(TUM_TABLOLAR, 1):
        sonuclar = tum_sonuclar[tablo_isim]
        grafik_cf_karsilastirma(sonuclar, tablo_isim, idx)

    print("\n  Tüm figürler /home/tzi4/tarik/ klasörüne kaydedildi.")
    print("═" * 70)

    plt.show()


if __name__ == "__main__":
    main()
