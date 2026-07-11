# Üç Menzil Modelinin "Mükerrer" Eğri Davranışı — Teşhis Raporu

*Tarih: 11 Temmuz 2026 — menzil2.py analizi*

## Soru

Zeng / Faessler / Kirschstein modellerinin eğrileri, hangi araç/kütle/batarya girilirse
girilsin birbirlerine göre hep aynı davranıyor; sadece ölçeklenmiş kopyalar görülüyor.
Bu bir mantık hatası mı, yoksa tek uçuş verisiyle fit etmenin doğal sonucu mu?

## Cevap (özet)

**Kod akışında bir "bug" yok; gözlemlenen davranış iki yapısal nedenin matematiksel
olarak garanti ettiği bir sonuçtu.** Model bir şeyi "overfit ederek" öğrenmedi —
tasarım gereği eğri şekli Fırfır'da donduruluyor ve araçtan araca **hiçbir şey
öğrenilmiyor/aktarılmıyordu**; yalnızca iki skaler (hover gücü ölçeği ve batarya Wh)
değişiyordu. Bu rapor iki nedeni sayısal kanıtlarıyla açıklar. (Faz-4 güncellemesiyle
artık fiziksel parametre transferi mevcut; sonda özetlenmiştir.)

---

## Neden 1 — Üç model de aynı veriye 2'şer serbest parametreyle fit ediliyor

`build_measured_curve_model_fit` üç modele de **aynı** girdileri verir:

| Girdi | Değer | Kaynak |
|---|---|---|
| Gözlemler | 11 hız bini, 2.46–12.34 m/s | 3 Temmuz DataLink (28 095 stabil örnek) |
| Hover referansı | 757.9 W (tek kol) | DataLink ölçümü |
| v0 (indüklenen hız) | 5.59 m/s | Kütle/disk alanından (formül) |
| Utip | 168.1 m/s¹ | DataLink RPM medyanı |

¹ Rapor tarihindeki ham ölçek; RPM ölçek düzeltmesi (bkz. "Ek keşif") sonrası
doğru değer 80.05 m/s'dir. Fit eğrileri bundan etkilenmez (Kanıt B).

Her model, `_fit_two_parameter_weighted` ile tam **2 serbest lineer çarpan** fit eder
(Zeng: f0 + k_par; Faessler: f0 + drag_scale; Kirschstein: relief + extra_cubic).
Ağırlıklı en küçük kareler, üç modeli de aynı 11 noktaya çeker.

### Kanıt A — Fit sonrası üç eğri veri aralığında pratik olarak özdeş

Gerçek 3 Temmuz fitinden, 2.5–12.3 m/s aralığında karşılıklı maksimum fark:

```
zeng      vs faessler    : max |ΔP/Ph| = 0.0006
zeng      vs kirschstein : max |ΔP/Ph| = 0.0001
faessler  vs kirschstein : max |ΔP/Ph| = 0.0007
```

Üç modelin fit MAE'si de aynıdır (~0.0277). Yani fit sonrası bu üçü **bağımsız tahmin
değil, aynı ampirik eğrinin üç re-parametrizasyonudur**. Kodun kendi denetimi de bunu
söylüyordu: *"diagnostic surrogate fits … not independent physical validation curves"*
(`fit_audit`, menzil2.py). Ekstrapolasyonda (>12.3 m/s) kalan küçük farklar da hep aynı
kalır, çünkü fit girdileri hiçbir koşulda değişmiyordu.

### Kanıt B — Fiziksel parametre değişse bile fit aynı eğriye "geri oturur"

v0 bilerek ±%30 bozulup Zeng yeniden fit edildiğinde eğri değişmez; iki serbest
parametre farkı tamamen kompanse eder:

```
v0 × 0.7 : f0 = 0.8954, k_par = 4.97e-05, MAE = 0.0288
v0 × 1.0 : f0 = 0.8177, k_par = 6.90e-05, MAE = 0.0277
v0 × 1.3 : f0 = 0.6976, k_par = 8.86e-05, MAE = 0.0273
```

Fit edilen parametreler kökten değişiyor (f0: 0.70↔0.90), üretilen eğri bin
noktalarında 3. ondalığa kadar aynı kalıyor. Sonuç: **tek uçuşun dar hız aralığındaki
verisi, parametreleri fiziksel olarak ayırt edemez (identifiability yok); eğriyi veri
belirler, model yapısı değil.** "Tek uçuşla fit etmenin doğal sonucu mu?" sorusunun
cevabı budur: evet — üç esnek modelin aynı veriye fiti, veri aralığında kaçınılmaz
olarak aynı eğriye yakınsar.

## Neden 2 — Araca uygulama eğrinin şeklini hiç değiştirmiyordu (tasarım)

Menüden çağrılan tek akış `run_preset_fit_apply_to_vehicle` idi ve koddaki yorum bunu
açıkça belgeliyordu: *"Model (P/Ph oran eğrisi) HER ZAMAN fit_profile üzerinden,
Fırfır DataLink verisiyle tune edilir."* Girilen aracın kütlesi, rotor sayısı,
pervanesi oran eğrisine **hiç girmiyordu**; araç yalnızca iki skaler katkı yapıyordu:

1. `result_hover_power_w = girilen_hover × hover_scale` (hover_scale ≈ 1.349,
   Fırfır gerçek/teorik hover oranı — sabit)
2. Batarya Wh (usable oranıyla)

`calculate_flight_for_speed` ise saf bir ölçekleme uygular:
`P(v) = P_hover·ratio(v)`, `t = E/P`, `R = v·t`. Üç `ratio(v)` fonksiyonu bit-bit aynı
kaldığından, her araç girişi üç eğriyi de **aynı sabitlerle çarpar** → göreli davranış
matematiksel olarak değişmez. "Sadece scale edilmiş halini görüyorum" gözlemi birebir
doğrudur. (Belirti: Bauersfeld hız işaretçileri araca göre kayarken model eğrilerinin
minimumları sabit kalıyordu — değişmeyen eğri üstünde hareket eden işaretçi.)

## Gerçekte de böyle mi? — Hayır

P/Ph şekli araç fiziğine bağlıdır:

- **v0 = √(W/2ρA)** (disk yükü): ağır araçta indüklenen güç yavaş düşer, endurans ve
  menzil optimum hızları sağa kayar.
- **Utip**: profil gücünün hızla artış oranını (3v²/U²) belirler.
- **CdA/W ve λ/W**: parazit ve rotor sürüklenme terimlerinin görece ağırlığı.

Donmuş şekil yaklaşımı yalnızca Fırfır'a aerodinamik olarak benzer araçlar
(benzer disk yükü, benzer sürükleme/ağırlık oranı) için savunulabilir bir yaklaşımdı.

## Faz-4 çözümü: fiziksel parametre transferi (uygulandı)

CF analojisinin doğru genellemesi: araçtan araca taşınabilir olan şey oran eğrisi
değil, **boyutsuz katsayılardır**. Yeni `build_transferred_model_suite` fitten şunları
çözer ve girilen aracın fiziğiyle eğrileri yeniden kurar:

- Zeng: δσ (profil), 1+k_ind (indüklenen), CdA (parazit)
- Faessler: CdA_body, λ/W (rotor sürüklenmesi)
- Kirschstein: lift/N (N başına kaldırma gücü), geometri-ölçekli profil gücü

**Özdeşlik testi:** transfer Fırfır'ın kendisine uygulanınca orijinal eğriler geri
gelir (Zeng/Faessler analitik olarak birebir; Kirschstein <0.02 kalıntıyla) ve üç
modelin hover tahmini ölçülen araç hover'ını (1516 W) birebir yeniden üretir.

**Ayrışma kanıtı (18 kg, 4×28", aynı Utip):**

```
                      Fırfır (12.4 kg)      18 kg araç
v0                    5.59 m/s              6.73 m/s
Zeng P_hover(pred)    1516 W                1723 W
Faessler              1516 W                1791 W
Kirschstein           1516 W                1920 W
P/Ph @ 10 m/s         0.993 / 0.993 / 0.994 0.962 / 0.975 / 0.993
```

Üç model, kütle değişince artık **gerçekten ayrışıyor** — çünkü her modelin hover
bileşen ayrıştırması farklı ve kütle her bileşeni farklı ölçekler. Bu ayrışma, üç
modelin hangisinin doğru genellediğini bir sonraki farklı-kütleli test uçuşuyla
sınamayı ilk kez mümkün kılar.

### Önemli uyarılar

1. **Zeng'in ayrıştırması fiziksel değildir.** Fit f0=0.818 verir → hover'ın %82'si
   profil gücüne atanır; buradan çıkan 1+k_ind=0.406, momentum teorisinin %41'i
   demektir (fiziksel alt sınır ~1.0). Bu, Neden-1'deki identifiability sorununun
   doğrudan sonucudur: transfer bu ayrıştırmayı dürüstçe taşır ama Zeng'in kütle
   duyarlılığı bu yüzden olması gerekenden zayıftır. **Kirschstein'ın ayrıştırması
   (lift/N = 7.36 W/N ≈ ideal 6.1 W/N × kayıplar) fiziksel olarak en tutarlısıdır;**
   farklı kütleli araçlara ekstrapolasyonda ona öncelik verin.
2. Kirschstein'ın orijinal fit parametreleri tek-kol elektrik referansını (758 W)
   araç-seviyesi profil gücüyle (621 W) karıştırıyordu; fit düzeltmeleri bunu absorbe
   ettiği için eğri doğruydu ama `lift/N=1.126` gibi ara değerler fiziksel değildi.
   Transfer bu bazı araç seviyesine (1516 W) tutarlı hale getirir.
3. Batarya kapasitesi eğri şeklini etkilemez (doğru davranış); ancak batarya değişimi
   **kütleyi** değiştiriyorsa yeni toplam kütleyi girmelisiniz.
4. Transferin doğrulanması için tek yol: farklı kütle/pervaneli bir araçla yeni bir
   DataLink uçuşu yapıp ölçülen eğriyi üç transfer tahminiyle karşılaştırmak.

## Ek keşif: DataLink RPM ölçeği ~2× hatalıydı — DÜZELTİLDİ (parser ölçeği uygulandı)

`testParameter_U8 Lite ... KV190.xls` yük testi tablosu eklendikten sonra ortaya
çıkan bulgu: datasheet, Fırfır hover itkisinde (3100 g/rotor, G28×9.2) **~2216
mekanik RPM** (Utip ≈ 82.5 m/s) veriyor; DataLink logları ise ham ~4500 "RPM"
(Utip 168.1) ölçüyordu — oran **2.04**.

Kesin fiziksel argüman: KV190 motor 6S'te (~22.2 V) yüksüz bile en fazla
190×22.2 ≈ **4218 RPM** dönebilir; hover'da (yüklü) 4500 mekanik RPM imkânsızdır.
Datasheet'in 2216'sı (yüksüzün ~%53'ü) ise tam beklenen bölgededir. U8 Lite
36N42P (21 kutup çifti) olduğundan ham alan eRPM türevi:
2216 × 21 / 10 ≈ 4654 ≈ ölçülen ~4500.

**Uygulanan kalıcı düzeltme (11 Temmuz 2026):**
- `parse_datalink_udat_file` ham alanı artık `DATALINK_RPM_SCALE = 10/21`
  (≈0.476) ile mekanik RPM'e çevirir; sanity filtresi de mekanik ölçeğe
  taşındı (`DATALINK_RPM_SANITY_RANGE_MECH`, 140–5750).
- Preset güncellendi: `utip_ms` 167.6 → **79.8 m/s**, `hover_rpm_estimate`
  4500 → **2142.9**. Guardrail `DATALINK_DATASHEET_UTIP_RANGE_MS`
  (120, 230) → (57, 110).
- Preset'in "eski yanlış" denip 168'e "düzeltilen" Utip'i (80 m/s)
  **baştan doğruydu**.

**Doğrulama (gerçek 3 Temmuz logları, düzeltme sonrası yeniden fit):**
- Ölçülen Utip medyanı 80.05 m/s → hover **2150 mekanik RPM**; datasheet
  çapası 2216 RPM'e göre fark −67 RPM (−%3, ~2200±100 beklentisi içinde).
- `estimate_theoretical_utip_datasheet` fit/datasheet ölçeği artık **0.970**
  (~1.0); menüdeki eRPM ölçek uyarısı artık tetiklenmiyor (test korur).
- Fit eğrileri beklendiği gibi ETKİLENMEDİ (Neden-1): üç modelin MAE'si
  0.0277–0.0278'de sabit kaldı. **Ayrıştırma** değişti: Zeng f0=0.818,
  k_par=6.90e-05 → **f0=0.800, k_par=5.19e-05**; profil teriminin hız eğimi
  (f0·3/U²) 8.7e-05 → 3.75e-04 ile 4.3× büyüdü, kübik parazit terimi buna
  karşılık küçüldü. Not: f0 hâlâ ~0.8 — hover'ın %80'ini profile atayan
  ayrıştırma ölçek düzeltmesiyle tamamen fizikselleşmedi; Neden-1'deki
  identifiability sınırı geçerliliğini koruyor (Kirschstein önceliği önerisi
  değişmedi).

## Bu çalışmada yapılan kod düzeltmeleri

1. **Gizli KeyError** — `fit_observation_weighted_zeng`'in gözlemsiz fallback dalı var
   olmayan `theoretical_params["k_par"]` anahtarını okuyordu; artık attitude-log
   prior'ından, o yoksa teorik CdA'dan türetiliyor.
2. **Sessiz yanlış normalizasyon** — ölçülen hover bulunamadığında oran eğrisi girilen
   aracın hover'ıyla normalize ediliyordu; artık fit aracının teorik hover'ına düşer
   ve uyarı basar (`resolve_fit_power_reference`).
3. **Ölü kod temizliği** — menüden erişilemeyen `run_custom_speed_models` silindi
   (testleri gerçek akış `run_preset_fit_apply_to_vehicle`'a taşındı);
   silinmiş API'ları çağıran bayat testler kaldırıldı
   (`test_menzil2_experimental_only.py` ve `test_menzil2_datalink.py`'nin 6 testi);
   5 testteki bayat sayısal beklentiler (eski 3.26 V/hücre Li-ion enerjisi ve eski
   rezerv şeması) güncel tanımlara güncellendi.
4. **Faz-4** — `build_transferred_model_suite` + menüye "Transfer uygulansın mı?"
   seçeneği (varsayılan: evet; "h" ile eski donmuş-şekil davranışı korunur).

## Tekrar üretme

- Testler: `python -m pytest -q` (25 test; transfer özdeşlik/ayrışma testleri
  `test_menzil2_transfer.py` içinde)
- Demo sayıları: bu rapordaki tablolar, gerçek 3 Temmuz logları üzerinde
  `run_datalink_measured_curve_analysis` + `fit_weighted_zeng_ratio` (v0 × 0.7/1.0/1.3)
  ile üretildi; 18 kg senaryosu menü akışında (mod 1 → quad → motor 17 → 18 kg →
  LiIon 2×27000 6S → seçenek 3 → transfer "e") koşuldu.
