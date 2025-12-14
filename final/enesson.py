import os
import cv2
import time
import json
import re
import numpy as np
from pathlib import Path
import fitz  # PyMuPDF
from paddleocr import PaddleOCRVL
import paddle
import traceback
from datetime import datetime

# --- AYARLAR ---
INPUT_FOLDER = Path("./deneysel")
OUTPUT_FOLDER = Path("./output_ihale")
TEMP_IMG_FOLDER = OUTPUT_FOLDER / "temp_processed_images"
LOG_FILE = OUTPUT_FOLDER / "processing_log.txt"
OOM_ERRORS_FILE = OUTPUT_FOLDER / "oom_errors.json"

# ====== TARİH ARALIĞI AYARLARI ======
START_DATE = "20251016"  # Başlangıç tarihi (YYYYMMDD formatında) - Yakın tarih
END_DATE = "20220101"    # Bitiş tarihi (YYYYMMDD formatında) - Geçmiş tarih
# ====================================

# VRAM İÇİN GÜVENLİ SINIR (Başlangıç değeri)
BASE_TARGET_MAX_DIMENSION = 1600

# Adaptif DPI azaltma oranları (3 deneme)
DPI_REDUCTION_ATTEMPTS = [
    1.0,   # İlk deneme: Orijinal boyut (100%)
    0.9,   # 2. deneme: %10 azaltma (90%)
    0.8,   # 3. deneme: %20 azaltma (80%)
    0.6    # 4. deneme: %40 azaltma (60%)
]

# OOM hataları için liste
oom_failed_pages = []

# --- TARİH ÇIKARTMA FONKSİYONU ---
def extract_date_from_filename(filename):
    """
    Dosya adından tarih çıkart (stitched_20250503 -> 20250503)
    Tarih bulunamazsa None döndür
    """
    # YYYYMMDD formatını ara (8 haneli sayı)
    match = re.search(r'(\d{8})', str(filename))
    if match:
        return match.group(1)
    # YYYY-MM-DD formatını ara
    match = re.search(r'(\d{4}[-_]\d{2}[-_]\d{2})', str(filename))
    if match:
        return match.group(1).replace('-', '').replace('_', '')
    # Tarih bulunamazsa None döndür
    return None

def is_in_date_range(date_str, start_date, end_date):
    """
    Tarihin belirtilen aralıkta olup olmadığını kontrol et
    start_date: yakın tarih (örn: 20221201)
    end_date: geçmiş tarih (örn: 20220101)
    """
    if date_str is None:
        return False
    
    try:
        # String tarihleri integer'a çevir (karşılaştırma için)
        date_int = int(date_str)
        start_int = int(start_date)
        end_int = int(end_date)
        
        # Aralık kontrolü (start >= date >= end, çünkü tersten gidiyoruz)
        return end_int <= date_int <= start_int
    except:
        return False

# --- LOG YAZMA FONKSİYONU ---
def log_message(message, print_console=True):
    """Hem konsola hem de log dosyasına yaz"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_text = f"[{timestamp}] {message}"
    
    if print_console:
        print(log_text)
    
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_text + "\n")

# --- 1. ADIM: AKILLI PDF DÖNÜŞTÜRME (TEK SAYFA - DPI PARAMETRESİ İLE) ---
def convert_pdf_page_to_image(pdf_path, page_num, output_folder, target_max_dim=BASE_TARGET_MAX_DIMENSION):
    """Tek bir PDF sayfasını görüntüye çevirir"""
    try:
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            doc.close()
            return None, None
            
        page = doc[page_num]
        
        # Sayfanın orijinal boyutlarını al
        rect = page.rect
        width_pt, height_pt = rect.width, rect.height
        long_side_pt = max(width_pt, height_pt)
        
        # Zoom hesapla
        if long_side_pt > 0:
            zoom_factor = target_max_dim / long_side_pt
        else:
            zoom_factor = 2.0
        
        # Tahmini görüntü boyutunu hesapla
        estimated_width = int(width_pt * zoom_factor)
        estimated_height = int(height_pt * zoom_factor)
        estimated_total_pixels = estimated_width * estimated_height
        
        # TOPLAM PİKSEL SINIRI: 2,100,000 (güvenli eşik)
        MAX_PIXELS = 2_100_000
        
        if estimated_total_pixels > MAX_PIXELS:
            zoom_factor = zoom_factor * 0.9
            
        # Aşırı büyütme koruması
        if zoom_factor > 4.0:
            zoom_factor = 4.0
            
        # Render
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
# --- 2. ADIM: GÖRÜNTÜ İYİLEŞTİRME ---
def enhance_image_for_ocr(image_path):
    """Görüntü kalitesini artır (debug kaydetmeden)"""
    try:
        img = cv2.imread(str(image_path))
        if img is None: 
            return str(image_path)
        
        # Gri tonlama
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Keskinleştirme
        kernel = np.array([[0, -0.5, 0],
                           [-0.5, 3, -0.5],
                           [0, -0.5, 0]])
        sharpened = cv2.filter2D(gray, -1, kernel)
        
        # CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(sharpened)
        
        # Renkli formata dön
        final_img = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        
        # Üzerine yaz (geçici dosyaya)
        cv2.imwrite(str(image_path), final_img)
        
        return str(image_path)
        
    except Exception as e:
        log_message(f"❌ Görüntü iyileştirme hatası: {e}")
        return str(image_path)

def is_oom_error(error):
    """Hata mesajının OOM (Out of Memory) hatası olup olmadığını kontrol et"""
    error_str = str(error).lower()
    oom_keywords = [
        "out of memory",
        "cuda out of memory",
        "resourceexhaustederror",
        "cannot allocate",
        "memory error"
    ]
    return any(keyword in error_str for keyword in oom_keywords)

def process_single_page_with_retry(pdf_path, page_num, pipeline, pdf_stem):
    """
    Tek bir sayfayı işle - OOM hatası durumunda DPI'ı azaltarak tekrar dene
    """
    
    for attempt_idx, dpi_scale in enumerate(DPI_REDUCTION_ATTEMPTS):
        # DPI'a göre hedef boyutu hesapla
        current_target_dim = int(BASE_TARGET_MAX_DIMENSION * dpi_scale)
        
        if attempt_idx > 0:
            log_message(f"   🔄 Yeniden deneniyor ({attempt_idx+1}/{len(DPI_REDUCTION_ATTEMPTS)}): "
                       f"DPI %{int(dpi_scale*100)} ({current_target_dim}px)")
        
        try:
            # CUDA cache temizle (her denemeden önce)
            paddle.device.cuda.empty_cache()
            time.sleep(1)  # GPU'nun temizlenmesi için kısa bekleme
            
            # Geçici klasör oluştur
            TEMP_IMG_FOLDER.mkdir(parents=True, exist_ok=True)
            
            # 1. PDF sayfasını görüntüye çevir (azaltılmış DPI ile)
            result = convert_pdf_page_to_image(pdf_path, page_num, TEMP_IMG_FOLDER, target_max_dim=current_target_dim)
            if result[0] is None:
                log_message(f"⚠️ {pdf_stem} - Sayfa {page_num+1}: Görüntü oluşturulamadı")
                return False
            
            img_path, img_size = result
            
            if attempt_idx == 0:
                log_message(f"   📐 Görüntü boyutu: {img_size[0]}x{img_size[1]}px")
            
            # 2. Görüntüyü iyileştir (debug kaydetmeden)
            enhanced_img = enhance_image_for_ocr(img_path)
            
            # 3. OCR işle
            prediction_args = {"format_block_content": True, "layout_nms": True}
            output = pipeline.predict(input=enhanced_img, **prediction_args)
            
            # 4. SADECE HTML KAYDET (Görselleri KAYDETME)
            if output and len(output) > 0:
                page_markdowns = [res.markdown for res in output]
                
                if page_markdowns:
                    final_text = pipeline.concatenate_markdown_pages(page_markdowns)
                    
                    # Sadece HTML dosyasını kaydet
                    output_path = OUTPUT_FOLDER / f"{pdf_stem}_sayfa_{page_num+1}.html"
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(final_text)
                    
                    success_msg = f"✅ {pdf_stem} - Sayfa {page_num+1}: Başarıyla işlendi"
                    if attempt_idx > 0:
                        success_msg += f" (DPI: %{int(dpi_scale*100)})"
                    log_message(success_msg)
            
            # 5. Geçici dosyayı SİL
            if os.path.exists(img_path):
                os.remove(img_path)
            
            # BAŞARILI - Döngüden çık
            return True
            
        except RuntimeError as e:
            # OOM hatası mı kontrol et
            if is_oom_error(e):
                log_message(f"   💥 OOM Hatası (Deneme {attempt_idx+1}/{len(DPI_REDUCTION_ATTEMPTS)}): "
                           f"{pdf_stem} - Sayfa {page_num+1}")
                
                # Geçici dosyayı temizle
                try:
                    temp_file = TEMP_IMG_FOLDER / f"temp_page_{page_num+1}.png"
                    if temp_file.exists():
                        os.remove(temp_file)
                except:
                    pass
                
                # CUDA belleğini agresif temizle
                paddle.device.cuda.empty_cache()
                time.sleep(2)
                
                # Eğer son deneme değilse, bir sonraki denemeye geç
                if attempt_idx < len(DPI_REDUCTION_ATTEMPTS) - 1:
                    continue
                else:
                    # TÜM DENEMEler BAŞARISIZ - JSON'a kaydet
                    log_message(f"   ❌ {pdf_stem} - Sayfa {page_num+1}: TÜM DENEMELER BAŞARISIZ (OOM)")
                    oom_failed_pages.append({
                        "pdf_name": pdf_path.name,
                        "pdf_stem": pdf_stem,
                        "page_number": page_num + 1,
                        "timestamp": datetime.now().isoformat(),
                        "error_type": "OOM (Out of Memory)",
                        "attempts": len(DPI_REDUCTION_ATTEMPTS)
                    })
                    return False
            else:
                # OOM dışı runtime hatası
                log_message(f"❌ Runtime Hatası - {pdf_stem} - Sayfa {page_num+1}: {str(e)[:200]}")
                return False
                
        except Exception as e:
            log_message(f"❌ Beklenmeyen Hata - {pdf_stem} - Sayfa {page_num+1}: {str(e)[:200]}")
            if attempt_idx == 0:  # Sadece ilk denemede traceback göster
                traceback.print_exc()
            return False
    
    # Tüm denemeler tükendi
    return False

def save_oom_errors_to_json():
    """OOM hatalarını JSON dosyasına kaydet"""
    if oom_failed_pages:
        with open(OOM_ERRORS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "total_oom_errors": len(oom_failed_pages),
                "generated_at": datetime.now().isoformat(),
                "failed_pages": oom_failed_pages
            }, f, indent=2, ensure_ascii=False)
        log_message(f"📝 OOM hataları kaydedildi: {OOM_ERRORS_FILE}")

def process_all_pdfs():
    """Inputs klasöründeki belirtilen tarih aralığındaki PDF'leri işle"""
    
    # Klasörleri kontrol et
    if not INPUT_FOLDER.exists():
        log_message(f"❌ Input klasörü bulunamadı: {INPUT_FOLDER}")
        return
    
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    
    # Tüm PDF'leri bul
    all_pdf_files = list(INPUT_FOLDER.glob("*.pdf"))
    
    # Tarih aralığına uygun PDF'leri filtrele
    filtered_pdfs = []
    for pdf in all_pdf_files:
        date_str = extract_date_from_filename(pdf.stem)
        if date_str and is_in_date_range(date_str, START_DATE, END_DATE):
            filtered_pdfs.append(pdf)
    
    # Tarihe göre TERS sırala (yakından geçmişe)
    pdf_files_sorted = sorted(filtered_pdfs, key=lambda x: extract_date_from_filename(x.stem), reverse=True)
    
    total_pdfs = len(pdf_files_sorted)
    
    if total_pdfs == 0:
        log_message(f"⚠️ {INPUT_FOLDER} klasöründe {START_DATE} - {END_DATE} aralığında PDF bulunamadı!")
        log_message(f"📊 Toplam {len(all_pdf_files)} PDF bulundu, ancak hiçbiri tarih aralığına uymuyor.")
        return
    
    log_message(f"📅 Tarih Aralığı: {START_DATE} (başlangıç) → {END_DATE} (bitiş)")
    log_message(f"📚 Tarih aralığında {total_pdfs} PDF dosyası bulundu (toplam: {len(all_pdf_files)})")
    log_message(f"🎯 Başlangıç DPI: {BASE_TARGET_MAX_DIMENSION}px")
    log_message(f"🔄 Adaptif azaltma: {[f'%{int(x*100)}' for x in DPI_REDUCTION_ATTEMPTS]}")
    log_message(f"📅 Sıralama: Yakın tarihten → Geçmiş tarihe")
    
    # İlk 5 dosyayı göster (sıralama kontrolü için)
    log_message("\n📋 İlk işlenecek 5 dosya:")
    for i, pdf in enumerate(pdf_files_sorted[:5], 1):
        date_extracted = extract_date_from_filename(pdf.stem)
        log_message(f"   {i}. {pdf.name} (Tarih: {date_extracted})")
    
    if total_pdfs > 5:
        log_message("   ...")
        log_message(f"📋 Son işlenecek dosya:")
        last_pdf = pdf_files_sorted[-1]
        date_extracted = extract_date_from_filename(last_pdf.stem)
        log_message(f"   {total_pdfs}. {last_pdf.name} (Tarih: {date_extracted})")
    
    log_message("=" * 60)
    
    # PaddleOCR VL başlat
    log_message("🚀 PaddleOCR VL motoru başlatılıyor...")
    try:
        pipeline = PaddleOCRVL(
            use_layout_detection=True,
            layout_threshold=0.5,
            use_doc_orientation_classify=True,
            use_chart_recognition=True
        )
        log_message("✅ Model başarıyla yüklendi")
    except Exception as e:
        log_message(f"❌ Model yükleme hatası: {e}")
        return
    
    # İstatistikler
    total_pages_processed = 0
    total_pages_failed = 0
    start_time = time.time()
    
    # Her PDF'i işle (tarih sırasına göre)
    for pdf_idx, pdf_path in enumerate(pdf_files_sorted, 1):
        pdf_stem = pdf_path.stem  # Dosya adı (uzantısız)
        date_str = extract_date_from_filename(pdf_stem)
        
        log_message("")
        log_message(f"📄 [{pdf_idx}/{total_pdfs}] İşleniyor: {pdf_path.name} (Tarih: {date_str})")
        
        try:
            # PDF'teki sayfa sayısını al
            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            doc.close()
            
            log_message(f"   📑 Toplam sayfa: {num_pages}")
            
            # Her sayfayı ayrı ayrı işle (retry mekanizması ile)
            for page_num in range(num_pages):
                success = process_single_page_with_retry(pdf_path, page_num, pipeline, pdf_stem)
                
                if success:
                    total_pages_processed += 1
                else:
                    total_pages_failed += 1
                
                # Her 5 sayfada bir ilerleme göster
                if (page_num + 1) % 5 == 0:
                    log_message(f"   ⏳ {page_num + 1}/{num_pages} sayfa tamamlandı...")
        
        except Exception as e:
            log_message(f"❌ PDF açma hatası ({pdf_path.name}): {e}")
            continue
        
        # Her PDF sonrası CUDA temizle
        paddle.device.cuda.empty_cache()
    
    # Özet istatistikler
    end_time = time.time()
    total_time = end_time - start_time
    
    log_message("")
    log_message("=" * 60)
    log_message("📊 İŞLEM TAMAMLANDI!")
    log_message(f"📅 İşlenen Tarih Aralığı: {START_DATE} → {END_DATE}")
    log_message(f"📚 İşlenen PDF Sayısı: {total_pdfs}")
    log_message(f"✅ Başarılı Sayfalar: {total_pages_processed}")
    log_message(f"❌ Hatalı Sayfalar: {total_pages_failed}")
    log_message(f"💥 OOM Hataları: {len(oom_failed_pages)}")
    log_message(f"⏱️  Toplam Süre: {total_time/60:.2f} dakika ({total_time:.2f} saniye)")
    if total_pages_processed > 0:
        log_message(f"⚡ Ortalama Hız: {total_time/total_pages_processed:.2f} saniye/sayfa")
    log_message(f"📁 HTML Çıktılar: {OUTPUT_FOLDER}")
    log_message("=" * 60)
    
    # OOM hatalarını JSON'a kaydet
    save_oom_errors_to_json()
    
    # Geçici klasörü temizle
    if TEMP_IMG_FOLDER.exists():
        import shutil
        try:
            shutil.rmtree(TEMP_IMG_FOLDER)
            log_message("🧹 Geçici dosyalar temizlendi")
        except:
            pass

# --- ANA PROGRAM ---
if __name__ == "__main__":
    log_message("🎬 Toplu PDF İşleme Başlatılıyor...")
    log_message(f"📂 Input Klasörü: {INPUT_FOLDER}")
    log_message(f"📁 Output Klasörü: {OUTPUT_FOLDER}")
    log_message(f"🎯 Hedef Boyut: {BASE_TARGET_MAX_DIMENSION}px (Adaptif)")
    log_message(f"📅 Tarih Aralığı: {START_DATE} → {END_DATE}")
    log_message("=" * 60)
    
    process_all_pdfs()