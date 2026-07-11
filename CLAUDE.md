# CLAUDE.md

Multicopter batarya ve menzil analiz araç seti (Türkçe proje). Fiziksel güç modelleri
(Zeng / Faessler / Kirschstein) gerçek uçuş telemetrisiyle ("Fırfır" aracı, 3 Temmuz
2026) kalibre edilir ve başka araçlara uygulanır.

## Çalıştırma

- Giriş noktası: `python menzil2.py` (etkileşimli menü). Önerilen akış: mod 1 →
  gövde/motor/batarya girişleri → ana menüde **seçenek 3 = Preset/log DataLink fit
  analizi**.
- Bağımlılıklar: `pip install -r requirements.txt` (matplotlib, pymavlink, pytest;
  Python 3.12 ile kullanılıyor).
- Testler: `python -m pytest -q` (~40 s; july3 suite gerçek 100 MB BIN loglarını
  parse eder). Ana suite: `test_menzil2_july3_measured_curve.py`. Transfer ve fallback
  testleri: `test_menzil2_transfer.py`.
- Grafik üreten koşularda `MPLBACKEND=Agg` kullan (headless).

## Dosya haritası

- `menzil2.py` — tek büyük modül (~5300 satır): Bauersfeld hesaplayıcı, motor thrust
  tabloları, DataLink `.udat` parser, ArduPilot `.BIN` eşleme, üç model fiti,
  Faz-4 fiziksel parametre transferi, menü.
- `menzil1.py` — legacy sade Bauersfeld+CF hesaplayıcı (referans; menzil2 bundan türedi).
- `CF_calculator.py`, `pil_analiz_v2.py`, `pil_bitirme_testi.py`, `analyze_july3_battery.py`
  — yardımcı/tek seferlik analizler.
- `remove_dead*.py`, `refactor*.py`, `update_menu.py`, `add_option5.py` vb. — menzil2.py
  düzenlemede kullanılmış tek seferlik kod-cerrahisi scriptleri; pipeline parçası değil.
- Raporlar: `mukerrer_egri_davranisi_raporu.md` (üç eğrinin özdeş davranışının teşhisi),
  `scientific_model_fit_audit.md`, `datalink_fit_method_report.md` (otomatik üretilir),
  `implementation_plan.md` (bilimsel disiplin: model başına yalnız 2 serbest parametre).

## Veri kuralları

- Kalibrasyon verisi: `3 Temmuz Tüm Test Logları/` → `00000076.BIN`, `00000077.BIN` +
  `Datalink/UART-260703-*` oturumları. Varsayılan tarih hint'i `260703`.
- Eski/karşılaştırma DataLink verisi: `Some Datalink Data/datalink/`
  (260623–260625 oturumları; testler bunları fixture olarak kullanır).
- Empirical interpolation grafiği yalnızca menü-5 ham veri görselleyicisinde
  üretilir (`raw_datalink_empirical_interpolation.png`); menü-3 preset fit akışı
  sadece power-ratio ve range/time grafiklerini üretir.
- `flight_attitude_00000075*.csv` — Faessler CdA/λ kestirimi için attitude logu.

## Kritik tuzaklar

- **6S2P tek-kol ölçümü:** Fırfır'ın gerçek paketi 6S2P (12 hücre) ama DataLink akım
  sensörü TEK paralel koldaydı. Ölçülen hover (~758 W) ve entegre enerji gerçek aracın
  YARISIDIR; araç seviyesi = ölçülen × `FIRFIR_BATTERY_PARALLEL_ARMS` (=2). P/Ph oranı
  kol-bağımsızdır (paydada da tek kol var). Bu ayrımı bozan her değişiklik 40 dk hover
  baseline'ını bozar (testler korur: %10 rezervde ≈39.86 dk).
- **Batarya kimyası:** Konino Li-ion/katı hal paketler `LiIon` olarak girilmeli
  (3.7 V/hücre nominal). `LiPo/LiHV` girmek enerji tabanını kaydırır.
- **Fit disiplini:** model başına yalnız 2 serbest parametre; P_hover, Utip, v0 ölçülür,
  ASLA fit edilmez (`audit_scientific_fit_parameters` ihlalleri reddeder; test korur).
- **Fit ≠ doğrulama:** üç modelin fit sonrası eğrileri veri aralığında özdeştir
  (maks fark ~0.0007) — bunlar "diagnostic surrogate fits". Neden ve kanıtlar:
  `mukerrer_egri_davranisi_raporu.md`.
- **Faz-4 transferi:** `build_transferred_model_suite` fitten boyutsuz katsayıları
  (δσ, 1+k_ind, CdA, λ/W, lift/N) çözüp girilen aracın kütle/pervane/Utip'iyle eğrileri
  yeniden kurar. Özdeşlik garantisi test edilir (Fırfır→Fırfır birebir). Menüde
  varsayılan açıktır; "h" ile eski donmuş-şekil davranışına dönülür. Batarya değişimi
  kütleyi değiştiriyorsa yeni TOPLAM kütle girilmelidir.
- **Utip kaynağı (transfer içinde):** 1) Fırfır ölçümü (varsayılan), 2) teorik —
  `estimate_theoretical_utip_datasheet` KV190 datasheet thrust→RPM eğrisinden
  (`u8lite_kv190_g28/g29_thrust_rpm` tabloları, pervaneye göre 28"/29") girilen
  kütleyle Utip türetir ve Fırfır ölçümüne göre % farkı raporlar; tablo yoksa
  pervane benzerliği (`estimate_theoretical_utip_similarity`) fallback'i,
  3) elle giriş. Başka motor/pervane konfigürasyonlarına genelleme planlanan iş.
- **DataLink RPM ölçeği (DÜZELTİLDİ):** ham `.udat` RPM alanı eRPM/10'dur
  (36N42P → 21 kutup çifti); parser `DATALINK_RPM_SCALE = 10/21` ile mekanik
  RPM'e çevirir. Doğrulama çapası: hover 3100 g/rotor → datasheet ~2216 RPM,
  ölçülen ~2150 RPM (Utip ~80 m/s, eski ham ölçekte 168.1 görünüyordu).
  Fit eğrileri düzeltmeden etkilenmedi (MAE sabit) ama ayrıştırma değişti
  (Zeng f0=0.818→0.800, k_par 6.9e-05→5.2e-05). Teorik Utip seçeneği yine de
  fit ölçeğine ÇAPALI kalır (ölçek artık ~0.97; uyarı yalnız tutarsızlıkta
  basılır — datasheet mutlak değerini fit'e karıştırma). Ham ölçeğe dönen her
  değişiklik guardrail'lere takılır (`DATALINK_DATASHEET_UTIP_RANGE_MS`
  57–110 m/s, testler korur); detay: `mukerrer_egri_davranisi_raporu.md`.
- Oran eğrisi normalizasyonu ölçülen hover bulunamazsa fit aracının teorik hover'ına
  düşer (`resolve_fit_power_reference`) — girilen aracın gücüyle asla sessizce
  normalize etme.
