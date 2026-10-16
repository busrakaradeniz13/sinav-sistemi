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
app.secret_key = "uzman_ogretmen_guvenli_sistem_key_2026_v3"

ADMIN_PASSWORD = "15698"
DATABASE_URL = os.environ.get("DATABASE_URL")
TURKEY_TZ = timezone(timedelta(hours=3))

def db_baglantisi():
    if DATABASE_URL:
        url = DATABASE_URL
        if "sslmode" not in url:
            url += "?sslmode=require" if "?" not in url else "&sslmode=require"
        return psycopg2.connect(url, cursor_factory=RealDictCursor)
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
        cursor.execute("INSERT INTO istatistikler (id, toplam_ziyaret, toplam_sorgu) VALUES (1, 0, 0) ON CONFLICT (id) DO NOTHING")

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
    except Exception as e:
        print(f"DB Kurulum Hatası: {e}")

veritabani_kur()

def istatistik_getir():
    toplam_ziyaret, toplam_sorgu = 0, 0
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("SELECT toplam_ziyaret, toplam_sorgu FROM istatistikler WHERE id = 1")
        res = cursor.fetchone()
        if res:
            toplam_ziyaret = res["toplam_ziyaret"]
            toplam_sorgu = res["toplam_sorgu"]
        cursor.close()
        conn.close()
    except:
        pass
    return toplam_ziyaret, toplam_sorgu

def sinav_verilerini_getir():
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        # Numaraya göre küçükten büyüğe sırala (Azdan Çoğa)
        cursor.execute("SELECT * FROM ogrenciler ORDER BY CAST(ogrenci_no AS INTEGER) ASC ON CONFLICT DO NOTHING")
    except:
        try:
            cursor.execute("SELECT * FROM ogrenciler ORDER BY ogrenci_no ASC")
        except:
            return {}

    try:
        ogrenci_satirlari = cursor.fetchall()
        veriler = {}
        for ogrenci in ogrenci_satirlari:
            no = ogrenci["ogrenci_no"]
            ad = ogrenci["ad"]
            
            cursor.execute("SELECT * FROM sinavlar WHERE ogrenci_no = %s ORDER BY id ASC", (no,))
            sinavlar = [dict(s) for s in cursor.fetchall()]

            veriler[no] = {
                "ad": ad,
                "sorgu_sayisi": ogrenci.get("sorgu_sayisi", 0),
                "son_sorgu_tarihi": ogrenci.get("son_sorgu_tarihi", "-"),
                "sinavlar": sinavlar
            }
        cursor.close()
        conn.close()
        return veriler
    except Exception as e:
        print(f"Veri çekme hatası: {e}")
        return {}

@app.route("/", methods=["GET", "POST"])
def veli_sorgula():
    sonuc, hata = None, None
    en_son_derece = None
    
    # Ziyaret sayısını artır
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("UPDATE istatistikler SET toplam_ziyaret = toplam_ziyaret + 1 WHERE id = 1")
        conn.commit()
        cursor.close()
        conn.close()
    except:
        pass

    sinav_verileri = sinav_verilerini_getir()
    aktif_testler = []
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
        ogrenci_no = request.form.get("ogrenci_no", "").strip()
        if not ogrenci_no:
            hata = "Lütfen okul numarası giriniz."
        elif ogrenci_no in sinav_verileri:
            # Sorgu sayısını ve Türkiye saati bilgisini güncelle
            try:
                su an_tsi = datetime.now(TURKEY_TZ).strftime("%d.%m.%Y %H:%M")
                conn = db_baglantisi()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ogrenciler 
                    SET sorgu_sayisi = sorgu_sayisi + 1, son_sorgu_tarihi = %s 
                    WHERE ogrenci_no = %s
                """, (su an_tsi, ogrenci_no))
                cursor.execute("UPDATE istatistikler SET toplam_sorgu = toplam_sorgu + 1 WHERE id = 1")
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"Sorgu sayaç güncelleme hatası: {e}")

            ham = sinav_verileri[ogrenci_no]
            ters_sinavlar = list(reversed(ham["sinavlar"]))
            sonuc = {"ogrenci_no": ogrenci_no, "ad": ham["ad"], "sinavlar": ters_sinavlar}
            if ters_sinavlar:
                d = str(ters_sinavlar[0].get("derece", "")).replace(".", "").strip().lower()
                if d in ["1", "2", "3"]:
                    en_son_derece = d
        else:
            hata = "Bu numaraya ait öğrenci bulunamadı."

    return render_template("sorgula.html", sonuc=sonuc, hata=hata, en_son_derece=en_son_derece, aktif_testler=aktif_testler)

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
            return redirect(url_for("veli_sorgula"))

        cursor.execute("SELECT * FROM ogrenci_online_sonuclar WHERE ogrenci_no = %s AND test_adi = %s", (ogrenci_no, test_adi))
        daha_once = cursor.fetchone()

        cursor.execute("SELECT * FROM sorular WHERE test_adi = %s ORDER BY id ASC", (test_adi,))
        sorular = cursor.fetchall()

        if request.method == "POST":
            if daha_once:
                flash("Bu sınavı zaten tamamladınız!", "error")
                return redirect(url_for("veli_sorgula"))

            dogru, yanlis, bos = 0, 0, 0
            toplam = len(sorular)
            
            for s in sorular:
                cevap = request.form.get(f"soru_{s['id']}")
                if not cevap:
                    bos += 1
                elif cevap.strip().upper() == s["dogru_cevap"].strip().upper():
                    dogru += 1
                else:
                    yanlis += 1

            puan = int((dogru / toplam) * 100) if toplam > 0 else 0
            tarih_str = datetime.now(TURKEY_TZ).strftime("%d.%m.%Y %H:%M")

            cursor.execute("""
                INSERT INTO ogrenci_online_sonuclar (ogrenci_no, test_adi, dogru, yanlis, bos, puan, tarih)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ogrenci_no, test_adi) DO NOTHING
            """, (ogrenci_no, test_adi, dogru, yanlis, bos, puan, tarih_str))

            cursor.execute("""
                INSERT INTO sinavlar (ogrenci_no, sinav, dogru, yanlis, bos, puan, derece)
                VALUES (%s, %s, %s, %s, %s, %s, '')
                ON CONFLICT (ogrenci_no, sinav) DO UPDATE SET
                    dogru = EXCLUDED.dogru, yanlis = EXCLUDED.yanlis, bos = EXCLUDED.bos, puan = EXCLUDED.puan
            """, (ogrenci_no, f"Online: {test_adi}", dogru, yanlis, bos, puan))

            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Sınav tamamlandı! Puanınız: {puan}", "success")
            return redirect(url_for("veli_sorgula"))

        cursor.close()
        conn.close()
        return render_template("sinav_coz.html", ogrenci=sinav_verileri[ogrenci_no], ogrenci_no=ogrenci_no, test_adi=test_adi, sure=test_ayar["sure_dakika"], sorular=sorular, daha_once=daha_once)
    except Exception as e:
        flash(f"Sınav hatası: {e}", "error")
        return redirect(url_for("veli_sorgula"))

@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    sinav_verileri = sinav_verilerini_getir()
    toplam_ziyaret, toplam_sorgu = istatistik_getir()
    tum_sorular, test_listesi = [], []

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
        if request.form.get("sifre", "").strip() == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
        else:
            flash("Hatalı şifre!", "error")

    if not session.get("admin_logged_in"):
        return render_template("admin.html", giris_yapildi=False)

    return render_template(
        "admin.html", 
        giris_yapildi=True, 
        veriler=sinav_verileri, 
        tum_sorular=tum_sorular, 
        test_listesi=test_listesi,
        toplam_ziyaret=toplam_ziyaret,
        toplam_sorgu=toplam_sorgu
    )

@app.route("/admin/cikis")
def admin_cikis():
    session.clear()
    return redirect(url_for("admin_panel"))

@app.route("/admin/coklu-soru-ekle", methods=["POST"])
def coklu_soru_ekle():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    
    test_adi = request.form.get("test_adi", "").strip()
    sure = int(request.form.get("sure", 30))
    soru_sayisi = int(request.form.get("soru_sayisi", 1))

    if test_adi and soru_sayisi > 0:
        try:
            conn = db_baglantisi()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO test_ayarlari (test_adi, sure_dakika, yayinlandi) 
                VALUES (%s, %s, FALSE) 
                ON CONFLICT (test_adi) DO UPDATE SET sure_dakika = EXCLUDED.sure_dakika
            """, (test_adi, sure))

            eklenen = 0
            for i in range(1, soru_sayisi + 1):
                metin = request.form.get(f"soru_metni_{i}", "").strip()
                a = request.form.get(f"secenek_a_{i}", "").strip()
                b = request.form.get(f"secenek_b_{i}", "").strip()
                c = request.form.get(f"secenek_c_{i}", "").strip()
                d = request.form.get(f"secenek_d_{i}", "").strip()
                dogru = request.form.get(f"dogru_cevap_{i}", "A").strip().upper()

                if metin:
                    cursor.execute("""
                        INSERT INTO sorular (test_adi, soru_metni, secenek_a, secenek_b, secenek_c, secenek_d, dogru_cevap) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (test_adi, metin, a, b, c, d, dogru))
                    eklenen += 1

            conn.commit()
            cursor.close()
            conn.close()
            flash(f"'{test_adi}' testine {eklenen} soru başarıyla eklendi!", "success")
        except Exception as e:
            flash(f"Hata: {e}", "error")

    return redirect(url_for("admin_panel"))

@app.route("/admin/test-yayinla/<test_adi>")
def test_yayinla(test_adi):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("SELECT yayinlandi FROM test_ayarlari WHERE test_adi = %s", (test_adi,))
        res = cursor.fetchone()
        if res:
            yeni = not res["yayinlandi"]
            cursor.execute("UPDATE test_ayarlari SET yayinlandi = %s WHERE test_adi = %s", (yeni, test_adi))
            conn.commit()
        cursor.close()
        conn.close()
    except:
        pass
    return redirect(url_for("admin_panel"))

@app.route("/admin/soru-sil/<int:soru_id>")
def soru_sil(soru_id):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sorular WHERE id = %s", (soru_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Soru silindi.", "info")
    except:
        pass
    return redirect(url_for("admin_panel"))

@app.route("/admin/ogrenci-ara/<ogrenci_no>")
def ogrenci_ara(ogrenci_no):
    if not session.get("admin_logged_in"): return jsonify({"bulundu": False})
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("SELECT ad FROM ogrenciler WHERE ogrenci_no = %s", (str(ogrenci_no).strip(),))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row: return jsonify({"bulundu": True, "ad": row["ad"]})
    except:
        pass
    return jsonify({"bulundu": False})

@app.route("/admin/kaydet", methods=["POST"])
def ogrenci_kaydet():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    no, ad, sinav, derece = request.form.get("ogrenci_no", "").strip(), request.form.get("ad", "").strip(), request.form.get("sinav", "Genel").strip(), request.form.get("derece", "").strip()
    try:
        dogru, yanlis, bos, puan = int(request.form.get("dogru", 0)), int(request.form.get("yanlis", 0)), int(request.form.get("bos", 0)), int(request.form.get("puan", 0))
    except:
        dogru, yanlis, bos, puan = 0, 0, 0, 0

    if no and ad:
        try:
            conn = db_baglantisi()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO ogrenciler (ogrenci_no, ad) VALUES (%s, %s) ON CONFLICT (ogrenci_no) DO UPDATE SET ad = EXCLUDED.ad", (no, ad))
            cursor.execute("""
                INSERT INTO sinavlar (ogrenci_no, sinav, dogru, yanlis, bos, puan, derece)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ogrenci_no, sinav) DO UPDATE SET dogru = EXCLUDED.dogru, yanlis = EXCLUDED.yanlis, bos = EXCLUDED.bos, puan = EXCLUDED.puan, derece = EXCLUDED.derece
            """, (no, sinav, dogru, yanlis, bos, puan, derece))
            conn.commit()
            cursor.close()
            conn.close()
            flash("Kayıt güncellendi.", "success")
        except Exception as e:
            flash(f"Hata: {e}", "error")
    return redirect(url_for("admin_panel"))

@app.route("/admin/ogrenci-sil/<ogrenci_no>")
def ogrenci_sil(ogrenci_no):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sinavlar WHERE ogrenci_no = %s", (str(ogrenci_no),))
        cursor.execute("DELETE FROM ogrenciler WHERE ogrenci_no = %s", (str(ogrenci_no),))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Öğrenci silindi.", "info")
    except:
        pass
    return redirect(url_for("admin_panel"))

@app.route("/admin/excel-yukle", methods=["POST"])
def excel_yukle():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    dosya = request.files.get("excel_dosya")
    if dosya:
        try:
            df = pd.read_excel(dosya)
            df.columns = [str(col).strip().lower() for col in df.columns]
            conn = db_baglantisi()
            cursor = conn.cursor()
            for _, row in df.iterrows():
                no = str(row.get("ogrenci_no", row.get("no", row.get("okul_no", "0")))).strip()
                ad = str(row.get("ad", row.get("ad_soyad", "İsimsiz"))).strip()
                sinav_adi = str(row.get("sinav", row.get("sinav_adi", "Genel"))).strip()
                try:
                    dogru = int(row.get("dogru", 0))
                    yanlis = int(row.get("yanlis", 0))
                    bos = int(row.get("bos", 0))
                    puan = int(row.get("puan", 0))
                    derece = str(row.get("derece", "")).strip()
                    if derece == "nan": derece = ""
                except:
                    dogru, yanlis, bos, puan, derece = 0, 0, 0, 0, ""
                if no and no != "nan":
                    cursor.execute("INSERT INTO ogrenciler (ogrenci_no, ad) VALUES (%s, %s) ON CONFLICT (ogrenci_no) DO UPDATE SET ad = EXCLUDED.ad", (no, ad))
                    cursor.execute("""
                        INSERT INTO sinavlar (ogrenci_no, sinav, dogru, yanlis, bos, puan, derece)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ogrenci_no, sinav) DO UPDATE SET dogru = EXCLUDED.dogru, yanlis = EXCLUDED.yanlis, bos = EXCLUDED.bos, puan = EXCLUDED.puan, derece = EXCLUDED.derece
                    """, (no, sinav_adi, dogru, yanlis, bos, puan, derece))
            conn.commit()
            cursor.close()
            conn.close()
            flash("Excel aktarıldı!", "success")
        except Exception as e:
            flash(f"Excel hatası: {e}", "error")
    return redirect(url_for("admin_panel"))

@app.route("/admin/excel-indir")
def excel_indir():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    try:
        veriler = sinav_verilerini_getir()
        satirlar = []
        for no, bilgi in veriler.items():
            for s in bilgi["sinavlar"]:
                satirlar.append({"ogrenci_no": no, "ad": bilgi["ad"], "sinav": s["sinav"], "dogru": s["dogru"], "yanlis": s["yanlis"], "bos": s["bos"], "puan": s["puan"], "derece": s.get("derece", "")})
        df = pd.DataFrame(satirlar)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="Ogretmen_Sinav_Sonuclari.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except:
        return redirect(url_for("admin_panel"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
