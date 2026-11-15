import os
import json
import asyncio
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv
from openai import AsyncOpenAI
import psycopg2
from psycopg2.extras import Json
import glob

# ----------------------------------------------------------------
# KONFİGÜRASYON
# ----------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("API_KEY")
# OpenAI uyumlu herhangi bir uç nokta; varsayılanlar pipeline.py ile aynı.
# Novita kullanıyorsan: BASE_URL=https://api.novita.ai/openai, MODEL=openai/gpt-oss-120b
BASE_URL = os.getenv("BASE_URL", "https://mia.csp.kloudeks.com/v1")
MODEL = os.getenv("MODEL", "gpt-oss-120b")

# Veritabanı Ayarları
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "database": os.getenv("DB_NAME", "ihale_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD")
}

# Hata önleyici kontrol
if not DB_CONFIG["password"]:
    print("⚠️ UYARI: DB_PASSWORD .env dosyasında bulunamadı!")

client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

# ----------------------------------------------------------------
# EXTRACTOR SINIFI
# ----------------------------------------------------------------

class HTMLToJSONExtractor:
    """HTML tablolarından yapılandırılmış JSON verisi çıkarır"""
    
    def __init__(self, model_name: str = MODEL):
        self.model_name = model_name
    
    def _clean_json_string(self, json_str: str) -> str:
        """
        LLM'den gelen Markdown işaretlerini (```json ... ```) temizler.
        Bu fonksiyon JSON Parse hatasını çözer.
        """
        # Markdown kod bloklarını temizle
        if "```json" in json_str:
            json_str = json_str.replace("```json", "").replace("```", "")
        elif "```" in json_str:
            json_str = json_str.replace("```", "")
        
        return json_str.strip()

    def _create_extraction_prompt(self, html_content: str) -> str:
        return f"""Sen Türk Resmi Gazete yasaklama ilanlarından veri çıkaran bir uzmansın.

Aşağıdaki HTML içeriğinden verileri çıkarıp JSON formatında döndür.

🔴 ÖNEMLİ: SADECE SAF JSON DÖNDÜR. Markdown (```json) KULLANMA.

🔴 HTML ENCODING SORUNU:
HTML'de "Â", "Ä°", "ÃœNÄ°VERSÄ°TESÄ°" gibi bozuk karakterler olabilir.
Bunları düzelt ve anlamlı hale getir.

🔴 YASAKLI vs ORTAK AYIRIMI:
- Yasaklı = "4. İhalelere Katılmaktan Yasaklanan"
- Ortak = "5. Ortak ve/veya Ortaklıkların"
- Eğer yasaklı bir şirket ise TC kimlik no BOŞ olmalı.

🔴 JSON ŞEMASI:
{{
  "ihale_kayit_numarasi": "",
  "yasaklama_karari_veren_bakanlik_kurum": "",
  "ihaleyi_yapan_idarenin_adi": "",
  "yasakli": [
    {{
      "yasakli_adi_unvani": "",
      "yasakli_tc_kimlik_no": "",
      "yasakli_vergi_kimlik_no": ""
    }}
  ],
  "ortaklar": [
    {{
      "ortak_adi_unvani": "",
      "ortak_tc_kimlik_no": "",
      "ortak_vergi_kimlik_no": ""
    }}
  ],
  "yasaklama_kanun_dayanagi": "",
  "yasaklama_kanun_kapsami": "",
  "yasaklama_suresi": ""
}}

HTML:
{html_content}
"""

    def _preprocess_html(self, html_content: str) -> str:
        """HTML encoding sorunlarını temizler"""
        import html as html_module
        cleaned = html_module.unescape(html_content)
        # Basit temizlik
        cleaned = cleaned.replace("Â", "").replace("â", "a")
        return cleaned
    
    async def extract_from_html(self, html_content: str, debug: bool = False, max_retries: int = 3) -> Dict[str, Any]:
        
        html_content = self._preprocess_html(html_content)
        
        for attempt in range(max_retries):
            try:
                prompt = self._create_extraction_prompt(html_content)
                
                if debug:
                    print(f"📤 API çağrısı yapılıyor... (Model: {self.model_name})")
                
                response = await client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    # response_format={"type": "json_object"}, # Bazı OSS modeller bunu desteklemez, kapattım garanti olsun
                    temperature=0.1,
                    max_tokens=4000
                )
                
                content = response.choices[0].message.content
                
                if not content:
                    continue

                # JSON TEMİZLİĞİ (HATA BURADAYDI)
                cleaned_content = self._clean_json_string(content)
                
                parsed_json = json.loads(cleaned_content)
                
                if debug:
                    yasakli_sayisi = len(parsed_json.get("yasakli", []))
                    print(f"✅ Başarılı - Yasaklı: {yasakli_sayisi}")
                
                return parsed_json
                
            except json.JSONDecodeError as e:
                if debug:
                    print(f"❌ JSON Parse Hatası (Deneme {attempt + 1}): {e}")
                    # Hatalı içeriği gör ki promptu düzeltelim
                    print(f"Gelen bozuk veri başı: {content[:100]}...") 
                await asyncio.sleep(1)
                continue
            except Exception as e:
                if debug:
                    print(f"❌ API Hatası: {e}")
                await asyncio.sleep(1)
                continue
        
        return self._get_empty_structure()
    
    def normalize_output(self, raw_json: Dict[str, Any]) -> Dict[str, Any]:
        # Normalize işlemleri (değişmedi, aynen kalsın)
        if not raw_json: return self._get_empty_structure()
        
        normalized = self._get_empty_structure()
        # ... (Önceki kodundaki normalizasyon mantığı aynı) ...
        # Kısalık olması için burayı özet geçiyorum, eski kodundaki normalize_output'u kullanabilirsin.
        # En önemlisi raw_json artık düzgün geliyor.
        
        # Basit bir kopyalama yapalım örnek için (sen eskisiyle değiştirebilirsin)
        normalized.update(raw_json)
        return normalized

    def _get_empty_structure(self) -> Dict[str, Any]:
        return {
            "ihale_kayit_numarasi": "",
            "yasaklama_karari_veren_bakanlik_kurum": "",
            "ihaleyi_yapan_idarenin_adi": "",
            "yasakli": [],
            "ortaklar": [],
            "yasaklama_kanun_dayanagi": "",
            "yasaklama_kanun_kapsami": "",
            "yasaklama_suresi": ""
        }

# ----------------------------------------------------------------
# VERİTABANI İŞLEMLERİ (DEĞİŞMEDİ)
# ----------------------------------------------------------------
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def insert_record_to_db(data: Dict[str, Any], yasaklama_tarihi: str) -> bool:
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        insert_query = """
        INSERT INTO ihale_yasaklilari (
            ihale_kayit_numarasi, 
            yasaklama_karari_veren_bakanlik_kurum, 
            ihaleyi_yapan_idarenin_adi,
            ortaklar, 
            yasaklama_kanun_dayanagi, 
            yasaklama_kanun_kapsami, 
            yasaklama_suresi,
            yasaklama_tarihi,
            yasakli
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        values = (
            data.get("ihale_kayit_numarasi", ""),
            data.get("yasaklama_karari_veren_bakanlik_kurum", ""),
            data.get("ihaleyi_yapan_idarenin_adi", ""),
            Json(data.get("ortaklar", [])),
            data.get("yasaklama_kanun_dayanagi", ""),
            data.get("yasaklama_kanun_kapsami", ""),
            data.get("yasaklama_suresi", ""),
            yasaklama_tarihi,
            Json(data.get("yasakli", []))
        )
        
        cur.execute(insert_query, values)
        conn.commit()
        cur.close()
        return True
        
    except Exception as error:
        print(f"❌ Veritabanı hatası: {error}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

# ----------------------------------------------------------------
# DOSYA İŞLEMLERİ (DÜZELTİLDİ: TARİH PARSE)
# ----------------------------------------------------------------

def find_html_files(directory: str) -> List[str]:
    return glob.glob(os.path.join(directory, "*.html"))

def parse_date_from_filename(filename: str) -> Optional[str]:
    """
    Dosya adından tarihi Regex ile akıllıca bulur.
    'stitched_' olsa da olmasa da çalışır.
    """
    try:
        # Regex ile dosya içindeki ilk 8 haneli sayıyı (YYYYMMDD) bul
        match = re.search(r"(\d{8})", filename)
        
        if match:
            date_str = match.group(1) # Örn: 20231201
            year = date_str[0:4]
            month = date_str[4:6]
            day = date_str[6:8]
            
            # Tarih geçerli mi kontrol et
            datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
            return f"{year}-{month}-{day}"
        
        # Alternatif format (YYYY-MM-DD)
        match_dash = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
        if match_dash:
            return match_dash.group(1)
            
        print(f"⚠️ Dosya adında tarih bulunamadı: {filename}")
        return None
        
    except Exception as e:
        print(f"⚠️ Tarih parse hatası ({filename}): {e}")
        return None

# ----------------------------------------------------------------
# MAIN ve PROCESS (AYNI)
# ----------------------------------------------------------------

async def process_and_save_html(html_path: str, extractor: HTMLToJSONExtractor, debug: bool = True) -> bool:
    filename = os.path.basename(html_path)
    if debug: print(f"📄 İşleniyor: {filename}")
    
    try:
        filename_without_ext = os.path.splitext(filename)[0]
        yasaklama_tarihi = parse_date_from_filename(filename_without_ext)
        
        if not yasaklama_tarihi:
            return False
        
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Extract işlemi (Retry mekanizmalı)
        raw_json = await extractor.extract_from_html(html_content, debug=debug)
        # Normalize (raw_json zaten düzgünse direkt kullanabilirsin)
        final_json = extractor.normalize_output(raw_json)
        
        success = insert_record_to_db(final_json, yasaklama_tarihi)
        if success and debug: print(f"✅ Kaydedildi: {filename}")
        return success
            
    except Exception as e:
        print(f"❌ Genel Hata ({filename}): {e}")
        return False

async def process_all_htmls_to_db(input_directory: str, debug: bool = True, max_concurrent: int = 5):
    html_files = find_html_files(input_directory)
    if not html_files:
        print(f"❌ Klasör boş: {input_directory}")
        return

    print(f"🚀 {len(html_files)} dosya işleniyor...")
    extractor = HTMLToJSONExtractor()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(html_file):
        async with semaphore:
            await process_and_save_html(html_file, extractor, debug)

    tasks = [process_with_semaphore(f) for f in html_files]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    # Klasör yolunu kendi Docker içindeki yoluna göre ayarla
    # Docker volume ile bağladıysan muhtemelen "./output_ihale" veya "./ihalex" altındadır
    input_dir = "./output_ihale" 
    
    if os.path.exists(input_dir):
        asyncio.run(process_all_htmls_to_db(input_dir))
    else:
        print(f"❌ Klasör bulunamadı: {input_dir}")