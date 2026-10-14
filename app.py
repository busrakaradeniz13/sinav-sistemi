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
# Bulut sunucularda oturumun kopmaması için sabit ve güvenli bir gizli anahtar
app.secret_key = "ogretmen_cok_gizli_guvenlik_anahtari_98765"

# ÖĞRETMEN GİRİŞ ŞİFRESİ
ADMIN_PASSWORD = "1234"

# Örnek başlangıç verileri
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


@app.route("/", methods=["GET", "POST"])
def index():
  sonuc = None
  hata = None
  if request.method == "POST":
    ogrenci_no = request.form.get("ogrenci_no", "").strip()
    if not ogrenci_no:
      hata = "Lütfen geçerli bir öğrenci numarası giriniz."
    elif ogrenci_no in sinav_verileri:
      sonuc = sinav_verileri[ogrenci_no]
    else:
      hata = "Bu numaraya ait sınav sonucu bulunamadı."
  return render_template("sorgula.html", sonuc=sonuc, hata=hata)


@app.route("/login", methods=["GET", "POST"])
def login():
  if request.method == "POST":
    sifre = request.form.get("sifre", "").strip()
    if sifre == ADMIN_PASSWORD:
      session["admin_logged_in"] = True
      return redirect(url_for("admin_panel"))
    else:
      flash("Hatalı şifre!", "error")
  return render_template("login.html")


@app.route("/logout")
def logout():
  session.clear()
  return redirect(url_for("login"))


@app.route("/admin", methods=["GET"])
def admin_panel():
  if not session.get("admin_logged_in"):
    return redirect(url_for("login"))
  return render_template("admin.html", veriler=sinav_verileri)


@app.route("/admin/kaydet", methods=["POST"])
def ogrenci_kaydet():
  if not session.get("admin_logged_in"):
    return redirect(url_for("login"))

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
    flash("Başarıyla kaydedildi!", "success")
  return redirect(url_for("admin_panel"))


@app.route("/admin/sil/<ogrenci_no>")
def ogrenci_sil(ogrenci_no):
  if not session.get("admin_logged_in"):
    return redirect(url_for("login"))

  if ogrenci_no in sinav_verileri:
    del sinav_verileri[ogrenci_no]
    flash("Kayıt silindi.", "info")
  return redirect(url_for("admin_panel"))


@app.route("/admin/excel-yukle", methods=["POST"])
def excel_yukle():
  if not session.get("admin_logged_in"):
    return redirect(url_for("login"))

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
      flash("Excel başarıyla yüklendi!", "success")
    except Exception as e:
      flash(f"Hata: {str(e)}", "error")
  return redirect(url_for("admin_panel"))


if __name__ == "__main__":
  app.run(debug=False, port=5000)
