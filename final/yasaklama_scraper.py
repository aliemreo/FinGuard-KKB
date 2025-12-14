import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import io
import os
from pypdf import PdfReader, PdfWriter, PageObject, Transformation
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import pdfplumber
from typing import List, Dict, Tuple, Optional
import re
from datetime import datetime, timedelta
from rapidfuzz import fuzz
import time
import json


class YasaklamaScraper:
    """
    Resmi Gazete'den yasaklama ilanlarını tarayan ve indiren sınıf.
    1 Aralık 2022 - 12 Aralık 2025 arası tüm ilanları işler.
    """
    
    def __init__(self, 
                 output_dir: str = "yasaklama_pdfs",
                 correction_dir: str = "duzeltme_iptal_pdfs",
                 tesseract_path: str = None,
                 poppler_path: str = None):
        """
        Args:
            output_dir: Normal yasaklama PDF'lerinin kaydedileceği klasör
            correction_dir: Düzeltme/İptal/Kaldır içeren PDF'lerin klasörü
            tesseract_path: Tesseract OCR yolu (Windows için)
            poppler_path: Poppler yolu (Windows için)
        """
        self.output_dir = output_dir
        self.correction_dir = correction_dir
        self.poppler_path = poppler_path
        self.fuzzy_threshold = 80
        
        # Tesseract ayarı
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # Klasörleri oluştur
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.correction_dir, exist_ok=True)
        
        # İstatistikler
        self.stats = {
            "total_days_scanned": 0,
            "total_pdfs_found": 0,
            "yasaklama_pdfs": 0,
            "correction_pdfs": 0,
            "failed_downloads": 0,
            "no_page_days": 0
        }
        
        # Headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # Düzeltme/İptal/Kaldır pattern'leri (başlıkta aranacak)
        self.correction_patterns = [
            r'KALDIR',
            r'İPTAL',
            r'DÜZELT',
            r'DUZELT',
            r'KALDIRMA',
            r'İPTALİ',
            r'DÜZELTİLMESİ',
            r'DÜZELTİM',
        ]
        
        # Yasaklama pattern
        self.yasaklama_pattern = r'İ?HALE(LE)?R?E\s*KATILMAKTAN\s*YASAKLAMA(\s*KARARI)?'
        self.yasaklama_keywords = [
            "İHALELERE KATILMAKTAN YASAKLAMA",
            "İHALERE KATILMAKTAN YASAKLAMA",
            "İHALELERE KATILMAKTAN YASAKLAMA KARARI",
            "İHALERE KATILMAKTAN YASAKLAMA KARARI"
        ]

    def normalize_text(self, text: str) -> str:
        """Türkçe karakterleri normalize et"""
        return text.upper().replace('i', 'İ').replace('ı', 'I')

    def is_yasaklama(self, text: str) -> bool:
        """Metinde yasaklama ifadesi var mı kontrol et"""
        normalized = self.normalize_text(text)
        
        # Regex kontrolü
        if re.search(self.yasaklama_pattern, normalized, re.IGNORECASE):
            return True
        
        # Fuzzy matching
        for keyword in self.yasaklama_keywords:
            norm_keyword = self.normalize_text(keyword)
            score = fuzz.partial_ratio(norm_keyword, normalized)
            if score >= self.fuzzy_threshold:
                return True
        
        return False

    def is_correction(self, text: str) -> bool:
        """Metinde düzeltme/iptal/kaldır ifadesi var mı kontrol et"""
        normalized = self.normalize_text(text)
        
        for pattern in self.correction_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return True
        return False

    def check_pdf_text(self, pdf_url: str) -> Tuple[bool, bool, str]:
        """
        PDF'den normal metin extraction ile kontrol yap.
        Returns: (is_yasaklama, is_correction, title_text)
        """
        try:
            r = requests.get(pdf_url, headers=self.headers, timeout=30)
            pdf_file = io.BytesIO(r.content)
            reader = PdfReader(pdf_file)
            
            all_text = ""
            for page in reader.pages:
                all_text += (page.extract_text() or "") + "\n"
            
            # İlk 500 karakter başlık olarak kabul et
            title_text = all_text[:500] if all_text else ""
            
            is_yasaklama = self.is_yasaklama(all_text)
            is_correction = self.is_correction(title_text)
            
            return is_yasaklama, is_correction, title_text
            
        except Exception as e:
            print(f"    ✗ Text extraction hatası: {e}")
            return False, False, ""

    def check_pdf_ocr(self, pdf_url: str, crop_ratio: float = 0.25) -> Tuple[bool, bool, str]:
        """
        PDF'in ilk sayfasının üst kısmına OCR uygula.
        Returns: (is_yasaklama, is_correction, title_text)
        """
        try:
            r = requests.get(pdf_url, headers=self.headers, timeout=30)
            pdf_bytes = r.content
            
            images = convert_from_bytes(
                pdf_bytes,
                dpi=300,
                first_page=1,
                last_page=1,
                poppler_path=self.poppler_path
            )
            
            if not images:
                return False, False, ""
            
            first_page = images[0]
            width, height = first_page.size
            crop_height = int(height * crop_ratio)
            title_region = first_page.crop((0, 0, width, crop_height))
            
            title_text = pytesseract.image_to_string(title_region, lang='tur')
            
            is_yasaklama = self.is_yasaklama(title_text)
            is_correction = self.is_correction(title_text)
            
            return is_yasaklama, is_correction, title_text
            
        except Exception as e:
            print(f"    ✗ OCR hatası: {e}")
            return False, False, ""

    def download_pdf(self, pdf_url: str, save_path: str) -> bool:
        """PDF'i indir ve kaydet"""
        try:
            r = requests.get(pdf_url, headers=self.headers, timeout=60)
            if r.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(r.content)
                return True
            return False
        except Exception as e:
            print(f"    ✗ İndirme hatası: {e}")
            return False

    def scan_single_day(self, year: int, month: int, day: int) -> List[Dict]:
        """
        Tek bir günü tara ve yasaklama PDF'lerini bul.
        Returns: Her PDF için bilgi içeren dict listesi
        """
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
            
            # PDF linklerini topla
            pdf_links = []
            for link in links:
                href = link.get('href')
                if href and href.lower().endswith('.pdf'):
                    pdf_links.append(urljoin(url, href))
            
            if not pdf_links:
                return results
            
            print(f"  {len(pdf_links)} PDF bulundu, taranıyor...")
            
            for idx, pdf_url in enumerate(pdf_links, 1):
                # Önce normal text extraction
                is_yasaklama, is_correction, title = self.check_pdf_text(pdf_url)
                
                # Bulunamadıysa OCR dene
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
                    print(f"    [{idx}] ✓ {status} bulundu")
            
            return results
            
        except Exception as e:
            print(f"  ✗ Hata: {e}")
            return results

    def generate_date_range(self, 
                           start_date: datetime, 
                           end_date: datetime,
                           reverse: bool = True) -> List[datetime]:
        """
        Tarih aralığı oluştur.
        reverse=True: Yeniden eskiye (varsayılan)
        """
        dates = []
        current = start_date
        
        while current >= end_date:
            dates.append(current)
            current -= timedelta(days=1)
        
        if not reverse:
            dates.reverse()
        
        return dates

    def run_full_scan(self,
                      start_date: datetime = datetime(2025, 12, 12),
                      end_date: datetime = datetime(2022, 12, 1),
                      delay_between_days: float = 0.5) -> Dict:
        """
        Tam tarama çalıştır: start_date'den end_date'e kadar tüm günleri tara.
        PDF'leri indir ve sınıflandır.
        
        Returns: İstatistikler ve indirilen dosya listesi
        """
        print("=" * 70)
        print("YASAKLAMA PDF TARAMA VE İNDİRME")
        print(f"Tarih Aralığı: {start_date.strftime('%d.%m.%Y')} -> {end_date.strftime('%d.%m.%Y')}")
        print(f"Normal PDF Klasörü: {self.output_dir}")
        print(f"Düzeltme/İptal Klasörü: {self.correction_dir}")
        print("=" * 70)
        
        all_results = []
        dates = self.generate_date_range(start_date, end_date, reverse=True)
        total_days = len(dates)
        
        for day_idx, date in enumerate(dates, 1):
            print(f"\n[{day_idx}/{total_days}] {date.strftime('%d.%m.%Y')} taranıyor...")
            
            self.stats["total_days_scanned"] += 1
            
            day_results = self.scan_single_day(date.year, date.month, date.day)
            
            if not day_results:
                print("  - Yasaklama bulunamadı veya sayfa yok")
                continue
            
            # PDF'leri indir
            for result in day_results:
                pdf_url = result["url"]
                pdf_name = pdf_url.split('/')[-1]
                date_prefix = result["date"].replace('-', '')
                
                # Düzeltme/İptal mi normal mi?
                if result["is_correction"]:
                    save_dir = self.correction_dir
                    save_path = os.path.join(save_dir, f"{date_prefix}_{pdf_name}")
                    self.stats["correction_pdfs"] += 1
                else:
                    save_dir = self.output_dir
                    save_path = os.path.join(save_dir, f"{date_prefix}_{pdf_name}")
                    self.stats["yasaklama_pdfs"] += 1
                
                # İndir
                if self.download_pdf(pdf_url, save_path):
                    result["local_path"] = save_path
                    print(f"    ✓ İndirildi: {save_path}")
                else:
                    self.stats["failed_downloads"] += 1
                    print(f"    ✗ İndirme başarısız: {pdf_url}")
                
                self.stats["total_pdfs_found"] += 1
                all_results.append(result)
            
            # Rate limiting
            time.sleep(delay_between_days)
        
        # İstatistikleri yazdır
        print("\n" + "=" * 70)
        print("TARAMA TAMAMLANDI")
        print("=" * 70)
        print(f"Taranan gün sayısı: {self.stats['total_days_scanned']}")
        print(f"Bulunan toplam yasaklama PDF: {self.stats['total_pdfs_found']}")
        print(f"  • Normal yasaklama: {self.stats['yasaklama_pdfs']}")
        print(f"  • Düzeltme/İptal: {self.stats['correction_pdfs']}")
        print(f"  • İndirme hatası: {self.stats['failed_downloads']}")
        
        # Sonuçları JSON olarak kaydet
        results_file = os.path.join(self.output_dir, "scan_results.json")
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                "stats": self.stats,
                "results": all_results
            }, f, ensure_ascii=False, indent=2)
        print(f"\nSonuçlar kaydedildi: {results_file}")
        
        return {
            "stats": self.stats,
            "results": all_results
        }


class SmartPDFStitcher:
    """PDF'leri temizleyip birleştiren sınıf - Sayı/ID'leri gizler"""
    
    def __init__(self, input_path: str, output_path: str):
        self.input_path = input_path
        self.output_path = output_path
        self.gap_threshold = 30
        self.margin_padding = 3
        self.found_numbers = []

    def get_all_content_boxes(self, page) -> List[Dict]:
        """Metin, çizgi, kutu ve resimlerin koordinatlarını toplar."""
        content_boxes = []

        words = page.extract_words()
        for w in words:
            content_boxes.append({
                "top": w['top'], "bottom": w['bottom'],
                "x0": w['x0'], "x1": w['x1']
            })

        graphics = (page.lines or []) + (page.rects or [])
        for g in graphics:
            top = min(g['top'], g['bottom'])
            bottom = max(g['top'], g['bottom'])
            x0 = min(g['x0'], g['x1'])
            x1 = max(g['x0'], g['x1'])
            content_boxes.append({
                "top": top, "bottom": bottom,
                "x0": x0, "x1": x1
            })

        images = page.images or []
        for img in images:
            content_boxes.append({
                "top": img['top'], "bottom": img['bottom'],
                "x0": img['x0'], "x1": img['x1']
            })

        return content_boxes

    def analyze_page_content(self, plumber_page, y_min=0, y_max=None) -> List[Dict]:
        """Sayfadaki güvenli (dolu) alanları analiz eder."""
        if y_max is None:
            y_max = plumber_page.height

        boxes = self.get_all_content_boxes(plumber_page)
        
        filtered_boxes = [
            b for b in boxes 
            if b['top'] >= y_min and b['bottom'] <= y_max
        ]
        
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
                    "left": crop_left,
                    "right": crop_right
                })
                current_seg_start = next_top - self.margin_padding
                current_seg_end = next_bottom
            else:
                current_seg_end = max(current_seg_end, next_bottom)
        
        final_bottom = min(y_max, current_seg_end + self.margin_padding)
        
        final_segments.append({
            "top": current_seg_start,
            "bottom": final_bottom,
            "left": crop_left,
            "right": crop_right
        })
        
        return final_segments

    def process(self) -> Tuple[str, List[str]]:
        """
        PDF'i işle ve optimize edilmiş versiyonu kaydet.
        Returns: (output_path, found_numbers)
        """
        print(f"🧹 [STITCHER] PDF işleniyor: {self.input_path}")
        
        number_pattern = re.compile(r'^\d[\w\-/]*')
        split_points = []
        
        with pdfplumber.open(self.input_path) as plumber_pdf:
            total_pages = len(plumber_pdf.pages)
            
            split_points.append({
                'page_index': 0, 
                'cut_before': 0.0, 
                'cut_after': 0.0, 
                'text': 'START'
            })
            
            for i, page in enumerate(plumber_pdf.pages):
                words = page.extract_words()
                words.sort(key=lambda x: (x['top'], x['x0']))
                
                for w in words:
                    if number_pattern.match(w['text']):
                        self.found_numbers.append(w['text'])
                        split_points.append({
                            'page_index': i,
                            'cut_before': w['top'], 
                            'cut_after': w['bottom'],
                            'text': w['text']
                        })

            last_page_height = plumber_pdf.pages[-1].height
            split_points.append({
                'page_index': total_pages - 1, 
                'cut_before': last_page_height, 
                'cut_after': last_page_height, 
                'text': 'END'
            })

        print(f"📄 {len(self.found_numbers)} adet ID bulundu")

        document_groups = []
        
        with pdfplumber.open(self.input_path) as plumber_pdf:
            for idx in range(len(split_points) - 1):
                start_pt = split_points[idx]
                end_pt = split_points[idx+1]
                
                current_group = []
                start_page = start_pt['page_index']
                end_page = end_pt['page_index']
                
                for p_idx in range(start_page, end_page + 1):
                    page = plumber_pdf.pages[p_idx]
                    
                    y_min = 0
                    y_max = page.height
                    
                    if p_idx == start_page:
                        y_min = start_pt['cut_after']
                    
                    if p_idx == end_page:
                        y_max = end_pt['cut_before']
                        
                    if p_idx == start_page and p_idx == end_page:
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

        for g_idx, group in enumerate(document_groups):
            total_height = 0
            max_width = 0

            for page_data in group:
                for seg in page_data["segments"]:
                    h = seg["bottom"] - seg["top"]
                    w = seg["right"] - seg["left"]
                    if h > 1:
                        total_height += h
                        if w > max_width:
                            max_width = w
            
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

                    plumber_top = seg["top"]
                    pypdf_upper = orig_h - plumber_top
                    pypdf_lower = orig_h - seg["bottom"]
                    
                    source_page.cropbox.lower_left = (float(seg["left"]), float(pypdf_lower))
                    source_page.cropbox.upper_right = (float(seg["right"]), float(pypdf_upper))
                    
                    current_y -= seg_h
                    
                    ty = current_y - pypdf_lower
                    tx = 10 - float(seg["left"])

                    new_page.merge_transformed_page(
                        source_page,
                        Transformation().translate(tx=tx, ty=ty)
                    )

            writer.add_page(new_page)

        with open(self.output_path, "wb") as f:
            writer.write(f)
        
        print(f"✅ [STITCHER] Optimize edilmiş PDF: {self.output_path}")
        return self.output_path, self.found_numbers


class BatchPDFProcessor:
    """
    İndirilen tüm PDF'leri SmartPDFStitcher ile işleyen sınıf.
    """
    
    def __init__(self, 
                 input_dir: str,
                 output_dir: str = None):
        """
        Args:
            input_dir: İşlenecek PDF'lerin bulunduğu klasör
            output_dir: İşlenmiş PDF'lerin kaydedileceği klasör (None ise input_dir/processed)
        """
        self.input_dir = input_dir
        self.output_dir = output_dir or os.path.join(input_dir, "processed")
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.results = []

    def process_all(self) -> List[Dict]:
        """
        Klasördeki tüm PDF'leri işle.
        Returns: Her PDF için işlem sonucu listesi
        """
        pdf_files = [f for f in os.listdir(self.input_dir) if f.lower().endswith('.pdf')]
        
        print(f"\n{'=' * 70}")
        print(f"BATCH PDF İŞLEME")
        print(f"Kaynak: {self.input_dir}")
        print(f"Hedef: {self.output_dir}")
        print(f"Toplam PDF: {len(pdf_files)}")
        print(f"{'=' * 70}\n")
        
        for idx, pdf_file in enumerate(pdf_files, 1):
            print(f"\n[{idx}/{len(pdf_files)}] İşleniyor: {pdf_file}")
            
            input_path = os.path.join(self.input_dir, pdf_file)
            output_path = os.path.join(self.output_dir, f"processed_{pdf_file}")
            
            try:
                stitcher = SmartPDFStitcher(input_path, output_path)
                result_path, found_ids = stitcher.process()
                
                self.results.append({
                    "original_file": pdf_file,
                    "processed_file": os.path.basename(result_path),
                    "found_ids": found_ids,
                    "id_count": len(found_ids),
                    "status": "success"
                })
                
            except Exception as e:
                print(f"  ✗ Hata: {e}")
                self.results.append({
                    "original_file": pdf_file,
                    "processed_file": None,
                    "found_ids": [],
                    "id_count": 0,
                    "status": f"error: {str(e)}"
                })
        
        # Sonuçları JSON olarak kaydet
        results_file = os.path.join(self.output_dir, "processing_results.json")
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        
        # Özet
        success_count = sum(1 for r in self.results if r["status"] == "success")
        total_ids = sum(r["id_count"] for r in self.results)
        
        print(f"\n{'=' * 70}")
        print(f"İŞLEM TAMAMLANDI")
        print(f"{'=' * 70}")
        print(f"Başarılı: {success_count}/{len(pdf_files)}")
        print(f"Toplam bulunan ID: {total_ids}")
        print(f"Sonuçlar: {results_file}")
        
        return self.results


def main():
    """
    Ana çalıştırma fonksiyonu.
    1. PDF'leri tara ve indir (12 Aralık 2025 -> 1 Aralık 2022)
    2. İndirilen PDF'leri SmartPDFStitcher ile işle
    """
    
    # =============== AYARLAR ===============
    # Windows için path'leri ayarlayın
    # TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    # POPPLER_PATH = r"C:\poppler-24.08.0\Library\bin"
    
    TESSERACT_PATH = None
    POPPLER_PATH = None

    # Çıktı klasörleri
    OUTPUT_DIR = "deneysel"
    CORRECTION_DIR = "deneyselduz"
    
    # Tarih aralığı
    START_DATE = datetime(2023, 12, 1)  # Başlangıç (en yeni)
    END_DATE = datetime(2022, 12, 1)      # Bitiş (en eski)
    
    # =============== ADIM 1: TARAMA VE İNDİRME ===============
    print("\n" + "=" * 70)
    print("ADIM 1: PDF TARAMA VE İNDİRME")
    print("=" * 70)
    
    scraper = YasaklamaScraper(
        output_dir=OUTPUT_DIR,
        correction_dir=CORRECTION_DIR,
        tesseract_path=TESSERACT_PATH,
        poppler_path=POPPLER_PATH
    )
    
    scan_results = scraper.run_full_scan(
        start_date=START_DATE,
        end_date=END_DATE,
        delay_between_days=0.5  # Her gün arası bekleme (saniye)
    )
    
    # =============== ADIM 2: PDF İŞLEME (STITCHER) ===============
    print("\n" + "=" * 70)
    print("ADIM 2: PDF'LERİ İŞLEME (STITCHER)")
    print("=" * 70)
    
    # Normal yasaklama PDF'lerini işle
    if os.path.exists(OUTPUT_DIR) and os.listdir(OUTPUT_DIR):
        processor = BatchPDFProcessor(
            input_dir=OUTPUT_DIR,
            output_dir=os.path.join(OUTPUT_DIR, "processed")
        )
        processing_results = processor.process_all()
    else:
        print("İşlenecek normal yasaklama PDF'i bulunamadı.")
    
    # Düzeltme/İptal PDF'lerini işle (opsiyonel)
    if os.path.exists(CORRECTION_DIR) and os.listdir(CORRECTION_DIR):
        correction_processor = BatchPDFProcessor(
            input_dir=CORRECTION_DIR,
            output_dir=os.path.join(CORRECTION_DIR, "processed")
        )
        correction_results = correction_processor.process_all()
    else:
        print("İşlenecek düzeltme/iptal PDF'i bulunamadı.")
    
    print("\n" + "=" * 70)
    print("TÜM İŞLEMLER TAMAMLANDI!")
    print("=" * 70)


if __name__ == "__main__":
    main()
