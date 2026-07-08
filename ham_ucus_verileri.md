# Li-ion Solid State 6S 27Ah — Ham Uçuş Verileri

**Batarya:** Custom Li-ion Solid State, 6S (seri), 27000mAh (nominal), 25.2Ah (ölçülmüş kullanılabilir kapasite)

**Ölçüm yöntemi:** İnip multimetre ile pack voltajı ölçümü (aksi belirtilmediği sürece). Bazı ölçümlerde iki ayrı multimetre kullanılmıştır (iki değer verildiğinde).

**Referans anchor noktaları (düşük C-rate şarj aleti testi):**
| V/cell | Ah kullanılan | SOC |
|:------:|:---:|:---:|
| 4.178V | 0.0Ah | 100% |
| 3.815V | 11.6Ah | 54% |
| 3.718V | 14.9Ah | 41% |
| 3.643V | 17.7Ah | 30% |
| 3.360V | 25.2Ah | 0% |

---

## Tezgah Testi (Bench Test)

**Tarih:** ~Mayıs 2026 öncesi  
**Açıklama:** 6S pack'i tezgah üzerinde ~45A sabit yük altında boşaltma testi. 5 cell ~4.2V'ye, 1 cell ~3.9V'ye şarj edilmiş durumda başlandı. Her 5 saniyede cell voltajı, pack voltajı ve akım kaydedildi. Toplam ~52 dk.  
**Veri kaynağı:** `pil_bitirme_testi.py` → `RAW_DATA` değişkeni (saniye bazlı kayıt)

> Ham veri çok uzun olduğundan burada yer verilmemiştir. Detay için `pil_bitirme_testi.py` dosyasına bakınız.

---

## Uçuş 1 — 25 Mayıs 2026

**Açıklama:** İlk drone test uçuşu. Autotune (PID otomatik ayarlama) dahil, agresif manevralar içeriyor. Drone: Hexacopter, U8 Lite KV190 + G28x9.2" pervaneler.

| # | Toplam Uçuş Süresi | Pack Voltajı (V) | Not |
|:-:|:---:|:---:|:---|
| 1 | Uçuş öncesi | 24.9 | Multimetre, dinlenmiş |
| 2 | 3 dk 53 sn | 24.5 | |
| 3 | 22 dk 03 sn | 23.2 | |
| 4 | 35 dk 20 sn | 22.06 | |
| 5 | 43 dk 50 sn | 21.42 | ~3.57V/cell |
| 6 | 45 dk 27 sn | 21.25 | ~3.54V/cell |
| 7 | 46 dk 18 sn | 21.13 | ~3.52V/cell, son ölçüm |
| 8 | Tam dinlenmiş (sabahı) | 21.3 | ~3.55V/cell |

---

## Uçuş 2 — 28 Mayıs 2026

**Açıklama:** Normal hover uçuşu. Sakin, althold modda bekleme. 26dk 12sn sonra indirildi (pil bitmedi, görev tamamlandı).

| # | Toplam Uçuş Süresi | Pack Voltajı (V) | Not |
|:-:|:---:|:---:|:---|
| 1 | Uçuş öncesi | 25.05 | Tam şarj |
| 2 | 4 dk 30 sn | 24.55 | Yatmamış (indirip hemen ölçüm) |
| 3 | 7 dk 23 sn | 24.4 | |
| 4 | 13 dk 48 sn | 23.9 (yatmamış), 24.1 (yatmış) | Hem yük altı hem dinlenmiş ölçüm var |
| 5 | 26 dk 12 sn | — | Son uçuş, voltaj ölçülmedi |

---

## Uçuş 3 — 24 Haziran 2026 (Değişiklik Sonrası)

**Açıklama:** Drone üzerinde bazı değişiklikler yapıldıktan sonraki ilk uçuş. Karışık mod: hover + autotune + althold'da gezinme uçuşu.

| # | Toplam Uçuş Süresi | Pack Voltajı (V) | Not |
|:-:|:---:|:---:|:---|
| 1 | Uçuş öncesi | 25 ve 25.1 | İki multimetre |
| 2 | 3 dk 23 sn | 24.6 ve 24.6 | İki multimetre |
| 3 | 17 dk 30 sn | 23.5 ve 23.5 | (~30sn'ye yakın, tam saniye belirsiz) |
| 4 | 27 dk 55 sn | 22.5 | (17:30 + 10dk 25sn daha) |
| 5 | 39 dk 20 sn | 21.5 | (27:55 + 11dk 25sn daha) |
| 6 | Tam dinlenmiş | 21.96 | |

---

## Uçuş 4 — 25 Haziran 2026

**Açıklama:** Henüz detaylandırılmadı.

| # | Toplam Uçuş Süresi | Pack Voltajı (V) | Not |
|:-:|:---:|:---:|:---|
| 1 | Uçuş öncesi | 24.4 ve 24.4 | İki multimetre, tam şarj değil! |
| 2 | 3 dk 17 sn | — | Ölçüm yapılmadı |
| 3 | 7 dk 29 sn | 23.8 ve 23.8 | İki multimetre |
| 4 | 14 dk 04 sn | 23 | |
| 5 | 18 dk 49 sn | 22.5 | |

---

## Tüm Uçuşlar — Toplu Ham Veri (CSV Formatı)

Aşağıdaki tablo tüm uçuşlardan elde edilen ham verileri tek bir yerde toplar.

```
Uçuş, Tarih, Toplam_Süre, Pack_V, Pack_V_2, Not
1, 2026-05-25, 0:00 (öncesi), 24.9, -, Dinlenmiş
1, 2026-05-25, 3:53, 24.5, -, -
1, 2026-05-25, 22:03, 23.2, -, -
1, 2026-05-25, 35:20, 22.06, -, -
1, 2026-05-25, 43:50, 21.42, -, -
1, 2026-05-25, 45:27, 21.25, -, -
1, 2026-05-25, 46:18, 21.13, -, Son ölçüm
1, 2026-05-25, dinlenmiş, 21.3, -, Sabahı tam rest
2, 2026-05-28, 0:00 (öncesi), 25.05, -, Tam şarj
2, 2026-05-28, 4:30, 24.55, -, Yatmamış
2, 2026-05-28, 7:23, 24.4, -, -
2, 2026-05-28, 13:48, 23.9, -, Yatmamış
2, 2026-05-28, 13:48, 24.1, -, Yatmış (aynı noktanın dinlenmiş hali)
2, 2026-05-28, 26:12, -, -, Son uçuş voltaj yok
3, 2026-06-24, 0:00 (öncesi), 25.0, 25.1, İki multimetre
3, 2026-06-24, 3:23, 24.6, 24.6, İki multimetre
3, 2026-06-24, 17:30, 23.5, 23.5, İki multimetre
3, 2026-06-24, 27:55, 22.5, -, -
3, 2026-06-24, 39:20, 21.5, -, -
3, 2026-06-24, dinlenmiş, 21.96, -, Tam rest
4, 2026-06-25, 0:00 (öncesi), 24.4, 24.4, Tam şarj değil!
4, 2026-06-25, 3:17, -, -, Ölçüm yok
4, 2026-06-25, 7:29, 23.8, 23.8, İki multimetre
4, 2026-06-25, 14:04, 23.0, -, -
4, 2026-06-25, 18:49, 22.5, -, -
```

---

*Bu doküman tüm ham uçuş verilerini içerir. Analiz sonuçları için ayrıca üzerinde çalışılan raporlara bakınız.*
