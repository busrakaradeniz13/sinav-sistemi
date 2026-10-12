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
app.secret_key = "ogretmen_gizli_anahtari_123"  # Oturum yönetimi için güvenlik anahtarı

# ÖĞRETMEN GİRİŞ ŞİFRESİ
ADMIN_PASSWORD = "1234"  # Burayı dilediğiniz şifreyle değiştirebilirsiniz

# Veri depolama (Uygulama açık olduğu sürece bellekte tutulur)
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


# --- VELİ SORGULAMA SAYFASI ---
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
      hata = (
          "Bu numaraya ait sınav sonucu bulunamadı. Lütfen numarayı kontrol"
          " ediniz."
      )

  return render_template("sorgula.html", sonuc=sonuc, hata=hata)


# --- ÖĞRETMEN GİRİŞ SAYFASI ---
@app.route("/login", methods=["GET", "POST"])
def login():
  if request.method == "POST":
    sifre = request.form.get("sifre")
    if sifre == ADMIN_PASSWORD:
      session["admin_logged_in"] = True
      return redirect(url_for("admin_panel"))
    else:
      flash("Hatalı şifre! Lütfen tekrar deneyin.", "error")

  return render_template("login.html")


# --- ÖĞRETMEN ÇIKIŞ ---
@app.route("/logout")
def logout():
  session.pop("admin_logged_in", None)
  return redirect(url_for("login"))


# --- ÖĞRETMEN YÖNETİM PANELİ ---
@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
  if not session.get("admin_logged_in"):
    return redirect(url_for("login"))

  return render_template("admin.html", veriler=sinav_verileri)


# --- ÖĞRENCİ EKLE / GÜNCELLE ---
@app.route("/admin/kaydet", methods=["POST"])
def ogrenci_kaydet():
  if not session.get("admin_logged_in"):
    return redirect(url_for("login"))

  ogrenci_no = request.form.get("ogrenci_no", "").strip()
  ad = request.form.get("ad", "").strip()
  sinav = request.form.get("sinav", "").strip()
  dogru = int(request.form.get("dogru", 0))
  yanlis = int(request.form.get("yanlis", 0))
  bos = int(request.form.get("bos", 0))
  puan = int(request.form.get("puan", 0))

  if ogrenci_no and ad:
    sinav_verileri[ogrenci_no] = {
        "ad": ad,
        "sinav": sinav,
        "dogru": dogru,
        "yanlis": yanlis,
        "bos": bos,
        "puan": puan,
    }
    flash("Öğrenci notu başarıyla kaydedildi!", "success")

  return redirect(url_for("admin_panel"))


# --- ÖĞRENCİ SİL ---
@app.route("/admin/sil/<ogrenci_no>")
def ogrenci_sil(ogrenci_no):
  if not session.get("admin_logged_in"):
    return redirect(url_for("login"))

  if ogrenci_no in sinav_verileri:
    del sinav_verileri[ogrenci_no]
    flash("Öğrenci kaydı silindi.", "info")

  return redirect(url_for("admin_panel"))


# --- EXCEL İLE TOPLU NOT YÜKLEME ---
@app.route("/admin/excel-yukle", methods=["POST"])
def excel_yukle():
  if not session.get("admin_logged_in"):
    return redirect(url_for("login"))

  dosya = request.files.get("excel_dosya")
  if dosya and (
      dosya.filename.endswith(".xlsx") or dosya.filename.endswith(".csv")
  ):
    try:
      if dosya.filename.endswith(".csv"):
        df = pd.read_csv(dosya)
      else:
        df = pd.read_excel(dosya)

      # Excel sütun isimleri: ogrenci_no, ad, sinav, dogru, yanlis, bos, puan
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
  else:
    flash("Lütfen geçerli bir .xlsx veya .csv dosyası yükleyin.", "error")

  return redirect(url_for("admin_panel"))


if __name__ == "__main__":
  app.run(debug=True, port=5000)