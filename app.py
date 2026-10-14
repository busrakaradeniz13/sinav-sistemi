import os
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import pandas as pd

app = Flask(__name__)
app.secret_key = "ogretmen_cok_gizli_guvenlik_anahtari_98765"

# ÖĞRETMEN GİRİŞ ŞİFRESİ
ADMIN_PASSWORD = "1234"

# Örnek başlangıç verileri (Bellek üstünde tutulan veri tabanı)
sinav_verileri = {
    "101": {
        "ad": "Ahmet Yılmaz",
        "sinav": "Matematik 1. Yazılı",
        "dogru": 18,
        "yanlis": 2,
        "bos": 0,
        "puan": 90,
    },
    "102": {
        "ad": "Ayşe Demir",
        "sinav": "Matematik 1. Yazılı",
        "dogru": 20,
        "yanlis": 0,
        "bos": 0,
        "puan": 100,
    },
}


# ==========================================
# 1. VELİ SORGULAMA BÖLÜMÜ (Sadece Ana Sayfa)
# ==========================================
@app.route("/", methods=["GET", "POST"])
def veli_sorgula():
  sonuc = None
  hata = None

  if request.method == "POST":
    ogrenci_no = request.form.get("ogrenci_no", "").strip()

    if not ogrenci_no:
      hata = "Lütfen geçerli bir öğrenci numarası giriniz."
    elif ogrenci_no in sinav_verileri:
      sonuc = sinav_verileri[ogrenci_no]
    else:
      hata = (
          "Bu numaraya ait sınav sonucu bulunamadı. Lütfen numarayı kontrol"
          " ediniz."
      )

  return render_template("sorgula.html", sonuc=sonuc, hata=hata)


# ==========================================
# 2. ÖĞRETMEN GİRİŞ VE YÖNETİM BÖLÜMÜ
# ==========================================
@app.route("/ogretmen-giris", methods=["GET", "POST"])
def ogretmen_giris():
  # Zaten giriş yapmışsa doğrudan panele yolla
  if session.get("admin_logged_in"):
    return redirect(url_for("ogretmen_panel"))

  if request.method == "POST":
    sifre = request.form.get("sifre", "").strip()
    if sifre == ADMIN_PASSWORD:
      session["admin_logged_in"] = True
      return redirect(url_for("ogretmen_panel"))
    else:
      flash("Hatalı şifre! Lütfen tekrar deneyin.", "error")

  return render_template("login.html")


@app.route("/ogretmen-cikis")
def ogretmen_cikis():
  session.clear()
  return redirect(url_for("ogretmen_giris"))


@app.route("/yonetim-paneli", methods=["GET"])
def ogretmen_panel():
  # Güvenlik kontrolü: Giriş yapmamışsa login sayfasına at
  if not session.get("admin_logged_in"):
    return redirect(url_for("ogretmen_giris"))

  return render_template("admin.html", veriler=sinav_verileri)


@app.route("/yonetim-paneli/kaydet", methods=["POST"])
def ogrenci_kaydet():
  if not session.get("admin_logged_in"):
    return redirect(url_for("ogretmen_giris"))

  ogrenci_no = request.form.get("ogrenci_no", "").strip()
  ad = request.form.get("ad", "").strip()

  if ogrenci_no and ad:
    sinav_verileri[ogrenci_no] = {
        "ad": ad,
        "sinav": request.form.get("sinav", "Genel Sınav"),
        "dogru": int(request.form.get("dogru", 0)),
        "yanlis": int(request.form.get("yanlis", 0)),
        "bos": int(request.form.get("bos", 0)),
        "puan": int(request.form.get("puan", 0)),
    }
    flash("Öğrenci notu başarıyla kaydedildi!", "success")

  return redirect(url_for("ogretmen_panel"))


@app.route("/yonetim-paneli/sil/<ogrenci_no>")
def ogrenci_sil(ogrenci_no):
  if not session.get("admin_logged_in"):
    return redirect(url_for("ogretmen_giris"))

  if ogrenci_no in sinav_verileri:
    del sinav_verileri[ogrenci_no]
    flash("Öğrenci kaydı silindi.", "info")

  return redirect(url_for("ogretmen_panel"))


@app.route("/yonetim-paneli/excel-yukle", methods=["POST"])
def excel_yukle():
  if not session.get("admin_logged_in"):
    return redirect(url_for("ogretmen_giris"))

  dosya = request.files.get("excel_dosya")
  if dosya:
    try:
      if dosya.filename.endswith(".csv"):
        df = pd.read_csv(dosya)
      else:
        df = pd.read_excel(dosya)

      for _, row in df.iterrows():
        no = str(row["ogrenci_no"]).strip()
        sinav_verileri[no] = {
            "ad": str(row["ad"]),
            "sinav": str(row.get("sinav", "Genel Sınav")),
            "dogru": int(row.get("dogru", 0)),
            "yanlis": int(row.get("yanlis", 0)),
            "bos": int(row.get("bos", 0)),
            "puan": int(row.get("puan", 0)),
        }
      flash("Excel başarıyla yüklendi ve notlar güncellendi!", "success")
    except Exception as e:
      flash(f"Excel okunurken hata oluştu: {str(e)}", "error")

  return redirect(url_for("ogretmen_panel"))


if __name__ == "__main__":
  app.run(debug=False, port=5000)
