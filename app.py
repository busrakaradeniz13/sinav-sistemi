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

ADMIN_PASSWORD = "1234"

# ÖRNEK VERİ YAPISI: Her öğrenci numarasının altında bir "liste" bulunur.
# Böylece aynı öğrencinin birden fazla sınav sonucu saklanabilir.
sinav_verileri = {
    "101": {
        "ad": "Ahmet Yılmaz",
        "sinavlar": [
            {
                "sinav": "Matematik 1. Yazılı",
                "dogru": 18,
                "yanlis": 2,
                "bos": 0,
                "puan": 90,
            },
            {
                "sinav": "Türkçe 1. Yazılı",
                "dogru": 15,
                "yanlis": 5,
                "bos": 0,
                "puan": 75,
            },
        ],
    },
    "102": {
        "ad": "Ayşe Demir",
        "sinavlar": [{
            "sinav": "Matematik 1. Yazılı",
            "dogru": 20,
            "yanlis": 0,
            "bos": 0,
            "puan": 100,
        }],
    },
}


# ==========================================
# 1. VELİ SORGULAMA SAYfASI (Tüm Sınavları Listeleme)
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
      sonuc = sinav_verileri[ogrenci_no]  # Öğrencinin adı ve tüm sınav listesi
    else:
      hata = (
          "Bu numaraya ait sınav sonucu bulunamadı. Lütfen numarayı kontrol"
          " ediniz."
      )

  return render_template("sorgula.html", sonuc=sonuc, hata=hata)


# ==========================================
# 2. ÖĞRETMEN YÖNETİM PANELİ
# ==========================================
@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
  if request.method == "POST":
    sifre = request.form.get("sifre", "").strip()
    if sifre == ADMIN_PASSWORD:
      session["admin_logged_in"] = True
    else:
      flash("Hatalı şifre!", "error")
      return render_template(
          "admin.html", veriler=sinav_verileri, giris_yapildi=False
      )

  if not session.get("admin_logged_in"):
    return render_template(
        "admin.html", veriler=sinav_verileri, giris_yapildi=False
    )

  return render_template(
      "admin.html", veriler=sinav_verileri, giris_yapildi=True
  )


@app.route("/admin/cikis")
def admin_cikis():
  session.clear()
  return redirect(url_for("admin_panel"))


# --- YENİ SINAV SONUCU EKLEME ---
@app.route("/admin/kaydet", methods=["POST"])
def ogrenci_kaydet():
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))

  ogrenci_no = request.form.get("ogrenci_no", "").strip()
  ad = request.form.get("ad", "").strip()
  sinav_adi = request.form.get("sinav", "Genel Sınav").strip()

  yeni_sinav = {
      "sinav": sinav_adi,
      "dogru": int(request.form.get("dogru", 0)),
      "yanlis": int(request.form.get("yanlis", 0)),
      "bos": int(request.form.get("bos", 0)),
      "puan": int(request.form.get("puan", 0)),
  }

  if ogrenci_no and ad:
    # Eğer bu numara daha önce kayıtlı değilse yeni öğrenci aç
    if ogrenci_no not in sinav_verileri:
      sinav_verileri[ogrenci_no] = {"ad": ad, "sinavlar": []}

    # Öğrencinin adını güncelle (belki değişmiştir)
    sinav_verileri[ogrenci_no]["ad"] = ad

    # Aynı sınav adına ait eski sonuç varsa güncelle, yoksa yeni ekle
    mevcut_sinavlar = sinav_verileri[ogrenci_no]["sinavlar"]
    bulundu = False
    for s in mevcut_sinavlar:
      if s["sinav"] == sinav_adi:
        s.update(yeni_sinav)
        bulundu = True
        break

    if not bulundu:
      mevcut_sinavlar.append(yeni_sinav)

    flash(
        f"{ad} için '{sinav_adi'}' sonucu başarıyla kaydedildi!", "success"
    )

  return redirect(url_for("admin_panel"))


# --- ÖĞRENCİNİN TÜM KAYITLARINI SİL ---
@app.route("/admin/sil/<ogrenci_no>")
def ogrenci_sil(ogrenci_no):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))

  if ogrenci_no in sinav_verileri:
    del sinav_verileri[ogrenci_no]
    flash("Öğrencinin tüm sınav kayıtları silindi.", "info")

  return redirect(url_for("admin_panel"))


# --- EXCEL İLE TOPLU YÜKLEME ---
@app.route("/admin/excel-yukle", methods=["POST"])
def excel_yukle():
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))

  dosya = request.files.get("excel_dosya")
  if dosya:
    try:
      if dosya.filename.endswith(".csv"):
        df = pd.read_csv(dosya)
      else:
        df = pd.read_excel(dosya)

      for _, row in df.iterrows():
        no = str(row["ogrenci_no"]).strip()
        ad = str(row["ad"]).strip()
        sinav_adi = str(row.get("sinav", "Genel Sınav")).strip()

        yeni_sinav = {
            "sinav": sinav_adi,
            "dogru": int(row.get("dogru", 0)),
            "yanlis": int(row.get("yanlis", 0)),
            "bos": int(row.get("bos", 0)),
            "puan": int(row.get("puan", 0)),
        }

        if no not in sinav_verileri:
          sinav_verileri[no] = {"ad": ad, "sinavlar": []}

        sinav_verileri[no]["ad"] = ad

        # Aynı sınav varsa güncelle, yoksa listeye ekle
        mevcut = sinav_verileri[no]["sinavlar"]
        eklendi = False
        for s in mevcut:
          if s["sinav"] == sinav_adi:
            s.update(yeni_sinav)
            eklendi = True
            break
        if not eklendi:
          mevcut.append(yeni_sinav)

      flash("Excel başarıyla toplu olarak yüklendi!", "success")
    except Exception as e:
      flash(f"Hata: {str(e)}", "error")

  return redirect(url_for("admin_panel"))


if __name__ == "__main__":
  app.run(debug=False, port=5000)
