"""
KKB Hackathon - LLM Service
OpenAI API kullanarak özet oluşturma servisi
"""

import json
from typing import List, Dict
from openai import OpenAI

from config import OPENAI_CONFIG


class LLMService:
    """LLM ile etkileşim için servis sınıfı"""
    
    def __init__(self):
        self.client = OpenAI(
            base_url=OPENAI_CONFIG["base_url"],
            api_key=OPENAI_CONFIG["api_key"]
        )
        self.model = OPENAI_CONFIG["model"]
        self.temperature = OPENAI_CONFIG["temperature"]
        self.max_tokens = OPENAI_CONFIG["max_tokens"]
    
    def generate_executive_summary(
        self,
        firma_adi: str,
        sicil_data: List[Dict],
        yasakli_data: List[Dict],
        haber_data: List[Dict]
    ) -> str:
        """
        Toplanan tüm verileri analiz ederek yönetici özeti oluşturur
        
        Args:
            firma_adi: Şirket adı
            sicil_data: Sicil kayıtları
            yasakli_data: Yasak kayıtları
            haber_data: Haber kayıtları
        
        Returns:
            Yönetici özeti metni
        """
        print("🤖 LLM ile özet oluşturuluyor...")
        
        prompt = self._build_prompt(
            firma_adi,
            sicil_data,
            yasakli_data,
            haber_data
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            summary = response.choices[0].message.content
            print("✅ Özet başarıyla oluşturuldu")
            return summary
            
        except Exception as e:
            print(f"❌ LLM özet hatası: {e}")
            return self._generate_fallback_summary(
                firma_adi,
                sicil_data,
                yasakli_data,
                haber_data
            )
    
    def _get_system_prompt(self) -> str:
        """Sistem prompt'unu döner"""
        return """Sen bir finansal analist ve raporlama uzmanısın. 
Firma verileri üzerine detaylı, objektif ve içgörülü raporlar hazırlarsın.
Raporların profesyonel, net ve karar vericiler için değerli olmalıdır.
Türkçe dilinde kusursuz yazarsın."""
    
    def _build_prompt(
        self,
        firma_adi: str,
        sicil_data: List[Dict],
        yasakli_data: List[Dict],
        haber_data: List[Dict]
    ) -> str:
        """Özet için prompt oluşturur"""
        return f"""
Aşağıda {firma_adi} firması hakkında toplanan veriler bulunmaktadır. 
Bu verileri analiz ederek yöneticiler için kapsamlı bir özet rapor hazırla.

## TİCARET SİCİL GAZETESİ KAYITLARI ({len(sicil_data)} kayıt):
{json.dumps(sicil_data, ensure_ascii=False, indent=2, default=str)}

## İHALE YASAKLISI KAYITLARI ({len(yasakli_data)} kayıt):
{json.dumps(yasakli_data, ensure_ascii=False, indent=2, default=str)}

## HABER ANALİZİ ({len(haber_data)} haber):
{json.dumps(haber_data, ensure_ascii=False, indent=2, default=str)}

Lütfen şu başlıklar altında detaylı bir özet hazırla:

## 1. Genel Durum
Firmanın mevcut durumu ve genel bir değerlendirmesi

## 2. Ticari Faaliyetler ve Değişiklikler
Ticaret sicil gazetesindeki kayıtlardan çıkan önemli gelişmeler

## 3. Risk Değerlendirmesi
İhale yasakları ve diğer riskli durumların analizi

## 4. Medya Görünürlüğü ve İtibar
Haberlerin analizi, sentiment dağılımı ve medyadaki algı

## 5. Öneriler ve Sonuç
Karar vericiler için öneriler ve genel değerlendirme

Özet profesyonel, net ve karar vericiler için değerli olmalıdır.
Her başlık altında somut verilerden örnekler ver ve yorumla.
"""
    
    def _generate_fallback_summary(
        self,
        firma_adi: str,
        sicil_data: List[Dict],
        yasakli_data: List[Dict],
        haber_data: List[Dict]
    ) -> str:
        """LLM hatası durumunda basit özet oluşturur"""
        summary = f"""# {firma_adi} - Yönetici Özeti

**NOT:** Bu özet, LLM servisi kullanılamadığı için otomatik olarak oluşturulmuştur.

## Genel Durum
{firma_adi} hakkında toplam {len(sicil_data) + len(yasakli_data) + len(haber_data)} adet veri kaydı bulunmaktadır.

## Ticari Faaliyetler
- Ticaret Sicil Gazetesi Kayıtları: {len(sicil_data)} adet
"""
        
        if sicil_data:
            summary += "\n### Öne Çıkan Tescil İşlemleri:\n"
            for ilan in sicil_data[:3]:
                tescil_konusu = ilan.get('detaylar', {}).get('tescil_konusu', 'Belirtilmemiş')
                summary += f"- {ilan.get('gazete_tarihi')}: {tescil_konusu}\n"
        
        summary += f"\n## Risk Değerlendirmesi\n"
        if yasakli_data:
            summary += f"**⚠️ DİKKAT:** Firma {len(yasakli_data)} adet ihale yasağına sahiptir.\n\n"
            for yasak in yasakli_data:
                summary += f"- {yasak.get('yasak_tarihi')}: {yasak.get('yasaklayan_kurum')} - {yasak.get('yasak_suresi')}\n"
        else:
            summary += "✅ Herhangi bir ihale yasağı kaydı bulunmamaktadır.\n"
        
        summary += f"\n## Medya Görünürlüğü\n"
        if haber_data:
            positive = len([h for h in haber_data if h.get('label') == 'positive'])
            neutral = len([h for h in haber_data if h.get('label') == 'neutral'])
            negative = len([h for h in haber_data if h.get('label') == 'negative'])
            
            summary += f"- Toplam {len(haber_data)} haber analiz edildi\n"
            summary += f"- Olumlu: {positive} | Nötr: {neutral} | Olumsuz: {negative}\n"
        else:
            summary += "ℹ️ Medya verisi bulunmamaktadır.\n"
        
        summary += "\n## Öneriler\n"
        summary += "Lütfen verileri detaylı olarak inceleyin ve risk değerlendirmesi yapın.\n"
        
        return summary


# Global LLM service instance
llm_service = LLMService()
