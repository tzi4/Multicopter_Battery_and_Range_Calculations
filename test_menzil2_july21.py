"""21 Temmuz veri kaynagi entegrasyon/regresyon testleri.

Devir notu ('21 temmuz Tum Test Loglari/MENZIL2_21_TEMMUZ_ENTEGRASYON_DEVIR_NOTU.md')
ve dogrulanmis referans cikti temel alinir. Amac: 3 Temmuz davranisini bozmadan
21 Temmuz'un 3 Temmuz'un eklendigi gibi eklendigini kanitlamak.
"""

from pathlib import Path

import pytest

import menzil2


def _firfir_context():
    # 3 Temmuz fitini test_menzil2_july3_measured_curve._firfir_context ile birebir kur.
    profile = menzil2.build_speed_model_profile("1", 12.4, 4, 29.0, 450.0)
    hover_power_w = (
        menzil2.get_power_from_thrust(12400.0 / 4.0, menzil2.u8lite_kv190_g29_data)
        * 4.0
    )
    battery_wh = menzil2.calculate_real_energy_wh(12, 27000, "liion")
    correction_factor = 0.72
    sonuc = menzil2.BauersfeldMenzilHesaplayici(
        hover_power_w,
        correction_factor,
        battery_wh,
        profile["mass_kg"],
        450.0,
        profile["prop_diameter_inch"],
        profile["num_rotors"],
    ).solve()
    return profile, sonuc, hover_power_w, battery_wh, correction_factor


def _july3_suite():
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()
    return menzil2.build_datalink_fitted_model_suite(
        profile, sonuc, hover_power_w, battery_wh, correction_factor
    )


@pytest.fixture(scope="module")
def july3_suite():
    return _july3_suite()


@pytest.fixture(scope="module")
def validation(july3_suite):
    return menzil2.run_july21_validation_against_july3(july3_suite, make_graph=False)


def _train_row(validation, target_speed_ms, tol=0.05):
    for row in validation["validation_rows"]:
        if row["phase"] != menzil2.JULY21_TRAIN_PHASE:
            continue
        if abs(row["speed_ms"] - target_speed_ms) <= tol:
            return row
    raise AssertionError(f"{target_speed_ms} m/s dogrulama noktasi bulunamadi")


# 2) Kesif: '21 temmuz' klasoru ve .bin uzantisi.
def test_find_july21_log_root_and_bin():
    root = menzil2.find_july21_log_root()
    assert root.is_dir()
    assert root.name.lower().startswith("21 temmuz")
    bin_path = menzil2.find_july21_bin_path(root)
    assert bin_path.suffix.lower() == ".bin"
    assert bin_path.exists()
    session = menzil2.find_july21_datalink_session(root)
    assert session.name == menzil2.JULY21_DATALINK_SESSION_NAME


# 4) Tam 10 kesintisiz [2,3,4,5] tur.
def test_july21_has_exactly_ten_uninterrupted_laps():
    root = menzil2.find_july21_log_root()
    bin_path = menzil2.find_july21_bin_path(root)
    _span, series = menzil2._read_july21_ardupilot_series(bin_path)
    flight_start, flight_end = menzil2._identify_july21_long_flight(series)
    laps = menzil2._build_july21_laps(series, flight_start, flight_end)
    uninterrupted = [
        lap
        for lap in laps
        if lap["mission_items"] == menzil2.JULY21_UNINTERRUPTED_LAP_ITEMS
    ]
    assert len(uninterrupted) == 10


# 1) July3 regresyonu: 21 Temmuz kodu yuklendikten sonra July3 suite ayni kalir.
def test_july3_suite_unchanged_with_july21_present(july3_suite):
    # Tek-kol hover ~757.89 W, arac 6S2P ~1515.78 W (devir notu temel degerleri).
    assert july3_suite["power_reference_w"] == pytest.approx(757.891, abs=0.5)
    assert july3_suite["vehicle_measured_hover_power_w"] == pytest.approx(
        1515.782, abs=1.0
    )
    # 3 Temmuz fit hiz kutusu sayisi 11.
    assert len(july3_suite["observations"]) == 11


# 6) Tek-kol x2 arac olcegi; oran ikiyle ikinci kez carpilmaz.
def test_vehicle_power_is_single_arm_times_parallel_arms(july3_suite):
    assert menzil2.FIRFIR_BATTERY_PARALLEL_ARMS == 2
    assert july3_suite["vehicle_measured_hover_power_w"] == pytest.approx(
        july3_suite["measured_hover_power_w"] * menzil2.FIRFIR_BATTERY_PARALLEL_ARMS,
        rel=1e-9,
    )


# 3) + 5) + 6) Saat duzeltmesi + residual toleransi + tek-kol x2 birlikte.
def test_july21_validation_reproduces_reference_high_speed_points(validation):
    meta = validation["metadata"]
    assert meta["clock_correction_s"] == pytest.approx(-56.18)
    assert meta["prop_diameter_inch"] == 28.0
    assert meta["uninterrupted_lap_count"] == 10
    # Referans: duzeltilip birlestirilen ornek ~30782.
    assert meta["joined_sample_count"] == pytest.approx(30782, abs=200)

    # Kararli-hal kapisi (|accel| <= 1.0 m/s2) sonrasi altin degerler: seyir
    # kutulari yalniz kararli ornekleri tasidigindan medyan biraz duser, ama
    # iyi orneklenen 17 m/s seyri hala fit'e ~%1-2 icinde oturur.
    row_16 = _train_row(validation, 16.915)
    assert row_16["sample_count"] > 3000  # iyi orneklenen kararli seyir
    assert row_16["measured_vehicle_power_w"] == pytest.approx(1848.269, abs=3.0)
    assert row_16["zeng_datalink_fit_residual_percent"] == pytest.approx(-0.719, abs=0.3)
    assert row_16["faessler_datalink_fit_residual_percent"] == pytest.approx(
        0.279, abs=0.3
    )
    assert row_16["kirschstein_datalink_fit_residual_percent"] == pytest.approx(
        -1.869, abs=0.3
    )

    row_17 = _train_row(validation, 17.075)
    assert row_17["sample_count"] > 3000
    assert row_17["measured_vehicle_power_w"] == pytest.approx(1832.384, abs=3.0)
    assert row_17["zeng_datalink_fit_residual_percent"] == pytest.approx(-2.285, abs=0.3)
    assert row_17["faessler_datalink_fit_residual_percent"] == pytest.approx(
        -1.246, abs=0.3
    )
    assert row_17["kirschstein_datalink_fit_residual_percent"] == pytest.approx(
        -3.480, abs=0.3
    )


# 3) Saat duzeltmesi olmadan yuksek-hiz residualleri belirgin sekilde bozulur:
# yalnizca en-yakin-timestamp eslesmesi yeterli degildir.
def test_july21_clock_correction_matters(monkeypatch, july3_suite):
    corrected = menzil2.run_july21_validation_against_july3(
        july3_suite, make_graph=False
    )
    monkeypatch.setattr(menzil2, "JULY21_DATALINK_CLOCK_AHEAD_S", 0.0)
    shifted = menzil2.run_july21_validation_against_july3(
        july3_suite, make_graph=False
    )

    def high_speed_zeng_abs_residuals(result):
        # Kararli-hal kapisi sonrasi yalniz yuksek-hiz (>=16 m/s) iyi orneklenen
        # seyir kutulari fit'e ~%2-3 icinde oturur; dusuk/orta hizda gorev
        # geometrisi cezasi vardir.
        return [
            abs(row["zeng_datalink_fit_residual_percent"])
            for row in result["validation_rows"]
            if row["phase"] == menzil2.JULY21_TRAIN_PHASE
            and row["speed_ms"] >= 16.0
        ]

    corrected_res = high_speed_zeng_abs_residuals(corrected)
    shifted_res = high_speed_zeng_abs_residuals(shifted)
    assert corrected_res and max(corrected_res) < 3.5
    # Ofset kaldirilinca ayni yuksek-hiz kutulari fiziksel olarak yanlis anlarla
    # eslesir ve residual belirgin buyur.
    assert shifted_res
    assert max(shifted_res) > max(corrected_res)


# Kararli-hal kapisi: dogrulama yalniz ilk-10-tur + dusuk-ivme; mudahale yok.
def test_validation_uses_only_steady_state_points(validation):
    # Pilot mudahalesi sonrasi faz dogrulamaya HIC girmez.
    phases = {row["phase"] for row in validation["validation_rows"]}
    assert phases == {"ilk_10_kesintisiz_tur"}
    assert "pilot_mudahalesi_sonrasi" not in validation["residual_summary"]
    assert menzil2.JULY21_VALIDATION_PHASES == ("ilk_10_kesintisiz_tur",)
    assert menzil2.JULY21_STEADY_MAX_ACCEL_MS2 == pytest.approx(1.0)
    # Kararli kapi tum ornekleri kabul eden hali daha az kutu birakir.
    steady = menzil2.build_july21_validation_observations(
        validation["joined_samples"], "ilk_10_kesintisiz_tur",
        validation["power_reference_w"],
    )
    all_pts = menzil2.build_datalink_speed_observations(
        [r for r in validation["joined_samples"]
         if r.get("validation_phase") == "ilk_10_kesintisiz_tur"
         and 2.0 <= r.get("speed_ms", -1) <= 20.0],
        min_speed_ms=2.0, max_speed_ms=20.0, bin_width_ms=1.0, min_samples=80,
        power_reference_w=validation["power_reference_w"], stable_only=True,
        min_stable_fraction=0.5,
    )
    assert len(steady) < len(all_pts)


# 7) + 8) Birlesik fit: post-mudahale dislanir, 28"/29" metadatasi korunur.
def test_combined_fit_excludes_post_intervention_and_keeps_prop_metadata():
    profile, sonuc, hover_power_w, battery_wh, correction_factor = _firfir_context()
    combined = menzil2.build_combined_july3_july21_fit_suite(
        profile, sonuc, hover_power_w, battery_wh, correction_factor
    )
    assert "pilot_mudahalesi_sonrasi" in combined["excluded_phases"]
    assert "gorev_disi" in combined["excluded_phases"]

    sources = {obs.get("flight_source") for obs in combined["observations"]}
    assert sources == {"2026-07-03", "2026-07-21"}
    # July21 egitim gozlemleri yalniz ilk 10 kesintisiz turdan.
    july21_obs = [
        obs for obs in combined["observations"] if obs.get("flight_source") == "2026-07-21"
    ]
    assert all(
        obs.get("validation_phase") == menzil2.JULY21_TRAIN_PHASE for obs in july21_obs
    )
    assert combined["july3_observation_count"] == 11
    assert combined["july21_train_observation_count"] == len(july21_obs)

    # 2-serbest-parametre bilimsel audit hala uygulanir.
    assert set(combined["fit_audit"]["models"]) == {
        "zeng_measured_fit",
        "faessler_measured_fit",
        "kirschstein_measured_fit",
    }
    # 21 Temmuz pervanesi 28"; fit profilinin 29" metadatasi ezilmemis.
    assert menzil2.JULY21_PROP_DIAMETER_INCH == 28.0


# Kesif katmani: hem root/UART-* hem root/Datalink/UART-* duzeni.
def test_resolve_datalink_session_root_supports_both_layouts():
    july3_root = Path("3 Temmuz Tüm Test Logları")
    july21_root = menzil2.find_july21_log_root()
    assert menzil2.resolve_datalink_session_root(july3_root).name == "Datalink"
    assert menzil2.resolve_datalink_session_root(july21_root) == july21_root


def test_discover_datalink_log_roots_lists_both_flights_with_hints():
    entries = {e["label"]: e for e in menzil2.discover_datalink_log_roots()}
    july3 = next(v for k, v in entries.items() if k.startswith("3 Temmuz"))
    july21 = next(v for k, v in entries.items() if k.lower().startswith("21 temmuz"))
    assert "260703" in july3["date_hints"] and july3["has_bin"]
    assert july21["date_hints"] == ["260721"] and july21["has_bin"]


# Ortak (menu-3 elle giris / menu-5 ham veri) pipeline 21 Temmuz'u isleyebilmeli:
# oturum kokte, .bin kucuk harf, oturuma ozel -56.18 s duzeltmesi haritadan.
def test_shared_pipeline_processes_july21_root_with_clock_map():
    assert menzil2.DATALINK_SESSION_CLOCK_CORRECTION_S[
        menzil2.JULY21_DATALINK_SESSION_NAME
    ] == pytest.approx(-56.18)
    # Kisa ucus oturumuna dogrulanmamis ofset uygulanmaz (devir notu).
    assert "UART-260721-161227" not in menzil2.DATALINK_SESSION_CLOCK_CORRECTION_S

    import math

    preset = dict(menzil2.FIRFIR_SPEED_PRESET)
    vi_h = math.sqrt(
        preset["mass_kg"]
        * 9.81
        / (2.0 * preset.get("rho", 1.225) * menzil2._disc_area_total_m2(preset))
    )
    result = menzil2.run_datalink_measured_curve_analysis(
        preset,
        {"vi_h": vi_h},
        1000.0,
        1000.0,
        1.0,
        log_root=menzil2.find_july21_log_root(),
        date_hint="260721",
        make_graph=False,
    )
    assert result["joined_sample_count"] > 30000
    assert len(result["speed_bin_observations"]) >= 10
    assert result["empirical_curve"].get("measured_points")
    accepted_sessions = {
        row["session"]
        for row in result["sync_report"]
        if row["accepted_for_fit"]
    }
    assert menzil2.JULY21_DATALINK_SESSION_NAME in accepted_sessions


# Grafik modu: yeni July21 dosya adlari July3'ten ayri, uretiliyor.
def test_july21_validation_emits_separate_graph_files(july3_suite, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = menzil2.run_july21_validation_against_july3(july3_suite, make_graph=True)
    assert (tmp_path / menzil2.JULY21_VALIDATION_RATIO_OUTPUT_PATH).exists()
    assert (tmp_path / menzil2.JULY21_VALIDATION_POWER_OUTPUT_PATH).exists()
    assert menzil2.JULY21_VALIDATION_RATIO_OUTPUT_PATH not in {
        menzil2.DATALINK_EMPIRICAL_OUTPUT_PATH,
        menzil2.DATALINK_DIAGNOSTIC_SURROGATE_OUTPUT_PATH,
    }
    assert result["graph_paths"]
