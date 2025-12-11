"""
KKB Hackathon - Firma Raporu Oluşturma Sistemi
Ana uygulama dosyası - Agentic AI ile otomatik firma raporu üretimi

Kullanım:
    python app.py
    
    veya
    
    from app import create_company_report
    create_company_report("Turkcell", "2024-01-01", "2024-12-31")
"""

from datetime import datetime
from typing import Optional

from config import USE_MOCK_DATA, REPORT_CONFIG
from data_fetchers import get_all_company_data
from llm_service import llm_service
from pdf_generator import pdf_generator


def create_company_report(
    firma_adi: str,
    baslangic_tarihi: str,
    bitis_tarihi: str,
    haber_json_path: Optional[str] = None,
    output_pdf: Optional[str] = None,
    generate_html_preview: bool = False
) -> str:
    """
    Firma raporu oluşturma ana fonksiyonu
    
    Args:
        firma_adi: Şirket adı (örn: "Turkcell")
        baslangic_tarihi: Başlangıç tarihi (YYYY-MM-DD formatında)
        bitis_tarihi: Bitiş tarihi (YYYY-MM-DD formatında)
        haber_json_path: Haber JSON dosya yolu (opsiyonel)
        output_pdf: Çıktı PDF dosya adı (opsiyonel)
        generate_html_preview: HTML önizleme oluştur (debug için)
    
    Returns:
        Oluşturulan PDF dosya yolu
    
    Example:
        >>> pdf_path = create_company_report(
        ...     firma_adi="Turkcell",
        ...     baslangic_tarihi="2024-01-01",
        ...     bitis_tarihi="2024-12-31"
        ... )
        >>> print(f"Rapor oluşturuldu: {pdf_path}")
    """
    
    # Banner
    print("\n" + "="*70)
    print("🚀 KKB HACKATHON - FİRMA RAPORU OLUŞTURMA SİSTEMİ")
    print("="*70 + "\n")
    
    # Tarihleri parse et
    baslangic = datetime.strptime(baslangic_tarihi, "%Y-%m-%d").date()
    bitis = datetime.strptime(bitis_tarihi, "%Y-%m-%d").date()
    
    # Başlangıç bilgileri
    print(f"📊 Firma: {firma_adi}")
    print(f"📅 Dönem: {baslangic.strftime('%d.%m.%Y')} - {bitis.strftime('%d.%m.%Y')}")
    print(f"💾 Mock Data Modu: {'AÇIK ✓' if USE_MOCK_DATA else 'KAPALI ✗'}")
    print("\n" + "-"*70 + "\n")
    
    try:
        # Adım 1-3: Tüm verileri topla
        all_data = get_all_company_data(
            firma_adi=firma_adi,
            baslangic=baslangic,
            bitis=bitis,
            haber_json_path=haber_json_path
        )
        
        # Adım 4: LLM ile yönetici özeti oluştur
        print("4️⃣ Yönetici özeti oluşturuluyor (LLM)...")
        executive_summary = llm_service.generate_executive_summary(
            firma_adi=firma_adi,
            sicil_data=all_data['sicil'],
            yasakli_data=all_data['yasakli'],
            haber_data=all_data['haberler']
        )
        print("   ✓ Özet hazırlandı\n")
        
        # HTML önizleme (opsiyonel)
        if generate_html_preview:
            print("🔍 HTML önizleme oluşturuluyor...")
            pdf_generator.preview_html(
                firma_adi=firma_adi,
                baslangic=baslangic,
                bitis=bitis,
                sicil_data=all_data['sicil'],
                yasakli_data=all_data['yasakli'],
                haber_data=all_data['haberler'],
                executive_summary=executive_summary
            )
        
        # Adım 5: PDF rapor oluştur
        print("5️⃣ PDF rapor oluşturuluyor...")
        pdf_path = pdf_generator.generate_report(
            firma_adi=firma_adi,
            baslangic=baslangic,
            bitis=bitis,
            sicil_data=all_data['sicil'],
            yasakli_data=all_data['yasakli'],
            haber_data=all_data['haberler'],
            executive_summary=executive_summary,
            output_filename=output_pdf
        )
        
        # Başarı mesajı
        print("\n" + "="*70)
        print(f"✅ RAPOR BAŞARIYLA OLUŞTURULDU")
        print(f"📄 Dosya: {pdf_path}")
        print("="*70 + "\n")
        
        return pdf_path
        
    except Exception as e:
        print("\n" + "="*70)
        print(f"❌ HATA: Rapor oluşturulurken bir hata oluştu")
        print(f"Hata detayı: {str(e)}")
        print("="*70 + "\n")
        raise


def batch_create_reports(companies: list, start_date: str, end_date: str) -> list:
    """
    Birden fazla firma için toplu rapor oluşturur
    
    Args:
        companies: Firma adları listesi
        start_date: Başlangıç tarihi (YYYY-MM-DD)
        end_date: Bitiş tarihi (YYYY-MM-DD)
    
    Returns:
        Oluşturulan PDF dosya yollarının listesi
    
    Example:
        >>> companies = ["Turkcell", "Türk Telekom", "Vodafone"]
        >>> reports = batch_create_reports(companies, "2024-01-01", "2024-12-31")
    """
    print("\n" + "="*70)
    print(f"📦 TOPLU RAPOR OLUŞTURMA - {len(companies)} Firma")
    print("="*70 + "\n")
    
    results = []
    for i, company in enumerate(companies, 1):
        print(f"\n[{i}/{len(companies)}] {company} için rapor oluşturuluyor...\n")
        try:
            pdf_path = create_company_report(
                firma_adi=company,
                baslangic_tarihi=start_date,
                bitis_tarihi=end_date
            )
            results.append({
                'company': company,
                'status': 'success',
                'pdf_path': pdf_path
            })
        except Exception as e:
            print(f"❌ {company} için rapor oluşturulamadı: {e}\n")
            results.append({
                'company': company,
                'status': 'failed',
                'error': str(e)
            })
    
    # Özet
    print("\n" + "="*70)
    print("📊 TOPLU RAPOR ÖZET")
    print("="*70)
    success_count = sum(1 for r in results if r['status'] == 'success')
    print(f"✅ Başarılı: {success_count}/{len(companies)}")
    print(f"❌ Başarısız: {len(companies) - success_count}/{len(companies)}")
    print("="*70 + "\n")
    
    return results


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Ana fonksiyon - CLI kullanımı için"""
    import sys
    
    if len(sys.argv) < 4:
        print("""
Kullanım:
    python app.py <firma_adi> <baslangic_tarihi> <bitis_tarihi> [haber_json]

Örnek:
    python app.py "Turkcell" "2024-01-01" "2024-12-31"
    python app.py "Turkcell" "2024-01-01" "2024-12-31" "haberler.json"
        """)
        sys.exit(1)
    
    firma_adi = sys.argv[1]
    baslangic_tarihi = sys.argv[2]
    bitis_tarihi = sys.argv[3]
    haber_json = sys.argv[4] if len(sys.argv) > 4 else None
    
    pdf_path = create_company_report(
        firma_adi=firma_adi,
        baslangic_tarihi=baslangic_tarihi,
        bitis_tarihi=bitis_tarihi,
        haber_json_path=haber_json
    )
    
    print(f"🎉 İşlem tamamlandı! PDF: {pdf_path}")


if __name__ == "__main__":
    # Demo - Tek firma raporu
    pdf_file = create_company_report(
        firma_adi="Turkcell",
        baslangic_tarihi="2024-01-01",
        bitis_tarihi="2024-12-31",
        generate_html_preview=True  # HTML önizleme de oluştur
    )
    
    print(f"🎉 Demo tamamlandı! PDF dosyası: {pdf_file}")
