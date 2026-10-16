import io
import os
from datetime import datetime, timezone, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
import pandas as pd

app = Flask(__name__)
app.secret_key = "ogretmen_cok_gizli_guvenlik_anahtari_98765"

ADMIN_PASSWORD = "15698"

DATABASE_URL = os.environ.get("DATABASE_URL")

# Türkiye Saat Dilimi (UTC+3)
TURKEY_TZ = timezone(timedelta(hours=3))

def db_baglantisi():
    if DATABASE_URL:
        url = DATABASE_URL
        if "sslmode" not in url:
            url += "?sslmode=require" if "?" not in url else "&sslmode=require"
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        return conn
    else:
        raise Exception("DATABASE_URL ortam değişkeni bulunamadı!")

def veritabani_kur():
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ogrenciler (
                ogrenci_no TEXT PRIMARY KEY,
                ad TEXT NOT NULL,
                sorgu_sayisi INTEGER DEFAULT 0,
                son_sorgu_tarihi TEXT DEFAULT '-'
            )
        """)
        cursor.execute("ALTER TABLE ogrenciler ADD COLUMN IF NOT EXISTS sorgu_sayisi INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE ogrenciler ADD COLUMN IF NOT EXISTS son_sorgu_tarihi TEXT DEFAULT '-'")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sinavlar (
                id SERIAL PRIMARY KEY,
                ogrenci_no TEXT NOT NULL,
                sinav TEXT NOT NULL,
                dogru INTEGER DEFAULT 0,
                yanlis INTEGER DEFAULT 0,
                bos INTEGER DEFAULT 0,
                puan INTEGER DEFAULT 0,
                derece TEXT DEFAULT '',
                FOREIGN KEY (ogrenci_no) REFERENCES ogrenciler (ogrenci_no) ON DELETE CASCADE,
                UNIQUE(ogrenci_no, sinav)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS istatistikler (
                id INTEGER PRIMARY KEY,
                toplam_ziyaret INTEGER DEFAULT 0,
                toplam_sorgu INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO istatistikler (id, toplam_ziyaret, toplam_sorgu)
            VALUES (1, 0, 0)
            ON CONFLICT (id) DO NOTHING
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sorular (
                id SERIAL PRIMARY KEY,
                test_adi TEXT NOT NULL,
                soru_metni TEXT NOT NULL,
                secenek_a TEXT NOT NULL,
                secenek_b TEXT NOT NULL,
                secenek_c TEXT NOT NULL,
                secenek_d TEXT NOT NULL,
                dogru_cevap TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_ayarlari (
                test_adi TEXT PRIMARY KEY,
                sure_dakika INTEGER DEFAULT 30,
                yayinlandi BOOLEAN DEFAULT FALSE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ogrenci_online_sonuclar (
                id SERIAL PRIMARY KEY,
                ogrenci_no TEXT NOT NULL,
                test_adi TEXT NOT NULL,
                dogru INTEGER DEFAULT 0,
                yanlis INTEGER DEFAULT 0,
                bos INTEGER DEFAULT 0,
                puan INTEGER DEFAULT 0,
                tarih TEXT DEFAULT '-',
                UNIQUE(ogrenci_no, test_adi)
            )
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print("Bulut veritabanı ve online sınav tabloları hazır.")
    except Exception as e:
        print(f"Veritabanı kurulum hatası: {e}")

veritabani_kur()

def genel_istatistik_arttir(tip="ziyaret"):
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        if tip == "ziyaret":
            cursor.execute("UPDATE istatistikler SET toplam_ziyaret = toplam_ziyaret + 1 WHERE id = 1")
        elif tip == "sorgu":
            cursor.execute("UPDATE istatistikler SET toplam_sorgu = toplam_sorgu + 1 WHERE id = 1")
        conn.commit()
        cursor.close()
        conn.close()
    except:
        pass

def genel_istatistikleri_oku():
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("SELECT toplam_ziyaret, toplam_sorgu FROM istatistikler WHERE id = 1")
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        if res:
            return res["toplam_ziyaret"], res["toplam_sorgu"]
    except:
        pass
    return 0, 0

def sinav_verilerini_getir():
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM ogrenciler")
        ogrenci_satirlari = cursor.fetchall()

        veriler = {}
        for ogrenci in ogrenci_satirlari:
            no = ogrenci["ogrenci_no"]
            ad = ogrenci["ad"]
            sorgu_sayisi = ogrenci.get("sorgu_sayisi", 0)
            son_sorgu_tarihi = ogrenci.get("son_sorgu_tarihi", "-")

            cursor.execute(
                "SELECT * FROM sinavlar WHERE ogrenci_no = %s ORDER BY id ASC", (no,)
            )
            sinav_satirlari = cursor.fetchall()

            sinavlar = []
            for s in sinav_satirlari:
                sinavlar.append({
                    "sinav": s["sinav"],
                    "dogru": s["dogru"],
                    "yanlis": s["yanlis"],
                    "bos": s["bos"],
                    "puan": s["puan"],
                    "derece": s["derece"] if s["derece"] else "",
                })

            veriler[no] = {
                "ad": ad,
                "sorgu_sayisi": sorgu_sayisi,
                "son_sorgu_tarihi": son_sorgu_tarihi,
                "sinavlar": sinavlar
            }

        cursor.close()
        conn.close()
        return veriler
    except Exception as e:
        print(f"Veri getirme hatası: {e}")
        return {}


@app.route("/", methods=["GET", "POST"])
def veli_sorgula():
    sonuc, hata = None, None
    en_son_derece = None
    sinav_verileri = sinav_verilerini_getir()
    aktif_testler = []

    if request.method == "GET":
        genel_istatistik_arttir("ziyaret")

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM test_ayarlari WHERE yayinlandi = TRUE")
        aktif_testler = cursor.fetchall()
        cursor.close()
        conn.close()
    except:
        pass

    if request.method == "POST":
        genel_istatistik_arttir("sorgu")
        ogrenci_no = request.form.get("ogrenci_no", "").strip()

        if not ogrenci_no:
            hata = "Lütfen geçerli bir öğrenci numarası giriniz."
        elif ogrenci_no in sinav_verileri:
            try:
                simdi = datetime.now(TURKEY_TZ).strftime("%d.%m.%Y %H:%M")
                conn = db_baglantisi()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE ogrenciler 
                    SET sorgu_sayisi = sorgu_sayisi + 1, son_sorgu_tarihi = %s 
                    WHERE ogrenci_no = %s
                    """,
                    (simdi, ogrenci_no)
                )
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"Sayaç güncelleme hatası: {e}")

            sinav_verileri = sinav_verilerini_getir()
            ham_veri = sinav_verileri[ogrenci_no]
            ters_sinavlar = list(reversed(ham_veri.get("sinavlar", [])))
            sonuc = {"ogrenci_no": ogrenci_no, "ad": ham_veri["ad"], "sinavlar": ters_sinavlar}

            if ters_sinavlar:
                en_son_sinav = ters_sinavlar[0]
                d_val = (
                    str(en_son_sinav.get("derece", "")).replace(".", "").strip().lower()
                )
                if d_val in ["1", "2", "3"]:
                    en_son_derece = d_val
        else:
            hata = "Bu numaraya ait öğrenci veya sınav sonucu bulunamadı."

    return render_template(
        "sorgula.html",
        sonuc=sonuc,
        hata=hata,
        en_son_derece=en_son_derece,
        aktif_testler=aktif_testler
    )


@app.route("/online-sinav/<test_adi>/<ogrenci_no>", methods=["GET", "POST"])
def online_sinav_coz(test_adi, ogrenci_no):
    sinav_verileri = sinav_verilerini_getir()
    if ogrenci_no not in sinav_verileri:
        flash("Geçersiz öğrenci!", "error")
        return redirect(url_for("veli_sorgula"))

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM test_ayarlari WHERE test_adi = %s AND yayinlandi = TRUE", (test_adi,))
        test_ayar = cursor.fetchone()
        if not test_ayar:
            flash("Bu sınav aktif değil veya yayınlanmamış.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("veli_sorgula"))

        cursor.execute("SELECT * FROM ogrenci_online_sonuclar WHERE ogrenci_no = %s AND test_adi = %s", (ogrenci_no, test_adi))
        daha_once_cozmus = cursor.fetchone()

        cursor.execute("SELECT * FROM sorular WHERE test_adi = %s ORDER BY id ASC", (test_adi,))
        sorular = cursor.fetchall()

        if request.method == "POST":
            if daha_once_cozmus:
                flash("Bu sınavı daha önce zaten tamamladınız!", "error")
                return redirect(url_for("veli_sorgula"))

            dogru_sayisi = 0
            yanlis_sayisi = 0
            bos_sayisi = 0
            toplam_soru = len(sorular)

            for soru in sorular:
                soru_id_str = str(soru["id"])
                ogrenci_cevabi = request.form.get(f"soru_{soru_id_str}")
                
                if not ogrenci_cevabi:
                    bos_sayisi += 1
                elif ogrenci_cevabi.strip().upper() == soru["dogru_cevap"].strip().upper():
                    dogru_sayisi += 1
                else:
                    yanlis_sayisi += 1

            puan = int((dogru_sayisi / toplam_soru) * 100) if toplam_soru > 0 else 0
            tarih_str = datetime.now(TURKEY_TZ).strftime("%d.%m.%Y %H:%M")

            cursor.execute(
                """
                INSERT INTO ogrenci_online_sonuclar (ogrenci_no, test_adi, dogru, yanlis, bos, puan, tarih)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ogrenci_no, test_adi) DO NOTHING
                """,
                (ogrenci_no, test_adi, dogru_sayisi, yanlis_sayisi, bos_sayisi, puan, tarih_str)
            )

            cursor.execute(
                """
                INSERT INTO sinavlar (ogrenci_no, sinav, dogru, yanlis, bos, puan, derece)
                VALUES (%s, %s, %s, %s, %s, %s, '')
                ON CONFLICT (ogrenci_no, sinav) DO UPDATE SET
                    dogru = EXCLUDED.dogru,
                    yanlis = EXCLUDED.yanlis,
                    bos = EXCLUDED.bos,
                    puan = EXCLUDED.puan
                """,
                (ogrenci_no, f"Online: {test_adi}", dogru_sayisi, yanlis_sayisi, bos_sayisi, puan)
            )

            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Sınavınız başarıyla gönderildi! Puanınız: {puan}", "success")
            return redirect(url_for("veli_sorgula"))

        cursor.close()
        conn.close()

        return render_template(
            "sinav_coz.html",
            ogrenci=sinav_verileri[ogrenci_no],
            ogrenci_no=ogrenci_no,
            test_adi=test_adi,
            sure=test_ayar["sure_dakika"],
            sorular=sorular,
            daha_once_cozmus=daha_once_cozmus
        )
    except Exception as e:
        flash(f"Sınav yüklenirken hata oluştu: {e}", "error")
        return redirect(url_for("veli_sorgula"))


@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    sinav_verileri = sinav_verilerini_getir()
    toplam_ziyaret, toplam_sorgu = genel_istatistikleri_oku()

    tum_sorular = []
    test_listesi = []
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sorular ORDER BY test_adi, id ASC")
        tum_sorular = cursor.fetchall()
        
        cursor.execute("SELECT * FROM test_ayarlari")
        test_listesi = cursor.fetchall()
        cursor.close()
        conn.close()
    except:
        pass

    if request.method == "POST":
        sifre = request.form.get("sifre", "").strip()
        if sifre == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
        else:
            flash("Hatalı şifre!", "error")
            return render_template(
                "admin.html",
                veriler=sinav_verileri,
                giris_yapildi=False,
                son_sinav="",
                toplam_ziyaret=toplam_ziyaret,
                toplam_sorgu=toplam_sorgu,
                tum_sorular=tum_sorular,
                test_listesi=test_listesi
            )

    if not session.get("admin_logged_in"):
        return render_template(
            "admin.html", veriler=sinav_verileri, giris_yapildi=False, son_sinav="",
            toplam_ziyaret=toplam_ziyaret, toplam_sorgu=toplam_sorgu,
            tum_sorular=tum_sorular, test_listesi=test_listesi
        )

    son_sinav = session.get("son_sinav_adi", "")
    return render_template(
        "admin.html",
        veriler=sinav_verileri,
        giris_yapildi=True,
        son_sinav=son_sinav,
        toplam_ziyaret=toplam_ziyaret,
        toplam_sorgu=toplam_sorgu,
        tum_sorular=tum_sorular,
        test_listesi=test_listesi
    )


@app.route("/admin/cikis")
def admin_cikis():
    session.clear()
    return redirect(url_for("admin_panel"))


@app.route("/admin/soru-ekle", methods=["POST"])
def soru_ekle():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    test_adi = request.form.get("test_adi", "").strip()
    sure = int(request.form.get("sure", 30))
    soru_metni = request.form.get("soru_metni", "").strip()
    secenek_a = request.form.get("secenek_a", "").strip()
    secenek_b = request.form.get("secenek_b", "").strip()
    secenek_c = request.form.get("secenek_c", "").strip()
    secenek_d = request.form.get("secenek_d", "").strip()
    dogru_cevap = request.form.get("dogru_cevap", "").strip().upper()

    if test_adi and soru_metni and dogru_cevap:
        try:
            conn = db_baglantisi()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO test_ayarlari (test_adi, sure_dakika, yayinlandi)
                VALUES (%s, %s, FALSE)
                ON CONFLICT (test_adi) DO UPDATE SET sure_dakika = EXCLUDED.sure_dakika
                """,
                (test_adi, sure)
            )

            cursor.execute(
                """
                INSERT INTO sorular (test_adi, soru_metni, secenek_a, secenek_b, secenek_c, secenek_d, dogru_cevap)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
