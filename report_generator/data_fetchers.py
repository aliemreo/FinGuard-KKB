"""
KKB Hackathon - Data Fetchers
Tüm veri kaynaklarından veri çekme fonksiyonları
"""

import json
import os
from datetime import date
from typing import List, Dict

from config import USE_MOCK_DATA
from database import db_manager
from mock_data import (
    generate_mock_sicil_data,
    generate_mock_yasakli_data,
    generate_mock_haber_data
)


def fetch_sicil_data(firma_adi: str, baslangic: date, bitis: date) -> List[Dict]:
    """
    Ticaret Sicil Gazetesi verilerini çeker
    
    Args:
        firma_adi: Şirket adı
        baslangic: Başlangıç tarihi
        bitis: Bitiş tarihi
    
    Returns:
        İlan kayıtları listesi
    """
    if USE_MOCK_DATA:
        print(f"📊 Mock Sicil verisi üretiliyor: {firma_adi}")
        return generate_mock_sicil_data(firma_adi, baslangic, bitis)
    
    # Gerçek veritabanı sorgusu
    print(f"📊 Sicil verileri veritabanından çekiliyor: {firma_adi}")
    query = """
        SELECT 
            id, ticaret_sicil_no, ilan_no, ilan_turu, 
            mersis_no, unvan, il, ilce, adres,
            tescil_tarihi, gazete_tarihi, gazete_sayisi, detaylar
        FROM ilanlar
        WHERE 
            LOWER(unvan) LIKE LOWER(%s)
            AND gazete_tarihi BETWEEN %s AND %s
        ORDER BY gazete_tarihi DESC
    """
    
    results = db_manager.execute_query(
        query,
        (f"%{firma_adi}%", baslangic, bitis)
    )
    
    print(f"✅ {len(results)} adet sicil kaydı bulundu")
    return results


def fetch_yasakli_data(firma_adi: str, baslangic: date, bitis: date) -> List[Dict]:
    """
    İhale Yasaklısı verilerini çeker
    
    Args:
        firma_adi: Şirket adı
        baslangic: Başlangıç tarihi
        bitis: Bitiş tarihi
    
    Returns:
        Yasak kayıtları listesi
    """
    if USE_MOCK_DATA:
        print(f"🚫 Mock Yasaklı verisi üretiliyor: {firma_adi}")
        return generate_mock_yasakli_data(firma_adi, baslangic, bitis)
    
    # Gerçek veritabanı sorgusu
    print(f"🚫 Yasaklı verileri veritabanından çekiliyor: {firma_adi}")
    query = """
        SELECT 
            id, firma_unvan, yasaklayan_kurum, yasak_tarihi,
            yasak_suresi, yasak_nedeni, yasak_kayit_no,
            gazete_sayisi, gazete_tarihi
        FROM ihale_yasakli
        WHERE 
            LOWER(firma_unvan) LIKE LOWER(%s)
            AND yasak_tarihi BETWEEN %s AND %s
        ORDER BY yasak_tarihi DESC
    """
    
    results = db_manager.execute_query(
        query,
        (f"%{firma_adi}%", baslangic, bitis)
    )
    
    print(f"✅ {len(results)} adet yasak kaydı bulundu")
    return results


def load_haber_data(json_file_path: str, firma_adi: str) -> List[Dict]:
    """
    Haber analizi JSON dosyasını yükler
    
    Args:
        json_file_path: JSON dosya yolu
        firma_adi: Şirket adı (filtreleme için)
    
    Returns:
        Haber kayıtları listesi
    """
    if USE_MOCK_DATA and not os.path.exists(json_file_path):
        print(f"📰 Mock Haber verisi üretiliyor: {firma_adi}")
        return generate_mock_haber_data(firma_adi)
    
    try:
        print(f"📰 Haber verileri yükleniyor: {json_file_path}")
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ {len(data)} adet haber kaydı yüklendi")
        return data
        
    except FileNotFoundError:
        print(f"⚠️  Dosya bulunamadı: {json_file_path}")
        if USE_MOCK_DATA:
            print("📰 Mock veri döndürülüyor")
            return generate_mock_haber_data(firma_adi)
        return []
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse hatası: {e}")
        return []


def get_all_company_data(
    firma_adi: str,
    baslangic: date,
    bitis: date,
    haber_json_path: str = None
) -> Dict:
    """
    Bir firma için tüm veri kaynaklarını toplar
    
    Args:
        firma_adi: Şirket adı
        baslangic: Başlangıç tarihi
        bitis: Bitiş tarihi
        haber_json_path: Haber JSON dosya yolu (opsiyonel)
    
    Returns:
        Tüm verileri içeren dictionary
    """
    print("\n" + "="*70)
    print(f"📦 Tüm veriler toplanıyor: {firma_adi}")
    print("="*70 + "\n")
    
    # Sicil verileri
    sicil_data = fetch_sicil_data(firma_adi, baslangic, bitis)
    
    # Yasaklı verileri
    yasakli_data = fetch_yasakli_data(firma_adi, baslangic, bitis)
    
    # Haber verileri
    haber_data = load_haber_data(
        haber_json_path or "haberler.json",
        firma_adi
    )
    
    print("\n" + "="*70)
    print("✅ Veri toplama tamamlandı")
    print(f"   • Sicil Kayıtları: {len(sicil_data)}")
    print(f"   • Yasak Kayıtları: {len(yasakli_data)}")
    print(f"   • Haber Kayıtları: {len(haber_data)}")
    print("="*70 + "\n")
    
    return {
        "sicil": sicil_data,
        "yasakli": yasakli_data,
        "haberler": haber_data
    }
