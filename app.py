import io
import os
from flask import (
    Flask,
    flash,
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

ADMIN_PASSWORD = "1234"
YEDEK_DOSYA_YOLU = "notlar_yedek.xlsx"

# Varsayılan başlangıç verileri (derece desteği eklendi)
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
                "derece": "1",
            },
            {
                "sinav": "Türkçe 1. Yazılı",
                "dogru": 15,
                "yanlis": 5,
                "bos": 0,
                "puan": 75,
                "derece": "",
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
            "derece": "2",
        }],
    },
}


# --- SİSTEM AÇILDIĞINDA ARŞİVDEKİ EXCELİ OKU ---
def yedekten_verileri_yukle():
  global sinav_verileri
  if os.path.exists(YEDEK_DOSYA_YOLU):
    try:
      df = pd.read_excel(YEDEK_DOSYA_YOLU)
      df.columns = [str(col).strip().lower() for col in df.columns]
      gecici_veri = {}

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
          derece = str(
              row.get("derece", row.get("siralama", ""))
              if pd.notna(row.get("derece", row.get("siralama", "")))
              else ""
          ).strip()
          if derece == "nan":
            derece = ""
        except:
          dogru, yanlis, bos, puan, derece = 0, 0, 0, 0, ""

        yeni_sinav = {
            "sinav": sinav_adi,
            "dogru": dogru,
            "yanlis": yanlis,
            "bos": bos,
            "puan": puan,
            "derece": derece,
        }

        if no and no != "nan":
          if no not in gecici_veri:
            gecici_veri[no] = {"ad": ad, "sinavlar": []}
          gecici_veri[no]["ad"] = ad
          mevcut = gecici_veri[no]["sinavlar"]

          eklendi = False
          for s in mevcut:
            if s["sinav"].lower() == sinav_adi.lower():
              s.update(yeni_sinav)
              eklendi = True
              break
          if not eklendi:
            mevcut.append(yeni_sinav)

      if gecici_veri:
        sinav_verileri = gecici_veri
    except Exception as e:
      print("Arşiv okunurken hata:", e)


yedekten_verileri_yukle()


# --- YAPILAN DEĞİŞİKLİKLERİ ARŞİVE KAYDET ---
def verileri_excele_yedekle():
  try:
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
    if satirlar:
      df = pd.DataFrame(satirlar)
      df.to_excel(YEDEK_DOSYA_YOLU, index=False)
  except Exception as e:
    print("Yedekleme hatası:", e)


@app.route("/", methods=["GET", "POST"])
def veli_sorgula():
  sonuc, hata = None, None
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
  derece = request.form.get("derece", "").strip()

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
      "derece": derece,
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

    verileri_excele_yedekle()
    flash(f"Başarılı: {ad} - {sinav_adi} kaydedildi.", "success")

  return redirect(url_for("admin_panel"))


@app.route("/admin/ogrenci-sil/<ogrenci_no>")
def ogrenci_sil(ogrenci_no):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))
  if ogrenci_no in sinav_verileri:
    del sinav_verileri[ogrenci_no]
    verileri_excele_yedekle()
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
    verileri_excele_yedekle()
    flash("Sınav sonucu silindi.", "info")
  return redirect(url_for("admin_panel"))


@app.route("/admin/excel-yukle", methods=["POST"])
def excel_yukle():
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))

  dosya = request.files.get("excel_dosya")
  if dosya:
    try:
      dosya.seek(0)
      dosya.save(YEDEK_DOSYA_YOLU)
      yedekten_verileri_yukle()
      flash("Excel başarıyla yüklendi ve arşivlendi!", "success")
    except Exception as e:
      flash(f"Excel yüklenirken hata: {str(e)}", "error")

  return redirect(url_for("admin_panel"))


# --- HAFIZADAN DOĞRUDAN ÖZEL İSİMLİ EXCEL OLUŞTURUP İNDİRME ---
@app.route("/admin/excel-indir")
def excel_indir():
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin_panel"))

  try:
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

    # Dosyayı sunucu diskine kaydetmek yerine RAM'de (bellekte) Excel baytlarına dönüştürüyoruz
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
  app.run(debug=False, port=5000)
