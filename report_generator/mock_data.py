"""
KKB Hackathon - Mock Data Generators
Test için sahte veri üretimi
"""

from datetime import date
from typing import List, Dict


def generate_mock_sicil_data(firma_adi: str, baslangic: date, bitis: date) -> List[Dict]:
    """
    Ticaret Sicil Gazetesi için sahte veri üretir
    
    Args:
        firma_adi: Şirket adı
        baslangic: Başlangıç tarihi
        bitis: Bitiş tarihi
    
    Returns:
        İlan kayıtları listesi
    """
    return [
        {
            "id": 1,
            "ticaret_sicil_no": "123456",
            "ilan_no": "2024/001234",
            "ilan_turu": 1,
            "mersis_no": "0123456789000001",
            "unvan": f"{firma_adi} ANONİM ŞİRKETİ",
            "il": 34,
            "ilce": "Kadıköy",
            "adres": "Bağdat Caddesi No:123 Kadıköy/İstanbul",
            "tescil_tarihi": "2024-01-15",
            "gazete_tarihi": "2024-01-20",
            "gazete_sayisi": "11234",
            "detaylar": {
                "tescil_konusu": "Sermaye Artırımı",
                "eski_sermaye": "5000000",
                "yeni_sermaye": "10000000",
                "yoneticiler": ["Ahmet YILMAZ", "Mehmet KAYA"],
                "aciklama": "Şirket sermayesi 5 milyon TL'den 10 milyon TL'ye yükseltilmiştir."
            }
        },
        {
            "id": 2,
            "ticaret_sicil_no": "123456",
            "ilan_no": "2024/005678",
            "ilan_turu": 2,
            "mersis_no": "0123456789000001",
            "unvan": f"{firma_adi} ANONİM ŞİRKETİ",
            "il": 34,
            "ilce": "Kadıköy",
            "adres": "Bağdat Caddesi No:123 Kadıköy/İstanbul",
            "tescil_tarihi": "2024-06-10",
            "gazete_tarihi": "2024-06-15",
            "gazete_sayisi": "11567",
            "detaylar": {
                "tescil_konusu": "Yönetim Kurulu Değişikliği",
                "yeni_yoneticiler": ["Ayşe DEMİR"],
                "gorevden_ayrilanlar": ["Mehmet KAYA"],
                "aciklama": "Yönetim kurulu üyesi değişikliği gerçekleştirilmiştir."
            }
        },
        {
            "id": 3,
            "ticaret_sicil_no": "123456",
            "ilan_no": "2024/008912",
            "ilan_turu": 3,
            "mersis_no": "0123456789000001",
            "unvan": f"{firma_adi} ANONİM ŞİRKETİ",
            "il": 34,
            "ilce": "Kadıköy",
            "adres": "Bağdat Caddesi No:456 Kadıköy/İstanbul",
            "tescil_tarihi": "2024-09-05",
            "gazete_tarihi": "2024-09-10",
            "gazete_sayisi": "11789",
            "detaylar": {
                "tescil_konusu": "Adres Değişikliği",
                "eski_adres": "Bağdat Caddesi No:123",
                "yeni_adres": "Bağdat Caddesi No:456",
                "aciklama": "Şirket merkez adresi değiştirilmiştir."
            }
        }
    ]


def generate_mock_yasakli_data(firma_adi: str, baslangic: date, bitis: date) -> List[Dict]:
    """
    İhale Yasaklısı için sahte veri üretir
    
    Args:
        firma_adi: Şirket adı
        baslangic: Başlangıç tarihi
        bitis: Bitiş tarihi
    
    Returns:
        Yasak kayıtları listesi
    """
    # Firma adında "Temiz" veya "Good" varsa yasaklı değil
    if "Temiz" in firma_adi or "Good" in firma_adi:
        return []
    
    return [
        {
            "id": 1,
            "firma_unvan": f"{firma_adi} ANONİM ŞİRKETİ",
            "yasaklayan_kurum": "Sağlık Bakanlığı / Kamu Hastaneleri Genel Müdürlüğü",
            "yasak_tarihi": "2024-03-15",
            "yasak_suresi": "1 YIL",
            "yasak_nedeni": "4735 Sayılı Kamu İhale Sözleşmeleri Kanunu - Sözleşme yükümlülüklerinin yerine getirilmemesi",
            "yasak_kayit_no": "2024/251823",
            "gazete_sayisi": "32456",
            "gazete_tarihi": "2024-03-20"
        },
        {
            "id": 2,
            "firma_unvan": f"{firma_adi} ANONİM ŞİRKETİ",
            "yasaklayan_kurum": "Ulaştırma ve Altyapı Bakanlığı",
            "yasak_tarihi": "2024-07-22",
            "yasak_suresi": "6 AY",
            "yasak_nedeni": "4734 Sayılı Kamu İhale Kanunu - Teklif ve sözleşme sürecinde yanlış beyanda bulunma",
            "yasak_kayit_no": "2024/389456",
            "gazete_sayisi": "32678",
            "gazete_tarihi": "2024-07-28"
        }
    ]


def generate_mock_haber_data(firma_adi: str) -> List[Dict]:
    """
    Haber analizi için sahte veri üretir
    
    Args:
        firma_adi: Şirket adı
    
    Returns:
        Haber kayıtları listesi
    """
    return [
        {
            "url": "https://www.ekonomim.com/haber/sermaye-artirimi-2024",
            "title": f"{firma_adi} Sermayesini 100 Milyon TL'ye Yükseltti",
            "published_at": "2024-02-15 14:30:00 +0000",
            "path_to_screenshot": "images/screenshot_01.png",
            "article_text": f"{firma_adi}, yönetim kurulu kararıyla şirket sermayesini 50 milyon TL'den 100 milyon TL'ye yükseltti. Şirket yetkilileri, bu artışın yeni yatırımlar için gerekli olduğunu ve büyüme hedeflerine ulaşmak için önemli bir adım olduğunu belirtti. Karar, Ticaret Sicil Gazetesi'nde yayımlanarak yürürlüğe girdi.",
            "language": "Turkish",
            "label": "positive",
            "confidence": 0.9124
        },
        {
            "url": "https://www.haberturk.com/teknoloji/yeni-yonetim-kurulu",
            "title": f"{firma_adi} Yönetim Kurulu'nda Değişiklik",
            "published_at": "2024-07-10 09:15:00 +0000",
            "path_to_screenshot": "images/screenshot_02.png",
            "article_text": f"{firma_adi}'de yönetim kurulu üyelerinde değişiklik yapıldı. Genel kurul kararıyla yeni üyeler atandı ve görevlerine başladı. Şirket, yeni yönetim kadrosuyla stratejik hedeflerine daha hızlı ulaşmayı planlıyor.",
            "language": "Turkish",
            "label": "neutral",
            "confidence": 0.7856
        },
        {
            "url": "https://www.dunya.com/ekonomi/ihale-yasagi-2024",
            "title": f"{firma_adi} Kamu İhalelerinden Geçici Olarak Yasaklandı",
            "published_at": "2024-03-25 16:45:00 +0000",
            "path_to_screenshot": "images/screenshot_03.png",
            "article_text": f"Sağlık Bakanlığı, {firma_adi}'yi sözleşme yükümlülüklerini yerine getirmediği gerekçesiyle 1 yıl süreyle kamu ihalelerine katılmaktan yasakladı. Yasak kararı Resmi Gazete'de yayımlanarak yürürlüğe girdi. Şirket yetkilileri konuyla ilgili henüz açıklama yapmadı.",
            "language": "Turkish",
            "label": "negative",
            "confidence": 0.8934
        },
        {
            "url": "https://www.bloomberght.com/is-dunyasi/teknoloji-yatirimi",
            "title": f"{firma_adi} Ar-Ge Merkezine 50 Milyon TL Yatırım Yapacak",
            "published_at": "2024-05-18 11:20:00 +0000",
            "path_to_screenshot": "images/screenshot_04.png",
            "article_text": f"{firma_adi}, İstanbul Teknopark'ta kuracağı Ar-Ge merkezine 50 milyon TL yatırım yapacağını açıkladı. Merkez, yapay zeka ve veri analitiği alanlarında çalışmalar yürütecek. Proje kapsamında 100 yeni mühendis istihdam edilecek.",
            "language": "Turkish",
            "label": "positive",
            "confidence": 0.9341
        },
        {
            "url": "https://www.ntv.com.tr/ekonomi/ikinci-ihale-yasagi",
            "title": f"{firma_adi}'ya İkinci Yasak Kararı",
            "published_at": "2024-08-05 13:50:00 +0000",
            "path_to_screenshot": "images/screenshot_05.png",
            "article_text": f"Ulaştırma ve Altyapı Bakanlığı, {firma_adi}'yi ihale sürecinde yanlış beyanda bulunduğu gerekçesiyle 6 ay süreyle yasakladı. Bu, şirketin bu yıl içinde aldığı ikinci yasak kararı oldu. Sektör analistleri, durumun şirketin finansal durumunu olumsuz etkileyebileceğini belirtiyor.",
            "language": "Turkish",
            "label": "negative",
            "confidence": 0.9156
        }
    ]
