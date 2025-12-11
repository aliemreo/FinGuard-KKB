"""
KKB Hackathon - PDF Generator Service
WeasyPrint ve Jinja2 kullanarak PDF rapor oluşturma
"""

import os
from datetime import datetime, date
from typing import List, Dict
from jinja2 import Template, Environment, FileSystemLoader
from weasyprint import HTML

from config import TEMPLATE_DIR, STATIC_DIR, OUTPUT_DIR, REPORT_CONFIG


class PDFGenerator:
    """PDF rapor oluşturma servisi"""
    
    def __init__(self):
        # Jinja2 environment setup
        self.env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        self.template = self.env.get_template('report_template.html')
        
        # Output directory oluştur
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    def generate_report(
        self,
        firma_adi: str,
        baslangic: date,
        bitis: date,
        sicil_data: List[Dict],
        yasakli_data: List[Dict],
        haber_data: List[Dict],
        executive_summary: str,
        output_filename: str = None
    ) -> str:
        """
        PDF rapor oluşturur
        
        Args:
            firma_adi: Şirket adı
            baslangic: Başlangıç tarihi
            bitis: Bitiş tarihi
            sicil_data: Sicil verileri
            yasakli_data: Yasaklı verileri
            haber_data: Haber verileri
            executive_summary: LLM özeti
            output_filename: Çıktı dosya adı (opsiyonel)
        
        Returns:
            Oluşturulan PDF dosya yolu
        """
        print(f"📄 PDF rapor oluşturuluyor...")
        
        # Output filename
        if not output_filename:
            safe_name = firma_adi.lower().replace(' ', '_').replace('ş', 's').replace('ı', 'i')
            output_filename = f"{safe_name}_raporu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # HTML içeriği oluştur
        html_content = self._render_html(
            firma_adi=firma_adi,
            baslangic=baslangic,
            bitis=bitis,
            sicil_data=sicil_data,
            yasakli_data=yasakli_data,
            haber_data=haber_data,
            executive_summary=executive_summary
        )
        
        # PDF'e dönüştür
        try:
            HTML(string=html_content, base_url=os.path.abspath(STATIC_DIR)).write_pdf(output_path)
            print(f"✅ PDF başarıyla oluşturuldu: {output_path}")
            return output_path
        except Exception as e:
            print(f"❌ PDF oluşturma hatası: {e}")
            raise
    
    def _render_html(
        self,
        firma_adi: str,
        baslangic: date,
        bitis: date,
        sicil_data: List[Dict],
        yasakli_data: List[Dict],
        haber_data: List[Dict],
        executive_summary: str
    ) -> str:
        """HTML template'ini render eder"""
        
        # CSS dosya yolunu hazırla
        css_path = os.path.abspath(os.path.join(STATIC_DIR, 'style.css'))
        
        # Template context
        context = {
            'firma_adi': firma_adi,
            'rapor_tarihi': datetime.now().strftime("%d.%m.%Y %H:%M"),
            'baslangic_tarihi': baslangic.strftime("%d.%m.%Y"),
            'bitis_tarihi': bitis.strftime("%d.%m.%Y"),
            'sicil_data': sicil_data,
            'yasakli_data': yasakli_data,
            'haber_data': haber_data,
            'executive_summary': executive_summary,
            'logo_url': REPORT_CONFIG['logo_url'],
            'company_name': REPORT_CONFIG['company_name'],
            'year': REPORT_CONFIG['year'],
            'css_path': css_path
        }
        
        return self.template.render(**context)
    
    def preview_html(
        self,
        firma_adi: str,
        baslangic: date,
        bitis: date,
        sicil_data: List[Dict],
        yasakli_data: List[Dict],
        haber_data: List[Dict],
        executive_summary: str
    ) -> str:
        """
        HTML önizleme oluşturur (debug için)
        
        Returns:
            HTML dosya yolu
        """
        html_content = self._render_html(
            firma_adi=firma_adi,
            baslangic=baslangic,
            bitis=bitis,
            sicil_data=sicil_data,
            yasakli_data=yasakli_data,
            haber_data=haber_data,
            executive_summary=executive_summary
        )
        
        output_path = os.path.join(OUTPUT_DIR, 'preview.html')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"📝 HTML önizleme oluşturuldu: {output_path}")
        return output_path


# Global PDF generator instance
pdf_generator = PDFGenerator()
