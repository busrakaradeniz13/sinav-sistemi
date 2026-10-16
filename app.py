import io
import os
import re
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
import pypdf
import docx

app = Flask(__name__)
app.secret_key = "uzman_ogretmen_guvenli_sistem_key_2026_v11"

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
        try:
            cursor.execute("SELECT * FROM ogrenciler ORDER BY CAST(ogrenci_no AS INTEGER) ASC")
        except:
            cursor.execute("SELECT * FROM ogrenciler ORDER BY ogrenci_no ASC")
            
        ogrenci_satirlari = cursor.fetchall()
        veriler = {}
        for ogrenci in ogrenci_satirlari:
            no = ogrenci["ogrenci_no"]
            ad = ogrenci["ad"]
            
            cursor.execute("SELECT * FROM sinavlar WHERE ogrenci_no = %s ORDER BY id DESC", (no,))
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

def tum_sinav_adlarini_getir():
    adlar = []
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT sinav FROM sinavlar UNION SELECT test_adi FROM test_ayarlari")
        rows = cursor.fetchall()
        for r in rows:
            val = r.get("sinav") or r.get("test_adi")
            if val and val not in adlar:
                adlar.append(val)
        cursor.close()
        conn.close()
    except:
        pass
    return adlar

@app.route("/", methods=["GET", "POST"])
def veli_sorgula():
    sonuc, hata = None, None
    en_son_derece = None
    
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
            try:
                su_an_tsi = datetime.now(TURKEY_TZ).strftime("%d.%m.%Y %H:%M")
                conn = db_baglantisi()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ogrenciler 
                    SET sorgu_sayisi = sorgu_sayisi + 1, son_sorgu_tarihi = %s 
                    WHERE ogrenci_no = %s
                """, (su_an_tsi, ogrenci_no))
                cursor.execute("UPDATE istatistikler SET toplam_sorgu = toplam_sorgu + 1 WHERE id = 1")
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"Sorgu sayaç güncelleme hatası: {e}")

            ham = sinav_verileri[ogrenci_no]
            sonuc = {"ogrenci_no": ogrenci_no, "ad": ham["ad"], "sinavlar": ham["sinavlar"]}
            
            if ham["sinavlar"]:
                son_sinav = ham["sinavlar"][0]
                d = str(son_sinav.get("derece", "")).replace(".", "").strip().lower()
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
    aktif_tab = request.args.get("tab", "tab-ogrenciler")
    kayitli_dersler = tum_sinav_adlarini_getir()

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
        toplam_sorgu=toplam_sorgu,
        aktif_tab=aktif_tab,
        kayitli_dersler=kayitli_dersler
    )

@app.route("/admin/cikis")
def admin_cikis():
    session.clear()
    return redirect(url_for("admin_panel"))

@app.route("/admin/sayaclari-sifirla")
def sayaclari_sifirla():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("UPDATE istatistikler SET toplam_ziyaret = 0, toplam_sorgu = 0 WHERE id = 1")
        cursor.execute("UPDATE ogrenciler SET sorgu_sayisi = 0")
        conn.commit()
        cursor.close()
        conn.close()
        flash("Tüm sayaçlar ve öğrenci sorgu sayıları başarıyla sıfırlandı!", "success")
    except Exception as e:
        flash(f"Sıfırlama hatası: {e}", "error")
    return redirect(url_for("admin_panel", tab="tab-ogrenciler"))

@app.route("/admin/coklu-soru-ekle", methods=["POST"])
def coklu_soru_ekle():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    
    test_adi = request.form.get("test_adi", "").strip()
    sure = int(request.form.get("sure", 30))
    soru_dosyasi = request.files.get("soru_dosyasi")

    if not test_adi:
        flash("Lütfen test adı giriniz.", "error")
        return redirect(url_for("admin_panel", tab="tab-sinavlar"))

    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO test_ayarlari (test_adi, sure_dakika, yayinlandi) 
            VALUES (%s, %s, FALSE) 
            ON CONFLICT (test_adi) DO UPDATE SET sure_dakika = EXCLUDED.sure_dakika
        """, (test_adi, sure))

        eklenen = 0

        if soru_dosyasi and soru_dosyasi.filename:
            dosya_adi = soru_dosyasi.filename.lower()
            tam_metin = ""
            
            if dosya_adi.endswith(".pdf"):
                reader = pypdf.PdfReader(soru_dosyasi)
                for sayfa in reader.pages:
                    t = sayfa.extract_text()
                    if t: tam_metin += t + "\n"
            elif dosya_adi.endswith(".docx"):
                doc = docx.Document(soru_dosyasi)
                for p in doc.paragraphs:
                    if p.text: tam_metin += p.text + "\n"

            soru_bloklari = re.split(r'(?i)(?:soru\s*\d+[\.\)]?|\d+[\.\)]\s+)', tam_metin)
            for blok in soru_bloklari:
                blok = blok.strip()
                if len(blok) > 10:
                    satirlar = [s.strip() for s in blok.split('\n') if s.strip()]
                    if len(satirlar) >= 5:
                        s_metni = satirlar[0]
                        sec_a = satirlar[1].lstrip('A-a.) ]')
                        sec_b = satirlar[2].lstrip('B-b.) ]')
                        sec_c = satirlar[3].lstrip('C-c.) ]')
                        sec_d = satirlar[4].lstrip('D-d.) ]')
                        dogru = "A"
                        
                        cursor.execute("""
                            INSERT INTO sorular (test_adi, soru_metni, secenek_a, secenek_b, secenek_c, secenek_d, dogru_cevap) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (test_adi, s_metni, sec_a, sec_b, sec_c, sec_d, dogru))
                        eklenen += 1
        else:
            soru_sayisi = int(request.form.get("soru_sayisi", 1))
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
        flash(f"'{test_adi}' testine toplam {eklenen} soru başarıyla eklendi!", "success")
    except Exception as e:
        flash(f"Soru ekleme hatası: {e}", "error")

    return redirect(url_for("admin_panel", tab="tab-sinavlar"))

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
    return redirect(url_for("admin_panel", tab="tab-sinavlar"))

@app.route("/admin/test-sil/<test_adi>")
def test_sil(test_adi):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    try:
        conn = db_baglantisi()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sorular WHERE test_adi = %s", (test_adi,))
        cursor.execute("DELETE FROM ogrenci_online_sonuclar WHERE test_adi = %s", (test_adi,))
        cursor.execute("DELETE FROM test_ayarlari WHERE test_adi = %s", (test_adi,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"'{test_adi}' sınavı ve ilgili tüm sorular/sonuçlar silindi.", "info")
    except Exception as e:
        flash(f"Sınav silme hatası: {e}", "error")
    return redirect(url_for("admin_panel", tab="tab-sinavlar"))

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
    return redirect(url_for("admin_panel", tab="tab-sinavlar"))

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
            flash("Kayıt eklendi/güncellendi.", "success")
        except Exception as e:
            flash(f"Hata: {e}", "error")
    return redirect(url_for("admin_panel", tab="tab-ekle"))

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
    return redirect(url_for("admin_panel", tab="tab-ogrenciler"))

@app.route("/admin/excel-yukle", methods=["POST"])
def excel_yukle():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    dosya = request.files.get("excel_dosya")
    if dosya and dosya.filename:
        try:
            df = pd.read_excel(dosya)
            col_map = {}
            for col in df.columns:
                c_str = str(col).strip().lower()
                if "no" in c_str: col_map["ogrenci_no"] = col
                elif "ad" in c_str or "isim" in c_str: col_map["ad"] = col
                elif "sinav" in c_str or "ders" in c_str: col_map["sinav"] = col
                elif "dogru" in c_str or "doğru" in c_str: col_map["dogru"] = col
                elif "yanlis" in c_str or "yanlış" in c_str: col_map["yanlis"] = col
                elif "bos" in c_str or "boş" in c_str: col_map["bos"] = col
                elif "puan" in c_str or "not" in c_str: col_map["puan"] = col
                elif "derece" in c_str or "sira" in c_str or "sıra" in c_str: col_map["derece"] = col

            conn = db_baglantisi()
            cursor = conn.cursor()
            eklenen = 0

            for _, row in df.iterrows():
                no_col = col_map.get("ogrenci_no")
                ad_col = col_map.get("ad")
                sinav_col = col_map.get("sinav")

                no = str(row[no_col]).strip() if no_col and pd.notna(row[no_col]) else ""
                ad = str(row[ad_col]).strip() if ad_col and pd.notna(row[ad_col]) else "İsimsiz"
                sinav_adi = str(row[sinav_col]).strip() if sinav_col and pd.notna(row[sinav_col]) else "Genel"

                if not no or no.lower() in ["nan", "none", "0", ""]:
                    continue

                try:
                    dogru = int(row[col_map["dogru"]]) if "dogru" in col_map and pd.notna(row[col_map["dogru"]]) else 0
                    yanlis = int(row[col_map["yanlis"]]) if "yanlis" in col_map and pd.notna(row[col_map["yanlis"]]) else 0
                    bos = int(row[col_map["bos"]]) if "bos" in col_map and pd.notna(row[col_map["bos"]]) else 0
                    puan = int(row[col_map["puan"]]) if "puan" in col_map and pd.notna(row[col_map["puan"]]) else 0
                    derece = str(row[col_map["derece"]]).strip() if "derece" in col_map and pd.notna(row[col_map["derece"]]) else ""
                    if derece.lower() == "nan": derece = ""
                except:
                    dogru, yanlis, bos, puan, derece = 0, 0, 0, 0, ""

                cursor.execute("INSERT INTO ogrenciler (ogrenci_no, ad) VALUES (%s, %s) ON CONFLICT (ogrenci_no) DO UPDATE SET ad = EXCLUDED.ad", (no, ad))
                cursor.execute("""
                    INSERT INTO sinavlar (ogrenci_no, sinav, dogru, yanlis, bos, puan, derece)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ogrenci_no, sinav) DO UPDATE SET dogru = EXCLUDED.dogru, yanlis = EXCLUDED.yanlis, bos = EXCLUDED.bos, puan = EXCLUDED.puan, derece = EXCLUDED.derece
                """, (no, sinav_adi, dogru, yanlis, bos, puan, derece))
                eklenen += 1

            conn.commit()
            cursor.close()
            conn.close()
            flash(f"Excel başarıyla işlendi! {eklenen} kayıt eklendi/güncellendi.", "success")
        except Exception as e:
            flash(f"Excel yükleme hatası: {e}", "error")
    return redirect(url_for("admin_panel", tab="tab-excel"))

@app.route("/admin/excel-indir")
def excel_indir():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_panel"))
    try:
        veriler = sinav_verilerini_getir()
        satirlar = []
        for no, bilgi in veriler.items():
            if bilgi["sinavlar"]:
                for s in bilgi["sinavlar"]:
                    satirlar.append({
                        "Öğrenci No": no,
                        "Ad Soyad": bilgi["ad"],
                        "Sınav / Ders": s["sinav"],
                        "Doğru": s["dogru"],
                        "Yanlış": s["yanlis"],
                        "Boş": s["bos"],
                        "Puan": s["puan"],
                        "Derece": s.get("derece", "")
                    })
            else:
                satirlar.append({
                    "Öğrenci No": no,
                    "Ad Soyad": bilgi["ad"],
                    "Sınav / Ders": "-",
                    "Doğru": 0, "Yanlış": 0, "Boş": 0, "Puan": 0, "Derece": ""
                })

        df = pd.DataFrame(satirlar)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sinav_Sonuclari")
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name="Ogretmen_Sinav_Sonuclari.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        flash(f"Excel indirme hatası: {e}", "error")
        return redirect(url_for("admin_panel", tab="tab-excel"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
