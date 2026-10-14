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
      hata = "Bu numaraya ait öğrenci veya sınav sonucu bulunamadı."
  return render_template("sorgula.html", sonuc=sonuc, hata=hata)


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


@app.route("/admin/kaydet", methods=["POST"])
def ogrenci_kaydet():
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))
  ogrenci_no = request.form.get("ogrenci_no", "").strip()
  ad = request.form.get("ad", "").strip()
  sinav_adi = request.form.get("sinav", "Genel Sınav").strip()
  try:
    dogru = int(request.form.get("dogru", 0))
    yanlis = int(request.form.get("yanlis", 0))
    bos = int(request.form.get("bos", 0))
    puan = int(request.form.get("puan", 0))
  except ValueError:
    dogru, yanlis, bos, puan = 0, 0, 0, 0

  yeni_sinav = {
      "sinav": sinav_adi,
      "dogru": dogru,
      "yanlis": yanlis,
      "bos": bos,
      "puan": puan,
  }
  if ogrenci_no and ad:
    if ogrenci_no not in sinav_verileri:
      sinav_verileri[ogrenci_no] = {"ad": ad, "sinavlar": []}
    sinav_verileri[ogrenci_no]["ad"] = ad
    mevcut = sinav_verileri[ogrenci_no]["sinavlar"]
    guncellendi = False
    for s in mevcut:
      if s["sinav"].lower() == sinav_adi.lower():
        s.update(yeni_sinav)
        guncellendi = True
        break
    if not guncellendi:
      mevcut.append(yeni_sinav)
    flash(f"Başarılı: {ad} - {sinav_adi} kaydedildi.", "success")
  return redirect(url_for("admin_panel"))


@app.route("/admin/ogrenci-sil/<ogrenci_no>")
def ogrenci_sil(ogrenci_no):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))
  if ogrenci_no in sinav_verileri:
    del sinav_verileri[ogrenci_no]
    flash("Öğrenci silindi.", "info")
  return redirect(url_for("admin_panel"))


@app.route("/admin/sinav-sil/<ogrenci_no>/<path:sinav_adi>")
def sinav_sil(ogrenci_no, sinav_adi):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))
  if ogrenci_no in sinav_verileri:
    sinavlar = sinav_verileri[ogrenci_no]["sinavlar"]
    sinav_verileri[ogrenci_no]["sinavlar"] = [
        s for s in sinavlar if s["sinav"] != sinav_adi
    ]
    flash("Sınav sonucu silindi.", "info")
  return redirect(url_for("admin_panel"))


# --- HATA KORUMALI AKILLI EXCEL YÜKLEME FONKSİYONU ---
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

      # Sütun isimlerini küçük harfe çevirip boşlukları temizleyelim (Hata riskini sıfırlar)
      df.columns = [str(col).strip().lower() for col in df.columns]

      for _, row in df.iterrows():
        # Alternatif sütun adlarını da destekler (ogrenci_no, no, okul_no vb.)
        no = str(
            row.get("ogrenci_no", row.get("no", row.get("okul_no", "0")))
        ).strip()
        ad = str(row.get("ad", row.get("ad_soyad", "İsimsiz"))).strip()
        sinav_adi = str(
            row.get("sinav", row.get("sinav_adi", "Genel Sınav"))
        ).strip()

        try:
          dogru = int(
              row.get("dogru", row.get("d", 0))
              if pd.notna(row.get("dogru", row.get("d", 0)))
              else 0
          )
          yanlis = int(
              row.get("yanlis", row.get("y", 0))
              if pd.notna(row.get("yanlis", row.get("y", 0)))
              else 0
          )
          bos = int(
              row.get("bos", row.get("b", 0))
              if pd.notna(row.get("bos", row.get("b", 0)))
              else 0
          )
          puan = int(
              row.get("puan", row.get("not", 0))
              if pd.notna(row.get("puan", row.get("not", 0)))
              else 0
          )
        except:
          dogru, yanlis, bos, puan = 0, 0, 0, 0

        yeni_sinav = {
            "sinav": sinav_adi,
            "dogru": dogru,
            "yanlis": yanlis,
            "bos": bos,
            "puan": puan,
        }

        if no and no != "nan":
          if no not in sinav_verileri:
            sinav_verileri[no] = {"ad": ad, "sinavlar": []}
          sinav_verileri[no]["ad"] = ad
          mevcut = sinav_verileri[no]["sinavlar"]

          eklendi = False
          for s in mevcut:
            if s["sinav"].lower() == sinav_adi.lower():
              s.update(yeni_sinav)
              eklendi = True
              break
          if not eklendi:
            mevcut.append(yeni_sinav)

      flash(
          "Excel dosyasındaki tüm veriler başarıyla ve hatasız yüklendi!",
          "success",
      )
    except Exception as e:
      flash(
          f"Excel okunurken bir hata oluştu. Lütfen dosya formatını"
          f" kontrol edin. Detay: {str(e)}",
          "error",
      )

  return redirect(url_for("admin_panel"))


if __name__ == "__main__":
  app.run(debug=False, port=5000)
