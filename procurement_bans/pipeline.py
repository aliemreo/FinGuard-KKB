"""
Unified Pipeline for Turkish Official Gazette Ban Announcements
================================================================
Bu script üç ana işlevi birleştirir:
1. PDF Scraping: Resmi Gazete'den yasaklama PDF'lerini indirir
2. PDF Processing: PDF'leri OCR ile HTML'e dönüştürür  
3. HTML Extraction: HTML'den JSON verisi çıkarır ve veritabanına kaydeder

Kullanım:
    python unified_pipeline.py [--mode MODE] [--debug]
    
Modlar:
    all     : Tüm pipeline'ı çalıştır (scrape -> process -> extract)
    scrape  : Sadece PDF indirme
    process : Sadece PDF'leri OCR ile işleme
    extract : Sadece HTML'den JSON çıkarma ve DB kayıt
"""

import os
import sys
import json
import asyncio
import re
import time
import glob
import io
import argparse
import traceback
import shutil
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

# Third-party imports
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ----------------------------------------------------------------
# KONFİGÜRASYON
# ----------------------------------------------------------------
load_dotenv()

# API Ayarları
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://mia.csp.kloudeks.com/v1")
MODEL = os.getenv("MODEL", "gpt-oss-120b")

# Veritabanı Ayarları
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "database": os.getenv("DB_NAME", "ihale_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD")
}

# Klasör Ayarları
INPUT_PDF_FOLDER = Path("./ihale_yasakli")          # İndirilen ham PDF'ler
CORRECTION_PDF_FOLDER = Path("./ihale_duzeltme")  # Düzeltme/İptal PDF'leri
PROCESSED_PDF_FOLDER = Path("./processed_pdfs") # Stitcher ile işlenmiş PDF'ler
OUTPUT_HTML_FOLDER = Path("./output_ihale")     # OCR çıktısı HTML'ler
TEMP_IMG_FOLDER = OUTPUT_HTML_FOLDER / "temp_processed_images"

# Tarih Aralığı
START_DATE = "20251016"  # Başlangıç tarihi (YYYYMMDD) - Yakın tarih
END_DATE = "20230101"    # Bitiş tarihi (YYYYMMDD) - Geçmiş tarih

# PDF Processing Ayarları
BASE_TARGET_MAX_DIMENSION = 1600
DPI_REDUCTION_ATTEMPTS = [1.0, 0.9, 0.8, 0.6]

# Scraper Ayarları
TESSERACT_PATH = None  # Windows: r'C:\Program Files\Tesseract-OCR\tesseract.exe'
POPPLER_PATH = None    # Windows: r"C:\poppler-24.08.0\Library\bin"

# Log dosyaları
LOG_FILE = OUTPUT_HTML_FOLDER / "processing_log.txt"
OOM_ERRORS_FILE = OUTPUT_HTML_FOLDER / "oom_errors.json"

# OOM hataları için liste
oom_failed_pages = []


# ----------------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# ----------------------------------------------------------------

def log_message(message: str, print_console: bool = True):
    """Hem konsola hem de log dosyasına yaz"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_text = f"[{timestamp}] {message}"
    
    if print_console:
        print(log_text)
    
    OUTPUT_HTML_FOLDER.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_text + "\n")


def extract_date_from_filename(filename: str) -> Optional[str]:
    """Dosya adından tarihi çıkart (stitched_20250503 -> 20250503)"""
    match = re.search(r'(\d{8})', str(filename))
    if match:
        return match.group(1)
    match = re.search(r'(\d{4}[-_]\d{2}[-_]\d{2})', str(filename))
    if match:
        return match.group(1).replace('-', '').replace('_', '')
    return None


def is_in_date_range(date_str: str, start_date: str, end_date: str) -> bool:
    """Tarihin belirtilen aralıkta olup olmadığını kontrol et
    
    Args:
        date_str: Kontrol edilecek tarih (YYYYMMDD)
        start_date: Başlangıç tarihi (YYYYMMDD) - en yeni tarih
        end_date: Bitiş tarihi (YYYYMMDD) - en eski tarih
    
    Returns:
        True eğer date_str, end_date ve start_date arasındaysa
    """
    if date_str is None:
        return False
    try:
        date_int = int(date_str)
        start_int = int(start_date)
        end_int = int(end_date)
        # end_date <= date_str <= start_date (end_date en eski, start_date en yeni)
        return end_int <= date_int <= start_int
    except:
        return False


def parse_date_from_filename(filename: str) -> Optional[str]:
    """Dosya adından tarihi YYYY-MM-DD formatında döndür"""
    try:
        match = re.search(r"(\d{8})", filename)
        if match:
            date_str = match.group(1)
            year = date_str[0:4]
            month = date_str[4:6]
            day = date_str[6:8]
            datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
            return f"{year}-{month}-{day}"
        
        match_dash = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
        if match_dash:
            return match_dash.group(1)
        return None
    except Exception as e:
        log_message(f"⚠️ Tarih parse hatası ({filename}): {e}")
        return None


def filter_files_by_date_range(files: List[Path], start_date_str: str, end_date_str: str) -> List[Path]:
    """Dosyaları tarih aralığına göre filtrele
    
    Args:
        files: Filtrelenecek dosya listesi
        start_date_str: Başlangıç tarihi (YYYYMMDD) - en yeni tarih
        end_date_str: Bitiş tarihi (YYYYMMDD) - en eski tarih
    
    Returns:
        Tarih aralığına uyan dosyalar
    """
    filtered = []
    for f in files:
        file_date = extract_date_from_filename(f.name)
        if file_date and is_in_date_range(file_date, start_date_str, end_date_str):
            filtered.append(f)
    return filtered


# ----------------------------------------------------------------
# BÖLÜM 1: PDF SCRAPER (Resmi Gazete'den PDF İndirme)
# ----------------------------------------------------------------

class YasaklamaScraper:
    """Resmi Gazete'den yasaklama ilanlarını tarayan ve indiren sınıf."""
    
    def __init__(self, 
                 output_dir: str = "deneysel",
                 correction_dir: str = "deneyselduz",
                 tesseract_path: str = None,
                 poppler_path: str = None):
        self.output_dir = output_dir
        self.correction_dir = correction_dir
        self.poppler_path = poppler_path
        self.fuzzy_threshold = 80
        
        # Lazy import for optional dependencies
        self.pytesseract = None
        if tesseract_path:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            self.pytesseract = pytesseract
        
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.correction_dir, exist_ok=True)
        
        self.stats = {
            "total_days_scanned": 0,
            "total_pdfs_found": 0,
            "yasaklama_pdfs": 0,
            "correction_pdfs": 0,
            "failed_downloads": 0,
            "no_page_days": 0
        }
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        self.correction_patterns = [
            r'KALDIR', r'İPTAL', r'DÜZELT', r'DUZELT',
            r'KALDIRMA', r'İPTALİ', r'DÜZELTİLMESİ', r'DÜZELTİM',
        ]
        
        self.yasaklama_pattern = r'İ?HALE(LE)?R?E\s*KATILMAKTAN\s*YASAKLAMA(\s*KARARI)?'
        self.yasaklama_keywords = [
            "İHALELERE KATILMAKTAN YASAKLAMA",
            "İHALERE KATILMAKTAN YASAKLAMA",
            "İHALELERE KATILMAKTAN YASAKLAMA KARARI",
            "İHALERE KATILMAKTAN YASAKLAMA KARARI"
        ]

    def normalize_text(self, text: str) -> str:
        return text.upper().replace('i', 'İ').replace('ı', 'I')

    def is_yasaklama(self, text: str) -> bool:
        from rapidfuzz import fuzz
        normalized = self.normalize_text(text)
        if re.search(self.yasaklama_pattern, normalized, re.IGNORECASE):
            return True
        for keyword in self.yasaklama_keywords:
            norm_keyword = self.normalize_text(keyword)
            score = fuzz.partial_ratio(norm_keyword, normalized)
            if score >= self.fuzzy_threshold:
                return True
        return False

    def is_correction(self, text: str) -> bool:
        normalized = self.normalize_text(text)
        for pattern in self.correction_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return True
        return False

    def check_pdf_text(self, pdf_url: str) -> Tuple[bool, bool, str]:
        try:
            from pypdf import PdfReader
            r = requests.get(pdf_url, headers=self.headers, timeout=30)
            pdf_file = io.BytesIO(r.content)
            reader = PdfReader(pdf_file)
            
            all_text = ""
            for page in reader.pages:
                all_text += (page.extract_text() or "") + "\n"
            
            title_text = all_text[:500] if all_text else ""
            is_yasaklama = self.is_yasaklama(all_text)
            is_correction = self.is_correction(title_text)
            return is_yasaklama, is_correction, title_text
        except Exception as e:
            log_message(f"    ✗ Text extraction hatası: {e}")
            return False, False, ""

    def check_pdf_ocr(self, pdf_url: str, crop_ratio: float = 0.25) -> Tuple[bool, bool, str]:
        if self.pytesseract is None:
            return False, False, ""
        try:
            from pdf2image import convert_from_bytes
            r = requests.get(pdf_url, headers=self.headers, timeout=30)
            pdf_bytes = r.content
            
            images = convert_from_bytes(
                pdf_bytes, dpi=300, first_page=1, last_page=1,
                poppler_path=self.poppler_path
            )
            
            if not images:
                return False, False, ""
            
            first_page = images[0]
            width, height = first_page.size
            crop_height = int(height * crop_ratio)
            title_region = first_page.crop((0, 0, width, crop_height))
            
            title_text = self.pytesseract.image_to_string(title_region, lang='tur')
            is_yasaklama = self.is_yasaklama(title_text)
            is_correction = self.is_correction(title_text)
            return is_yasaklama, is_correction, title_text
        except Exception as e:
            log_message(f"    ✗ OCR hatası: {e}")
            return False, False, ""

    def download_pdf(self, pdf_url: str, save_path: str) -> bool:
        try:
            r = requests.get(pdf_url, headers=self.headers, timeout=60)
            if r.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(r.content)
                return True
            return False
        except Exception as e:
            log_message(f"    ✗ İndirme hatası: {e}")
            return False

    def scan_single_day(self, year: int, month: int, day: int) -> List[Dict]:
        year_str = str(year)
        month_str = str(month).zfill(2)
        day_str = str(day).zfill(2)
        ymd = f"{year_str}{month_str}{day_str}"
        
        url = f"https://www.resmigazete.gov.tr/ilanlar/eskiilanlar/{year_str}/{month_str}/{ymd}-4.htm"
        results = []
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code != 200:
                return results
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = soup.find_all('a')
            
            pdf_links = []
            for link in links:
                href = link.get('href')
                if href and href.lower().endswith('.pdf'):
                    pdf_links.append(urljoin(url, href))
            
            if not pdf_links:
                return results
            
            log_message(f"  {len(pdf_links)} PDF bulundu, taranıyor...")
            
            for idx, pdf_url in enumerate(pdf_links, 1):
                is_yasaklama, is_correction, title = self.check_pdf_text(pdf_url)
                
                if not is_yasaklama:
                    is_yasaklama_ocr, is_correction_ocr, title_ocr = self.check_pdf_ocr(pdf_url)
                    if is_yasaklama_ocr:
                        is_yasaklama = True
                        is_correction = is_correction_ocr
                        title = title_ocr
                
                if is_yasaklama:
                    results.append({
                        "url": pdf_url,
                        "date": f"{year_str}-{month_str}-{day_str}",
                        "is_correction": is_correction,
                        "title_preview": title[:200] if title else ""
                    })
                    status = "DÜZELTME/İPTAL" if is_correction else "YASAKLAMA"
                    log_message(f"    [{idx}] ✓ {status} bulundu")
            
            return results
        except Exception as e:
            log_message(f"  ✗ Hata: {e}")
            return results

    def generate_date_range(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        dates = []
        current = start_date
        while current >= end_date:
            dates.append(current)
            current -= timedelta(days=1)
        return dates

    def run_full_scan(self,
                      start_date: datetime = datetime(2025, 12, 12),
                      end_date: datetime = datetime(2022, 12, 1),
                      delay_between_days: float = 0.5) -> Dict:
        log_message("=" * 70)
        log_message("YASAKLAMA PDF TARAMA VE İNDİRME")
        log_message(f"Tarih Aralığı: {start_date.strftime('%d.%m.%Y')} -> {end_date.strftime('%d.%m.%Y')}")
        log_message("=" * 70)
        
        all_results = []
        dates = self.generate_date_range(start_date, end_date)
        total_days = len(dates)
        
        for day_idx, date in enumerate(dates, 1):
            log_message(f"\n[{day_idx}/{total_days}] {date.strftime('%d.%m.%Y')} taranıyor...")
            self.stats["total_days_scanned"] += 1
            
            day_results = self.scan_single_day(date.year, date.month, date.day)
            
            if not day_results:
                continue
            
            for result in day_results:
                pdf_url = result["url"]
                pdf_name = pdf_url.split('/')[-1]
                date_prefix = result["date"].replace('-', '')
                
                if result["is_correction"]:
                    save_dir = self.correction_dir
                    save_path = os.path.join(save_dir, f"{date_prefix}_{pdf_name}")
                    self.stats["correction_pdfs"] += 1
                else:
                    save_dir = self.output_dir
                    save_path = os.path.join(save_dir, f"{date_prefix}_{pdf_name}")
                    self.stats["yasaklama_pdfs"] += 1
                
                if self.download_pdf(pdf_url, save_path):
                    result["local_path"] = save_path
                    log_message(f"    ✓ İndirildi: {save_path}")
                else:
                    self.stats["failed_downloads"] += 1
                
                self.stats["total_pdfs_found"] += 1
                all_results.append(result)
            
            time.sleep(delay_between_days)
        
        log_message("\n" + "=" * 70)
        log_message("TARAMA TAMAMLANDI")
        log_message(f"Bulunan toplam PDF: {self.stats['total_pdfs_found']}")
        log_message(f"  • Normal yasaklama: {self.stats['yasaklama_pdfs']}")
        log_message(f"  • Düzeltme/İptal: {self.stats['correction_pdfs']}")
        log_message("=" * 70)
        
        return {"stats": self.stats, "results": all_results}


# ----------------------------------------------------------------
# BÖLÜM 2: PDF STITCHER (PDF Temizleme ve Birleştirme)
# ----------------------------------------------------------------

class SmartPDFStitcher:
    """PDF'leri temizleyip birleştiren sınıf - Sayı/ID'leri gizler"""
    
    def __init__(self, input_path: str, output_path: str):
        self.input_path = input_path
        self.output_path = output_path
        self.gap_threshold = 30
        self.margin_padding = 3
        self.found_numbers = []

    def get_all_content_boxes(self, page) -> List[Dict]:
        content_boxes = []
        words = page.extract_words()
        for w in words:
            content_boxes.append({
                "top": w['top'], "bottom": w['bottom'],
                "x0": w['x0'], "x1": w['x1']
            })
        graphics = (page.lines or []) + (page.rects or [])
        for g in graphics:
            content_boxes.append({
                "top": min(g['top'], g['bottom']),
                "bottom": max(g['top'], g['bottom']),
                "x0": min(g['x0'], g['x1']),
                "x1": max(g['x0'], g['x1'])
            })
        images = page.images or []
        for img in images:
            content_boxes.append({
                "top": img['top'], "bottom": img['bottom'],
                "x0": img['x0'], "x1": img['x1']
            })
        return content_boxes

    def analyze_page_content(self, plumber_page, y_min=0, y_max=None) -> List[Dict]:
        if y_max is None:
            y_max = plumber_page.height

        boxes = self.get_all_content_boxes(plumber_page)
        filtered_boxes = [b for b in boxes if b['top'] >= y_min and b['bottom'] <= y_max]
        
        if not filtered_boxes:
            return []

        min_x = min([b['x0'] for b in filtered_boxes])
        max_x = max([b['x1'] for b in filtered_boxes])
        crop_left = max(0, min_x - self.margin_padding)
        crop_right = min(plumber_page.width, max_x + self.margin_padding)
        
        intervals = sorted([(b['top'], b['bottom']) for b in filtered_boxes], key=lambda x: x[0])
        merged_intervals = []
        
        if intervals:
            curr_top, curr_bottom = intervals[0]
            for next_top, next_bottom in intervals[1:]:
                if next_top < curr_bottom:
                    curr_bottom = max(curr_bottom, next_bottom)
                else:
                    merged_intervals.append((curr_top, curr_bottom))
                    curr_top, curr_bottom = next_top, next_bottom
            merged_intervals.append((curr_top, curr_bottom))
        
        final_segments = []
        if not merged_intervals:
            return []

        current_seg_start = max(y_min, merged_intervals[0][0] - self.margin_padding)
        current_seg_end = merged_intervals[0][1]
        
        for next_top, next_bottom in merged_intervals[1:]:
            gap = next_top - current_seg_end
            if gap > self.gap_threshold:
                final_segments.append({
                    "top": current_seg_start,
                    "bottom": current_seg_end + self.margin_padding,
                    "left": crop_left, "right": crop_right
                })
                current_seg_start = next_top - self.margin_padding
                current_seg_end = next_bottom
            else:
                current_seg_end = max(current_seg_end, next_bottom)
        
        final_segments.append({
            "top": current_seg_start,
            "bottom": min(y_max, current_seg_end + self.margin_padding),
            "left": crop_left, "right": crop_right
        })
        return final_segments

    def process(self) -> Tuple[str, List[str]]:
        import pdfplumber
        from pypdf import PdfReader, PdfWriter, PageObject, Transformation
        
        log_message(f"🧹 [STITCHER] PDF işleniyor: {self.input_path}")
        number_pattern = re.compile(r'^\d[\w\-/]*')
        split_points = []
        
        with pdfplumber.open(self.input_path) as plumber_pdf:
            total_pages = len(plumber_pdf.pages)
            split_points.append({'page_index': 0, 'cut_before': 0.0, 'cut_after': 0.0, 'text': 'START'})
            
            for i, page in enumerate(plumber_pdf.pages):
                words = page.extract_words()
                words.sort(key=lambda x: (x['top'], x['x0']))
                for w in words:
                    if number_pattern.match(w['text']):
                        self.found_numbers.append(w['text'])
                        split_points.append({
                            'page_index': i, 'cut_before': w['top'],
                            'cut_after': w['bottom'], 'text': w['text']
                        })

            last_page_height = plumber_pdf.pages[-1].height
            split_points.append({
                'page_index': total_pages - 1,
                'cut_before': last_page_height,
                'cut_after': last_page_height, 'text': 'END'
            })

        document_groups = []
        with pdfplumber.open(self.input_path) as plumber_pdf:
            for idx in range(len(split_points) - 1):
                start_pt = split_points[idx]
                end_pt = split_points[idx+1]
                current_group = []
                
                for p_idx in range(start_pt['page_index'], end_pt['page_index'] + 1):
                    page = plumber_pdf.pages[p_idx]
                    y_min = 0 if p_idx != start_pt['page_index'] else start_pt['cut_after']
                    y_max = page.height if p_idx != end_pt['page_index'] else end_pt['cut_before']
                    
                    if p_idx == start_pt['page_index'] and p_idx == end_pt['page_index']:
                        if y_min >= y_max:
                            continue

                    clean_segments = self.analyze_page_content(page, y_min=y_min + 1, y_max=y_max - 1)
                    if clean_segments:
                        current_group.append({
                            "page_index": p_idx,
                            "original_height": page.height,
                            "segments": clean_segments
                        })
                
                if current_group:
                    document_groups.append(current_group)

        reader = PdfReader(self.input_path)
        writer = PdfWriter()

        for group in document_groups:
            total_height = sum(seg["bottom"] - seg["top"] for pd in group for seg in pd["segments"] if seg["bottom"] - seg["top"] > 1)
            max_width = max((seg["right"] - seg["left"] for pd in group for seg in pd["segments"]), default=0)
            
            if total_height == 0:
                continue

            new_page = PageObject.create_blank_page(width=max_width + 20, height=total_height + 20)
            current_y = total_height + 10
            
            for page_data in group:
                source_page = reader.pages[page_data["page_index"]]
                orig_h = float(page_data["original_height"])

                for seg in page_data["segments"]:
                    seg_h = seg["bottom"] - seg["top"]
                    if seg_h <= 1:
                        continue

                    pypdf_upper = orig_h - seg["top"]
                    pypdf_lower = orig_h - seg["bottom"]
                    
                    source_page.cropbox.lower_left = (float(seg["left"]), float(pypdf_lower))
                    source_page.cropbox.upper_right = (float(seg["right"]), float(pypdf_upper))
                    
                    current_y -= seg_h
                    new_page.merge_transformed_page(
                        source_page,
                        Transformation().translate(tx=10 - float(seg["left"]), ty=current_y - pypdf_lower)
                    )

            writer.add_page(new_page)

        with open(self.output_path, "wb") as f:
            writer.write(f)
        
        log_message(f"✅ [STITCHER] Optimize edilmiş PDF: {self.output_path}")
        return self.output_path, self.found_numbers


class BatchPDFProcessor:
    """İndirilen tüm PDF'leri SmartPDFStitcher ile işleyen sınıf."""
    
    def __init__(self, input_dir: str, output_dir: str = None, 
                 start_date_str: str = None, end_date_str: str = None):
        self.input_dir = input_dir
        self.output_dir = output_dir or os.path.join(input_dir, "processed")
        self.start_date_str = start_date_str
        self.end_date_str = end_date_str
        os.makedirs(self.output_dir, exist_ok=True)
        self.results = []

    def process_all(self) -> List[Dict]:
        all_pdfs = [Path(self.input_dir) / f for f in os.listdir(self.input_dir) if f.lower().endswith('.pdf')]
        
        # Tarih filtrelemesi uygula
        if self.start_date_str and self.end_date_str:
            pdf_files = filter_files_by_date_range(all_pdfs, self.start_date_str, self.end_date_str)
            log_message(f"📅 Tarih filtresi: {self.start_date_str} -> {self.end_date_str}")
            log_message(f"   Toplam: {len(all_pdfs)}, Filtrelenmiş: {len(pdf_files)}")
        else:
            pdf_files = all_pdfs
            log_message("📅 Tarih filtresi yok - tüm PDF'ler işlenecek")
        
        log_message(f"\n{'=' * 70}")
        log_message(f"BATCH PDF STITCHER İŞLEME")
        log_message(f"Kaynak: {self.input_dir}")
        log_message(f"Toplam PDF: {len(pdf_files)}")
        log_message(f"{'=' * 70}\n")
        
        for idx, pdf_path in enumerate(pdf_files, 1):
            pdf_file = pdf_path.name
            log_message(f"\n[{idx}/{len(pdf_files)}] İşleniyor: {pdf_file}")
            input_path = str(pdf_path)
            output_path = os.path.join(self.output_dir, f"stitched_{pdf_file}")
            
            try:
                stitcher = SmartPDFStitcher(input_path, output_path)
                result_path, found_ids = stitcher.process()
                self.results.append({
                    "original_file": pdf_file,
                    "processed_file": os.path.basename(result_path),
                    "found_ids": found_ids,
                    "status": "success"
                })
            except Exception as e:
                log_message(f"  ✗ Hata: {e}")
                self.results.append({
                    "original_file": pdf_file,
                    "status": f"error: {str(e)}"
                })
        
        return self.results


# ----------------------------------------------------------------
# BÖLÜM 3: PDF OCR İŞLEME (PaddleOCR ile HTML'e dönüştürme)
# ----------------------------------------------------------------

def is_oom_error(error) -> bool:
    error_str = str(error).lower()
    return any(kw in error_str for kw in ["out of memory", "cuda out of memory", "resourceexhaustederror"])


def convert_pdf_page_to_image(pdf_path, page_num, output_folder, target_max_dim=BASE_TARGET_MAX_DIMENSION):
    import fitz
    try:
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            doc.close()
            return None, None
            
        page = doc[page_num]
        rect = page.rect
        long_side_pt = max(rect.width, rect.height)
        zoom_factor = target_max_dim / long_side_pt if long_side_pt > 0 else 2.0
        
        MAX_PIXELS = 2_100_000
        if int(rect.width * zoom_factor) * int(rect.height * zoom_factor) > MAX_PIXELS:
            zoom_factor *= 0.9
        if zoom_factor > 4.0:
            zoom_factor = 4.0
            
        mat = fitz.Matrix(zoom_factor, zoom_factor)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        save_path = output_folder / f"temp_page_{page_num+1}.png"
        pix.save(save_path)
        actual_size = (pix.width, pix.height)
        doc.close()
        return str(save_path), actual_size
    except Exception as e:
        log_message(f"❌ Sayfa çevirme hatası (sayfa {page_num+1}): {e}")
        return None, None


def enhance_image_for_ocr(image_path):
    import cv2
    import numpy as np
    try:
        img = cv2.imread(str(image_path))
        if img is None:
            return str(image_path)
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        kernel = np.array([[0, -0.5, 0], [-0.5, 3, -0.5], [0, -0.5, 0]])
        sharpened = cv2.filter2D(gray, -1, kernel)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(sharpened)
        final_img = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        cv2.imwrite(str(image_path), final_img)
        return str(image_path)
    except Exception as e:
        log_message(f"❌ Görüntü iyileştirme hatası: {e}")
        return str(image_path)


def process_single_page_with_retry(pdf_path, page_num, pipeline, pdf_stem):
    import paddle
    
    for attempt_idx, dpi_scale in enumerate(DPI_REDUCTION_ATTEMPTS):
        current_target_dim = int(BASE_TARGET_MAX_DIMENSION * dpi_scale)
        
        if attempt_idx > 0:
            log_message(f"   🔄 Retry ({attempt_idx+1}/{len(DPI_REDUCTION_ATTEMPTS)}): DPI %{int(dpi_scale*100)}")
        
        try:
            paddle.device.cuda.empty_cache()
            time.sleep(1)
            
            TEMP_IMG_FOLDER.mkdir(parents=True, exist_ok=True)
            result = convert_pdf_page_to_image(pdf_path, page_num, TEMP_IMG_FOLDER, target_max_dim=current_target_dim)
            
            if result[0] is None:
                return False
            
            img_path, img_size = result
            if attempt_idx == 0:
                log_message(f"   📐 Boyut: {img_size[0]}x{img_size[1]}px")
            
            enhanced_img = enhance_image_for_ocr(img_path)
            output = pipeline.predict(input=enhanced_img, format_block_content=True, layout_nms=True)
            
            if output and len(output) > 0:
                page_markdowns = [res.markdown for res in output]
                if page_markdowns:
                    final_text = pipeline.concatenate_markdown_pages(page_markdowns)
                    output_path = OUTPUT_HTML_FOLDER / f"{pdf_stem}_sayfa_{page_num+1}.html"
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(final_text)
                    log_message(f"✅ {pdf_stem} - Sayfa {page_num+1}: Başarılı")
            
            if os.path.exists(img_path):
                os.remove(img_path)
            return True
            
        except RuntimeError as e:
            if is_oom_error(e):
                log_message(f"   💥 OOM Hatası - Sayfa {page_num+1}")
                paddle.device.cuda.empty_cache()
                time.sleep(2)
                if attempt_idx == len(DPI_REDUCTION_ATTEMPTS) - 1:
                    oom_failed_pages.append({
                        "pdf_name": str(pdf_path.name),
                        "page_number": page_num + 1,
                        "timestamp": datetime.now().isoformat()
                    })
                    return False
                continue
            else:
                log_message(f"❌ Runtime Hatası: {str(e)[:200]}")
                return False
        except Exception as e:
            log_message(f"❌ Hata: {str(e)[:200]}")
            return False
    return False


def process_all_pdfs_ocr(start_date_str: str = None, end_date_str: str = None):
    """PDF'leri OCR ile işle ve HTML'e dönüştür
    
    Args:
        start_date_str: Başlangıç tarihi (YYYYMMDD formatında)
        end_date_str: Bitiş tarihi (YYYYMMDD formatında)
    """
    import fitz
    import paddle
    from paddleocr import PaddleOCRVL
    
    if not PROCESSED_PDF_FOLDER.exists():
        log_message(f"❌ İşlenmiş PDF klasörü bulunamadı: {PROCESSED_PDF_FOLDER}")
        return
    
    OUTPUT_HTML_FOLDER.mkdir(parents=True, exist_ok=True)
    
    all_pdfs = list(PROCESSED_PDF_FOLDER.glob("*.pdf"))
    
    # Tarih filtresi uygulanacaksa filtrele, yoksa tüm PDF'leri al
    if start_date_str and end_date_str:
        filtered_pdfs = filter_files_by_date_range(all_pdfs, start_date_str, end_date_str)
        log_message(f"📅 Tarih filtresi: {start_date_str} -> {end_date_str}")
        log_message(f"   Toplam: {len(all_pdfs)}, Filtrelenmiş: {len(filtered_pdfs)}")
    else:
        filtered_pdfs = all_pdfs
        log_message("📅 Tarih filtresi yok - tüm PDF'ler işlenecek")
    
    pdf_files = sorted(filtered_pdfs, key=lambda x: extract_date_from_filename(x.stem) or "", reverse=True)
    
    if not pdf_files:
        log_message("⚠️ İşlenecek PDF bulunamadı!")
        return
    
    log_message(f"📚 {len(pdf_files)} PDF işlenecek")
    log_message("🚀 PaddleOCR VL başlatılıyor...")
    
    try:
        pipeline = PaddleOCRVL(
            use_layout_detection=True,
            layout_threshold=0.5,
            use_doc_orientation_classify=True,
            use_chart_recognition=True
        )
    except Exception as e:
        log_message(f"❌ Model yükleme hatası: {e}")
        return
    
    total_success = 0
    total_failed = 0
    
    for pdf_idx, pdf_path in enumerate(pdf_files, 1):
        pdf_stem = pdf_path.stem
        log_message(f"\n📄 [{pdf_idx}/{len(pdf_files)}] {pdf_path.name}")
        
        try:
            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            doc.close()
            
            for page_num in range(num_pages):
                if process_single_page_with_retry(pdf_path, page_num, pipeline, pdf_stem):
                    total_success += 1
                else:
                    total_failed += 1
        except Exception as e:
            log_message(f"❌ PDF açma hatası: {e}")
        
        paddle.device.cuda.empty_cache()
    
    log_message(f"\n✅ Başarılı: {total_success}, ❌ Başarısız: {total_failed}")
    
    if oom_failed_pages:
        with open(OOM_ERRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(oom_failed_pages, f, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------
# BÖLÜM 4: HTML'DEN JSON ÇIKARMA VE VERİTABANI
# ----------------------------------------------------------------

class HTMLToJSONExtractor:
    """HTML tablolarından yapılandırılmış JSON verisi çıkarır"""
    
    def __init__(self, model_name: str = MODEL):
        self.model_name = model_name
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    def _clean_json_string(self, json_str: str) -> str:
        if "```json" in json_str:
            json_str = json_str.replace("```json", "").replace("```", "")
        elif "```" in json_str:
            json_str = json_str.replace("```", "")
        return json_str.strip()

    def _create_extraction_prompt(self, html_content: str) -> str:
        return f"""Sen Türk Resmi Gazete yasaklama ilanlarından veri çıkaran bir uzmansın.

Aşağıdaki HTML içeriğinden verileri çıkarıp JSON formatında döndür.

🔴 ÖNEMLİ: SADECE SAF JSON DÖNDÜR. Markdown (```json) KULLANMA.

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
        import html as html_module
        cleaned = html_module.unescape(html_content)
        cleaned = cleaned.replace("Â", "").replace("â", "a")
        return cleaned
    
    async def extract_from_html(self, html_content: str, debug: bool = False, max_retries: int = 3) -> Dict[str, Any]:
        html_content = self._preprocess_html(html_content)
        
        for attempt in range(max_retries):
            try:
                prompt = self._create_extraction_prompt(html_content)
                
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=4000
                )
                
                content = response.choices[0].message.content
                if not content:
                    continue

                cleaned_content = self._clean_json_string(content)
                parsed_json = json.loads(cleaned_content)
                
                if debug:
                    log_message(f"✅ JSON başarılı - Yasaklı: {len(parsed_json.get('yasakli', []))}")
                return parsed_json
                
            except json.JSONDecodeError as e:
                if debug:
                    log_message(f"❌ JSON Parse Hatası (Deneme {attempt + 1}): {e}")
                await asyncio.sleep(1)
            except Exception as e:
                if debug:
                    log_message(f"❌ API Hatası: {e}")
                await asyncio.sleep(1)
        
        return self._get_empty_structure()
    
    def normalize_output(self, raw_json: Dict[str, Any]) -> Dict[str, Any]:
        if not raw_json:
            return self._get_empty_structure()
        normalized = self._get_empty_structure()
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


def get_db_connection():
    import psycopg2
    return psycopg2.connect(**DB_CONFIG)


def insert_record_to_db(data: Dict[str, Any], yasaklama_tarihi: str) -> bool:
    import psycopg2
    from psycopg2.extras import Json
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        insert_query = """
        INSERT INTO ihale_yasaklilari (
            ihale_kayit_numarasi, yasaklama_karari_veren_bakanlik_kurum, 
            ihaleyi_yapan_idarenin_adi, ortaklar, yasaklama_kanun_dayanagi, 
            yasaklama_kanun_kapsami, yasaklama_suresi, yasaklama_tarihi, yasakli
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
        log_message(f"❌ DB hatası: {error}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


async def process_and_save_html(html_path: str, extractor: HTMLToJSONExtractor, debug: bool = True) -> bool:
    filename = os.path.basename(html_path)
    
    try:
        filename_without_ext = os.path.splitext(filename)[0]
        yasaklama_tarihi = parse_date_from_filename(filename_without_ext)
        
        if not yasaklama_tarihi:
            return False
        
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        raw_json = await extractor.extract_from_html(html_content, debug=debug)
        final_json = extractor.normalize_output(raw_json)

        # LLM çağrısı başarısız olursa (yanlış API_KEY/BASE_URL, timeout) extractor boş
        # şablon döndürür; bunu veritabanına boş satır olarak yazma.
        if not final_json.get("yasakli") and not final_json.get("ihale_kayit_numarasi"):
            log_message(f"⚠️ LLM veri döndürmedi, DB'ye yazılmadı: {filename}")
            return False

        success = insert_record_to_db(final_json, yasaklama_tarihi)
        if success and debug:
            log_message(f"✅ DB'ye kaydedildi: {filename}")
        return success
    except Exception as e:
        log_message(f"❌ Hata ({filename}): {e}")
        return False


async def process_all_htmls_to_db(input_directory: str, debug: bool = True, max_concurrent: int = 5,
                                   start_date_str: str = None, end_date_str: str = None):
    """HTML dosyalarını JSON'a çevirip veritabanına kaydet
    
    Args:
        input_directory: HTML dosyalarının bulunduğu klasör
        debug: Debug modunu etkinleştir
        max_concurrent: Maksimum eşzamanlı işlem sayısı
        start_date_str: Başlangıç tarihi (YYYYMMDD)
        end_date_str: Bitiş tarihi (YYYYMMDD)
    """
    all_html_files = [Path(f) for f in glob.glob(os.path.join(input_directory, "*.html"))]
    
    # Tarih filtrelemesi uygula
    if start_date_str and end_date_str:
        html_files = filter_files_by_date_range(all_html_files, start_date_str, end_date_str)
        log_message(f"📅 Tarih filtresi: {start_date_str} -> {end_date_str}")
        log_message(f"   Toplam: {len(all_html_files)}, Filtrelenmiş: {len(html_files)}")
    else:
        html_files = all_html_files
        log_message("📅 Tarih filtresi yok - tüm HTML'ler işlenecek")
    
    if not html_files:
        log_message(f"❌ İşlenecek HTML dosyası bulunamadı: {input_directory}")
        return

    log_message(f"🚀 {len(html_files)} HTML dosyası işleniyor...")
    extractor = HTMLToJSONExtractor()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(html_file):
        async with semaphore:
            await process_and_save_html(str(html_file), extractor, debug)

    tasks = [process_with_semaphore(f) for f in html_files]
    await asyncio.gather(*tasks)


# ----------------------------------------------------------------
# ANA ÇALIŞTIRMA FONKSİYONLARI
# ----------------------------------------------------------------

def run_scraper(start_date: datetime, end_date: datetime):
    """PDF'leri Resmi Gazete'den indir"""
    log_message("\n" + "=" * 70)
    log_message("ADIM 1: PDF TARAMA VE İNDİRME")
    log_message("=" * 70)
    
    scraper = YasaklamaScraper(
        output_dir=str(INPUT_PDF_FOLDER),
        correction_dir=str(CORRECTION_PDF_FOLDER),
        tesseract_path=TESSERACT_PATH,
        poppler_path=POPPLER_PATH
    )
    return scraper.run_full_scan(start_date=start_date, end_date=end_date)


def run_stitcher(start_date: datetime = None, end_date: datetime = None):
    """PDF'leri SmartPDFStitcher ile işle"""
    log_message("\n" + "=" * 70)
    log_message("ADIM 2: PDF STITCHER İŞLEME")
    log_message("=" * 70)
    
    # datetime'ı YYYYMMDD string formatına çevir
    start_str = start_date.strftime("%Y%m%d") if start_date else None
    end_str = end_date.strftime("%Y%m%d") if end_date else None
    
    if INPUT_PDF_FOLDER.exists() and os.listdir(INPUT_PDF_FOLDER):
        processor = BatchPDFProcessor(
            input_dir=str(INPUT_PDF_FOLDER),
            output_dir=str(PROCESSED_PDF_FOLDER),
            start_date_str=start_str,
            end_date_str=end_str
        )
        return processor.process_all()
    else:
        log_message("İşlenecek PDF bulunamadı.")
        return []


def run_ocr(start_date: datetime = None, end_date: datetime = None):
    """PDF'leri OCR ile HTML'e dönüştür"""
    log_message("\n" + "=" * 70)
    log_message("ADIM 3: PDF OCR İŞLEME")
    log_message("=" * 70)
    
    # datetime'ı YYYYMMDD string formatına çevir
    start_str = start_date.strftime("%Y%m%d") if start_date else None
    end_str = end_date.strftime("%Y%m%d") if end_date else None
    
    process_all_pdfs_ocr(start_str, end_str)


def run_extractor(start_date: datetime = None, end_date: datetime = None):
    """HTML'lerden JSON çıkar ve DB'ye kaydet"""
    log_message("\n" + "=" * 70)
    log_message("ADIM 4: HTML -> JSON -> DB")
    log_message("=" * 70)
    
    # datetime'ı YYYYMMDD string formatına çevir
    start_str = start_date.strftime("%Y%m%d") if start_date else None
    end_str = end_date.strftime("%Y%m%d") if end_date else None
    
    if OUTPUT_HTML_FOLDER.exists():
        asyncio.run(process_all_htmls_to_db(
            str(OUTPUT_HTML_FOLDER),
            start_date_str=start_str,
            end_date_str=end_str
        ))
    else:
        log_message(f"❌ HTML klasörü bulunamadı: {OUTPUT_HTML_FOLDER}")


def main():
    parser = argparse.ArgumentParser(description="Unified Pipeline for Turkish Official Gazette Ban Announcements")
    parser.add_argument("--mode", choices=["all", "scrape", "stitch", "ocr", "extract"], 
                       default="all", help="İşlem modu")
    parser.add_argument("--debug", action="store_true", help="Debug modu")
    parser.add_argument("--start-date", type=str, default=None, 
                       help="Başlangıç tarihi (YYYY-MM-DD) - varsayılan: bugün")
    parser.add_argument("--end-date", type=str, default=None, 
                       help="Bitiş tarihi (YYYY-MM-DD) - varsayılan: 2022-12-01")
    
    args = parser.parse_args()
    
    # Tarihler belirtilmemişse varsayılanları kullan
    if args.start_date:
        start_dt = datetime.strptime(args.start_date, "%Y-%m-%d")
    else:
        start_dt = datetime.now()  # Bugünün tarihi
    
    if args.end_date:
        end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")
    else:
        end_dt = datetime(2022, 12, 1)  # Varsayılan bitiş
    
    log_message("🎬 UNIFIED PIPELINE BAŞLATILIYOR")
    log_message(f"Mode: {args.mode}")
    log_message(f"📅 Tarih Aralığı: {start_dt.strftime('%d.%m.%Y')} -> {end_dt.strftime('%d.%m.%Y')}")
    log_message("=" * 70)
    
    if args.mode == "all":
        run_scraper(start_dt, end_dt)
        run_stitcher(start_dt, end_dt)
        run_ocr(start_dt, end_dt)
        run_extractor(start_dt, end_dt)
    elif args.mode == "scrape":
        run_scraper(start_dt, end_dt)
    elif args.mode == "stitch":
        run_stitcher(start_dt, end_dt)
    elif args.mode == "ocr":
        run_ocr(start_dt, end_dt)
    elif args.mode == "extract":
        run_extractor(start_dt, end_dt)
    
    log_message("\n" + "=" * 70)
    log_message("✅ TÜM İŞLEMLER TAMAMLANDI!")
    log_message("=" * 70)


if __name__ == "__main__":
    main()
