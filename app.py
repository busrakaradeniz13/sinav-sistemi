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
    """PostgreSQL (Neon) bulut veritabanına güvenli bağlanır."""
    if DATABASE_URL:
        url = DATABASE_URL
        if "sslmode" not in url:
            url += "?sslmode=require" if "?" not in url else "&sslmode=require"
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        return conn
    else:
        raise Exception("DATABASE_URL ortam değişkeni bulunamadı!")

def veritabani_kur():
    """Bulut veritabanında tüm tabloları ve online sınav tablolarını otomatik oluşturur."""
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()

        # Öğrenciler tablosu
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

        # Sınavlar (Karne / Notlar) tablosu
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

        # Genel Ziyaret ve Sorgulama Sayacı
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

        # ONLINE SINAV MODÜLÜ TABLOLARI
        # 1. Sorular Tablosu
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

        # 2. Test Ayarları ve Yayın Durumu Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_ayarlari (
                test_adi TEXT PRIMARY KEY,
                sure_dakika INTEGER DEFAULT 30,
                yayinlandi BOOLEAN DEFAULT FALSE
            )
        """)

        # 3. Öğrenci Online Sınav Sonuçları Tablosu
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

    # Yayınlanmış aktif online sınavları veritabanından çek
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


# --- ONLINE SINAV ÇÖZME SAYFASI ---
@app.route("/online-sinav/<test_adi>/<ogrenci_no>", methods=["GET", "POST"])
def online_sinav_coz(test_adi, ogrenci_no):
    sinav_verileri = sinav_verilerini_getir()
    if ogrenci_no not in sinav_verileri:
        flash("Geçersiz öğrenci!", "error")
        return redirect(url_for("veli_sorgula"))

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        
        # Test ayarlarını al
        cursor.execute("SELECT * FROM test_ayarlari WHERE test_adi = %s AND yayinlandi = TRUE", (test_adi,))
        test_ayar = cursor.fetchone()
        if not test_ayar:
            flash("Bu sınav aktif değil veya yayınlanmamış.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("veli_sorgula"))

        # Daha önce çözmüş mü kontrol et
        cursor.execute("SELECT * FROM ogrenci_online_sonuclar WHERE ogrenci_no = %s AND test_adi = %s", (ogrenci_no, test_adi))
        daha_once_cozmus = cursor.fetchone()

        # Soruları getir
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

            # Puan hesapla (100 üzerinden)
            puan = int((dogru_sayisi / toplam_soru) * 100) if toplam_soru > 0 else 0
            tarih_str = datetime.now(TURKEY_TZ).strftime("%d.%m.%Y %H:%M")

            # Sonucu kaydet
            cursor.execute(
                """
                INSERT INTO ogrenci_online_sonuclar (ogrenci_no, test_adi, dogru, yanlis, bos, puan, tarih)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ogrenci_no, test_adi) DO NOTHING
                """,
                (ogrenci_no, test_adi, dogru_sayisi, yanlis_sayisi, bos_sayisi, puan, tarih_str)
            )

            # Ayrıca ana sinavlar tablosuna da ekle ki karneye işlensin
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


# --- ADMIN PANELİ ---
@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    sinav_verileri = sinav_verilerini_getir()
    toplam_ziyaret, toplam_sorgu = genel_istatistikleri_oku()

    # Aktif testleri ve soruları admin için getir
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


# --- YENİ: SORU EKLEME ROUTE ---
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

            # Test ayarlarını kaydet veya güncelle (varsayılan olarak yayınlanmamış başlar)
            cursor.execute(
                """
                INSERT INTO test_ayarlari (test_adi, sure_dakika, yayinlandi)
                VALUES (%s, %s, FALSE)
                ON CONFLICT (test_adi) DO UPDATE SET sure_dakika = EXCLUDED.sure_dakika
                """,
                (test_adi, sure)
            )

            # Soruyu ekle
            cursor.execute(
                """
                INSERT INTO sorular (test_adi, soru_metni, secenek_a, secenek_b, secenek_c, secenek_d, dogru_cevap)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (test_adi, soru_metni, secenek_a, secenek_b, secenek_c, secenek_d, dogru_cevap)
            )

            conn.commit()
            cursor.close()
            conn.close()
            flash("Soru başarıyla eklendi!", "success")
        except Exception as e:
            flash(f"Soru ekleme hatası: {e}", "error")

    return redirect(url_for("admin_panel"))


# --- YENİ: TESTİ YAYINLA / YAYINDAN KALDIR ---
@app.route("/admin/test-yayinla/<test_adi>")
def test_yayinla(test_adi):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        # Mevcut yayın durumunu tersine çevir
        cursor.execute("SELECT yayinlandi FROM test_ayarlari WHERE test_adi = %s", (test_adi,))
        res = cursor.fetchone()
        if res:
            yeni_durum = not res["yayinlandi"]
            cursor.execute("UPDATE test_ayarlari SET yayinlandi = %s WHERE test_adi = %s", (yeni_durum, test_adi))
            conn.commit()
            durum_metni = "yayına alındı!" if yeni_durum else "yayından kaldırıldı."
            flash(f"'{test_adi'}' başarıyla {durum_metni}", "success")
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"İşlem hatası: {e}", "error")

    return redirect(url_for("admin_panel"))


# --- YENİ: SORU SİL ---
@app.route("/admin/soru-sil/<int:soru_id>")
def soru_sil(soru_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sorular WHERE id = %s", (soru_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Soru silindi.", "info")
    except Exception as e:
        flash(f"Silme hatası: {e}", "error")

    return redirect(url_for("admin_panel"))


@app.route("/admin/ogrenci-ara/<ogrenci_no>")
def ogrenci_ara(ogrenci_no):
    if not session.get("admin_logged_in"):
        return jsonify({"bulundu": False})

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ad FROM ogrenciler WHERE ogrenci_no = %s", (str(ogrenci_no).strip(),)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            return jsonify({"bulundu": True, "ad": row["ad"]})
    except:
        pass
    return jsonify({"bulundu": False})


@app.route("/admin/kaydet", methods=["POST"])
def ogrenci_kaydet():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    ogrenci_no = request.form.get("ogrenci_no", "").strip()
    ad = request.form.get("ad", "").strip()
    sinav_adi = request.form.get("sinav", "Genel Sınav").strip()
    derece = request.form.get("derece", "").strip()

    if sinav_adi:
        session["son_sinav_adi"] = sinav_adi

    try:
        dogru = int(request.form.get("dogru", 0))
        yanlis = int(request.form.get("yanlis", 0))
        bos = int(request.form.get("bos", 0))
        puan = int(request.form.get("puan", 0))
    except ValueError:
        dogru, yanlis, bos, puan = 0, 0, 0, 0

    if ogrenci_no and ad:
        try:
            conn = db_baglantisi()
            cursor = conn.cursor()

            cursor.execute(
                """
                    INSERT INTO ogrenciler (ogrenci_no, ad, sorgu_sayisi, son_sorgu_tarihi) 
                    VALUES (%s, %s, 0, '-')
                    ON CONFLICT (ogrenci_no) DO UPDATE SET ad = EXCLUDED.ad
                """,
                (ogrenci_no, ad),
            )

            cursor.execute(
                """
                    INSERT INTO sinavlar (ogrenci_no, sinav, dogru, yanlis, bos, puan, derece)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ogrenci_no, sinav) DO UPDATE SET
                        dogru = EXCLUDED.dogru,
                        yanlis = EXCLUDED.yanlis,
                        bos = EXCLUDED.bos,
                        puan = EXCLUDED.puan,
                        derece = EXCLUDED.derece
                """,
                (ogrenci_no, sinav_adi, dogru, yanlis, bos, puan, derece),
            )

            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Başarılı: {ad} - {sinav_adi} kaydedildi.", "success")
        except Exception as e:
            flash(f"Kayıt hatası: {str(e)}", "error")

    return redirect(url_for("admin_panel"))


@app.route("/admin/ogrenci-sil/<ogrenci_no>")
def ogrenci_sil(ogrenci_no):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sinavlar WHERE ogrenci_no = %s", (str(ogrenci_no),))
        cursor.execute("DELETE FROM ogrenciler WHERE ogrenci_no = %s", (str(ogrenci_no),))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Öğrenci veritabanından silindi.", "info")
    except Exception as e:
        flash(f"Silme hatası: {e}", "error")

    return redirect(url_for("admin_panel"))


@app.route("/admin/sinav-sil/<ogrenci_no>/<path:sinav_adi>")
def sinav_sil(ogrenci_no, sinav_adi):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM sinavlar WHERE ogrenci_no = %s AND sinav = %s",
            (str(ogrenci_no), sinav_adi),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Sınav sonucu silindi.", "info")
    except Exception as e:
        flash(f"Silme hatası: {e}", "error")

    return redirect(url_for("admin_panel"))


@app.route("/admin/excel-yukle", methods=["POST"])
def excel_yukle():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    dosya = request.files.get("excel_dosya")
    if dosya:
        try:
            df = pd.read_excel(dosya)
            df.columns = [str(col).strip().lower() for col in df.columns]

            conn = db_baglantisi()
            cursor = conn.cursor()

            for _, row in df.iterrows():
                no = str(
                    row.get("ogrenci_no", row.get("no", row.get("okul_no", "0")))
                ).strip()
                ad = str(row.get("ad", row.get("ad_soyad", "İsimsiz"))).strip()
                sinav_adi = str(
                    row.get("sinav", row.get("sinav_adi", "Genel Sınav"))
                ).strip()

                try:
                    dogru = int(
                        row.get("dogru", 0) if pd.notna(row.get("dogru", 0)) else 0
                    )
                    yanlis = int(
                        row.get("yanlis", 0) if pd.notna(row.get("yanlis", 0)) else 0
                    )
                    bos = int(row.get("bos", 0) if pd.notna(row.get("bos", 0)) else 0)
                    puan = int(row.get("puan", 0) if pd.notna(row.get("puan", 0)) else 0)
                    derece = str(
                        row.get("derece", "") if pd.notna(row.get("derece", "")) else ""
                    ).strip()
                    if derece == "nan":
                        derece = ""
                except:
                    dogru, yanlis, bos, puan, derece = 0, 0, 0, 0, ""

                if no and no != "nan":
                    cursor.execute(
                        """
                            INSERT INTO ogrenciler (ogrenci_no, ad, sorgu_sayisi, son_sorgu_tarihi) 
                            VALUES (%s, %s, 0, '-')
                            ON CONFLICT (ogrenci_no) DO UPDATE SET ad = EXCLUDED.ad
                        """,
                        (no, ad),
                    )

                    cursor.execute(
                        """
                            INSERT INTO sinavlar (ogrenci_no, sinav, dogru, yanlis, bos, puan, derece)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ogrenci_no, sinav) DO UPDATE SET
                                dogru = EXCLUDED.dogru,
                                yanlis = EXCLUDED.yanlis,
                                bos = EXCLUDED.bos,
                                puan = EXCLUDED.puan,
                                derece = EXCLUDED.derece
                        """,
                        (no, sinav_adi, dogru, yanlis, bos, puan, derece),
                    )

            conn.commit()
            cursor.close()
            conn.close()

            flash("Excel verileri bulut veritabanına aktarıldı!", "success")
        except Exception as e:
            flash(f"Excel yüklenirken hata: {str(e)}", "error")

    return redirect(url_for("admin_panel"))


@app.route("/admin/excel-indir")
def excel_indir():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))

    try:
        sinav_verileri = sinav_verilerini_getir()
        satirlar = []

        for no, bilgi in sinav_verileri.items():
            ad = bilgi["ad"]
            for s in bilgi["sinavlar"]:
                satirlar.append({
                    "ogrenci_no": no,
                    "ad": ad,
                    "sinav": s["sinav"],
                    "dogru": s["dogru"],
                    "yanlis": s["yanlis"],
                    "bos": s["bos"],
                    "puan": s["puan"],
                    "derece": s.get("derece", ""),
                })

        df = pd.DataFrame(satirlar)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="Büşra Güngör Öğrenci Sınav Sonuçları.xlsx",
            mimetype=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
    except Exception as e:
        flash(f"İndirme sırasında bir hata oluştu: {str(e)}", "error")
        return redirect(url_for("admin_panel"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
