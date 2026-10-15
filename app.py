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
    """Bulut veritabanında tabloları ve öğrenci bazlı sayaçları otomatik oluşturur."""
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

        # Genel Ziyaret ve Sorgulama Sayacı İçin Tablo
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

        conn.commit()
        cursor.close()
        conn.close()
        print("Bulut veritabanı ve öğrenci bazlı sayaç tabloları hazır.")
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

    if request.method == "GET":
        genel_istatistik_arttir("ziyaret")

    if request.method == "POST":
        genel_istatistik_arttir("sorgu")
        ogrenci_no = request.form.get("ogrenci_no", "").strip()

        if not ogrenci_no:
            hata = "Lütfen geçerli bir öğrenci numarası giriniz."
        elif ogrenci_no in sinav_verileri:
            # Türkiye saatine göre (UTC+3) anlık zamanı kaydet
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
                print(f"Öğrenci sayaç güncelleme hatası: {e}")

            sinav_verileri = sinav_verilerini_getir()
            ham_veri = sinav_verileri[ogrenci_no]
            ters_sinavlar = list(reversed(ham_veri.get("sinavlar", [])))
            sonuc = {"ad": ham_veri["ad"], "sinavlar": ters_sinavlar}

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
    )


@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    sinav_verileri = sinav_verilerini_getir()
    toplam_ziyaret, toplam_sorgu = genel_istatistikleri_oku()

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
            )

    if not session.get("admin_logged_in"):
        return render_template(
            "admin.html", veriler=sinav_verileri, giris_yapildi=False, son_sinav="",
            toplam_ziyaret=toplam_ziyaret, toplam_sorgu=toplam_sorgu
        )

    son_sinav = session.get("son_sinav_adi", "")
    return render_template(
        "admin.html",
        veriler=sinav_verileri,
        giris_yapildi=True,
        son_sinav=son_sinav,
        toplam_ziyaret=toplam_ziyaret,
        toplam_sorgu=toplam_sorgu,
    )


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


@app.route("/admin/cikis")
def admin_cikis():
    session.clear()
    return redirect(url_for("admin_panel"))


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
