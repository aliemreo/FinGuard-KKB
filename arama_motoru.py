import psycopg2
import json
import argparse
import sys
from datetime import datetime

# ----------------------------------------------------------------
# AYARLAR
# ----------------------------------------------------------------
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "ihale_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "lolzedcr7")
}

def baglanti_kur():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"[ERROR] Bağlantı Hatası: {e}")
        return None

def detayli_yazdir(kayitlar, kolon_isimleri):
    if not kayitlar:
        print("\n[!] Belirtilen kriterlere uygun (aktif yasaklılığı çakışan) kayıt bulunamadı.")
        # Save empty result
        with open("ihale_results.json", "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return

    print(f"\n[OK] Toplam {len(kayitlar)} kayıt bulundu. Döküm Başlıyor...\n")
    
    # Prepare JSON output
    json_results = []
    
    for i, row in enumerate(kayitlar, 1):
        print(f"[SONUC #{i}] " + ("=" * 50))
        
        # Build dictionary for JSON
        row_dict = {}
        for col_name, value in zip(kolon_isimleri, row):
            
            # Hesaplanan geçici kolonları yazdırma
            if col_name in ['yasak_bitis_tarihi', 'yasak_suresi_interval']:
                continue

            print(f"  {col_name.upper()}: ", end="")
            
            if value is None:
                print("NULL")
                row_dict[col_name] = None
            elif isinstance(value, (dict, list)):
                print("\n" + json.dumps(value, ensure_ascii=False, indent=4))
                row_dict[col_name] = value
            elif isinstance(value, datetime):
                date_str = value.strftime('%Y-%m-%d')
                print(date_str)
                row_dict[col_name] = date_str
            else:
                print(value)
                row_dict[col_name] = value
        
        # Bitiş Tarihini Göster
        bitis_tarihi = row[-1] 
        if isinstance(bitis_tarihi, datetime):
            bitis_str = bitis_tarihi.strftime('%Y-%m-%d')
            print(f"[!] (HESAPLANAN) YASAK BİTİŞ TARİHİ: {bitis_str}")
            row_dict['yasak_bitis_tarihi'] = bitis_str

        print("\n" + ("=" * 65) + "\n")
        json_results.append(row_dict)
    
    # Save to JSON file
    output_file = "ihale_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] Sonuçlar '{output_file}' dosyasına kaydedildi.\n")

def main():
    parser = argparse.ArgumentParser(description="Aktif Yasaklılık Kontrolü")
    # Help kısmını güncelledim
    parser.add_argument("-i", "--isim", required=True, help="Aranacak Yasaklı Şirket/Şahıs İsmi")
    parser.add_argument("-b", "--baslangic", required=True, help="Sorgu Başlangıç Tarihi (YYYY.MM.DD)")
    parser.add_argument("-s", "--son", required=True, help="Sorgu Bitiş Tarihi (YYYY.MM.DD)")

    args = parser.parse_args()

    isim = args.isim
    
    # ----------------------------------------------------------------
    # 🛠️ TARİH FORMATI DÜZELTME (YYYY.MM.DD -> YYYY-MM-DD)
    # ----------------------------------------------------------------
    # Kullanıcı 2023.01.01 girerse, biz onu 2023-01-01 yaparız.
    user_baslangic = args.baslangic.replace('.', '-')
    user_bitis = args.son.replace('.', '-')

    print(f"\n[INFO] Sorgu Başlatılıyor...")
    print(f"[DATE] Senin Aralığın: {user_baslangic} -> {user_bitis}")
    print(f"[SEARCH] İsim          : {isim}")
    print(f"[!] Kural         : 2022-12-14 sonrası kayıtlar taranıyor.")

    conn = baglanti_kur()
    if not conn: return

    try:
        cur = conn.cursor()
        
        sql = """
            WITH hesaplanmis_veri AS (
                SELECT *,
                    CASE 
                        WHEN yasaklama_suresi ILIKE %s THEN 
                            (COALESCE(NULLIF(REGEXP_REPLACE(yasaklama_suresi, '[^0-9]', '', 'g'), ''), '0')::int * INTERVAL '1 year')
                        WHEN yasaklama_suresi ILIKE %s THEN 
                            (COALESCE(NULLIF(REGEXP_REPLACE(yasaklama_suresi, '[^0-9]', '', 'g'), ''), '0')::int * INTERVAL '1 month')
                        WHEN yasaklama_suresi ILIKE %s THEN 
                            (COALESCE(NULLIF(REGEXP_REPLACE(yasaklama_suresi, '[^0-9]', '', 'g'), ''), '0')::int * INTERVAL '1 day')
                        ELSE INTERVAL '0 day' 
                    END as yasak_suresi_interval
                FROM ihale_yasaklilari
            ),
            tarihli_veri AS (
                SELECT *,
                    (yasaklama_tarihi::date + yasak_suresi_interval) as yasak_bitis_tarihi
                FROM hesaplanmis_veri
            )
            SELECT * FROM tarihli_veri
            WHERE 
                yasaklama_tarihi::date >= '2022-12-14'
                
                AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements(yasakli) el
                    WHERE el->>'yasakli_adi_unvani' ILIKE %s
                )

                AND %s::date <= yasak_bitis_tarihi 
                AND %s::date >= yasaklama_tarihi::date
            
            ORDER BY yasaklama_tarihi DESC;
        """
        
        p_yil = '%yıl%'
        p_ay = '%ay%'
        p_gun = '%gün%'
        p_isim = f"%{isim}%"
        
        # Parametreleri gönder
        cur.execute(sql, (p_yil, p_ay, p_gun, p_isim, user_baslangic, user_bitis))
        
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        
        detayli_yazdir(rows, colnames)
        cur.close()

    except psycopg2.Error as e:
        print(f"[ERROR] Veritabanı Hatası: {e}")
    except ValueError:
        print("[ERROR] Tarih formatı hatalı! Lütfen YYYY.MM.DD formatında girin.")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    main()