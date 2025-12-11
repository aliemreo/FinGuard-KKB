# 🚀 KKB Hackathon - Firma Raporu Oluşturma Sistemi

Agentic AI kullanarak otomatik firma raporu üretimi yapan modüler Python uygulaması.

## 📋 İçindekiler

- [Özellikler](#özellikler)
- [Proje Yapısı](#proje-yapısı)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Konfigürasyon](#konfigürasyon)
- [Modüller](#modüller)
- [Veri Kaynakları](#veri-kaynakları)

## ✨ Özellikler

- ✅ **Modüler Mimari**: Her modül kendi sorumluluğunu taşır
- ✅ **Mock Data Desteği**: Veritabanı olmadan test edilebilir
- ✅ **PostgreSQL Entegrasyonu**: Gerçek veritabanı desteği
- ✅ **LLM Özet Oluşturma**: OpenAI API ile akıllı analiz
- ✅ **Profesyonel PDF Çıktısı**: WeasyPrint ile modern tasarım
- ✅ **Ayrı HTML/CSS**: Kolay özelleştirme
- ✅ **Toplu İşlem**: Birden fazla firma için rapor
- ✅ **Türkçe Destek**: Tam Türkçe içerik

## 📁 Proje Yapısı

```
.
├── app.py                  # Ana uygulama
├── config.py               # Konfigürasyon ayarları
├── database.py             # Veritabanı yönetimi
├── data_fetchers.py        # Veri çekme fonksiyonları
├── llm_service.py          # LLM özet servisi
├── pdf_generator.py        # PDF oluşturma servisi
├── mock_data.py            # Mock veri üreticileri
├── requirements.txt        # Python bağımlılıkları
├── README.md              # Bu dosya
│
├── templates/             # HTML template'ler
│   └── report_template.html
│
├── static/                # CSS ve statik dosyalar
│   └── style.css
│
└── output/                # Oluşturulan PDF'ler
    └── *.pdf
```

## 🔧 Kurulum

### 1. Gerekli Paketleri Yükleyin

```bash
pip install -r requirements.txt
```

### 2. Konfigürasyonu Düzenleyin

`config.py` dosyasını açın ve ayarları düzenleyin:

```python
# Mock data ile test için
USE_MOCK_DATA = True

# Gerçek veritabanı için
USE_MOCK_DATA = False
DB_CONFIG = {
    "host": "your_host",
    "database": "your_db",
    "user": "your_user",
    "password": "your_password"
}

# OpenAI API key
OPENAI_CONFIG["api_key"] = "sk-YOUR-ACTUAL-KEY"
```

### 3. Dizinleri Oluşturun

Gerekli dizinler otomatik oluşturulur, ancak manuel oluşturmak isterseniz:

```bash
mkdir -p templates static output
```

## 🎯 Kullanım

### Basit Kullanım

```python
from app import create_company_report

# Tek firma için rapor
pdf_path = create_company_report(
    firma_adi="Turkcell",
    baslangic_tarihi="2024-01-01",
    bitis_tarihi="2024-12-31"
)
print(f"Rapor oluşturuldu: {pdf_path}")
```

### Toplu Rapor Oluşturma

```python
from app import batch_create_reports

companies = ["Turkcell", "Türk Telekom", "Vodafone"]
results = batch_create_reports(
    companies=companies,
    start_date="2024-01-01",
    end_date="2024-12-31"
)
```

### Komut Satırından

```bash
# Tek firma
python app.py "Turkcell" "2024-01-01" "2024-12-31"

# Haber JSON dosyası ile
python app.py "Turkcell" "2024-01-01" "2024-12-31" "haberler.json"
```

### Demo Çalıştırma

```bash
python app.py
```

## ⚙️ Konfigürasyon

### Mock Data Toggle

`config.py` dosyasında:

```python
USE_MOCK_DATA = True   # Mock data kullan
USE_MOCK_DATA = False  # Gerçek veritabanı kullan
```

### Veritabanı Ayarları

PostgreSQL bağlantı bilgileri:

```python
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "kkb_hackathon",
    "user": "postgres",
    "password": "your_password"
}
```

### LLM API Ayarları

OpenAI API konfigürasyonu:

```python
OPENAI_CONFIG = {
    "base_url": "https://mia.csp.kloudeks.com/v1",
    "api_key": "sk-XXXX",
    "model": "gpt-oss-120b",
    "temperature": 0.7,
    "max_tokens": 2000
}
```

## 📦 Modüller

### `config.py`
Tüm proje ayarlarını merkezi olarak yönetir.

### `database.py`
PostgreSQL bağlantı yönetimi ve sorgu çalıştırma.

### `mock_data.py`
Test için sahte veri üretimi.

### `data_fetchers.py`
Tüm veri kaynaklarından veri çekme fonksiyonları:
- Ticaret Sicil Gazetesi
- İhale Yasaklısı
- Haber Analizi

### `llm_service.py`
OpenAI API ile etkileşim ve özet oluşturma.

### `pdf_generator.py`
WeasyPrint ve Jinja2 ile PDF rapor oluşturma.

### `app.py`
Ana uygulama - tüm modülleri orkestra eder.

## 🗄️ Veri Kaynakları

### 1. Ticaret Sicil Gazetesi

**Tablo:** `ilanlar`

**Sütunlar:**
- id, ticaret_sicil_no, ilan_no, ilan_turu
- mersis_no, unvan, il, ilce, adres
- tescil_tarihi, gazete_tarihi, gazete_sayisi
- detaylar (JSONB)

### 2. İhale Yasaklısı

**Tablo:** `ihale_yasakli`

**Sütunlar:**
- id, firma_unvan, yasaklayan_kurum
- yasak_tarihi, yasak_suresi, yasak_nedeni
- yasak_kayit_no, gazete_sayisi, gazete_tarihi

### 3. Haber Analizi

**Format:** JSON dosyası

**Alan yapısı:**
```json
{
  "url": "string",
  "title": "string",
  "published_at": "string",
  "article_text": "string",
  "label": "positive|neutral|negative",
  "confidence": float
}
```

## 📄 PDF İçeriği

Oluşturulan rapor şunları içerir:

1. **Kapak Sayfası**
   - Firma adı
   - Logo
   - Tarih bilgileri

2. **Yönetici Özeti**
   - LLM tarafından oluşturulan kapsamlı analiz

3. **Ticaret Sicil Gazetesi**
   - Tablo formatında kayıtlar
   - Detaylı açıklamalar

4. **İhale Yasaklısı**
   - Uyarı kutuları
   - Yasak detayları

5. **Medya Analizi**
   - Sentiment istatistikleri
   - Haber kartları

## 🎨 Özelleştirme

### HTML Template

`templates/report_template.html` dosyasını düzenleyin.

### CSS Stilleri

`static/style.css` dosyasını düzenleyin.

### Logo Değiştirme

`config.py` dosyasında:

```python
REPORT_CONFIG = {
    "logo_url": "https://your-logo-url.com/logo.png",
    ...
}
```

## 🐛 Hata Ayıklama

### HTML Önizleme

PDF yerine HTML önizleme oluşturmak için:

```python
create_company_report(
    firma_adi="Turkcell",
    baslangic_tarihi="2024-01-01",
    bitis_tarihi="2024-12-31",
    generate_html_preview=True  # HTML önizleme
)
```

Bu `output/preview.html` dosyası oluşturur.

### Veritabanı Bağlantı Testi

```python
from database import db_manager

if db_manager.test_connection():
    print("✅ Bağlantı başarılı")
else:
    print("❌ Bağlantı başarısız")
```

## 📝 Notlar

- Mock data modu aktifken veritabanına bağlanmaz
- LLM servisi hata verirse fallback özet oluşturur
- PDF oluşturma için WeasyPrint sistem bağımlılıkları gerektirir
- Türkçe karakterler tam destek ile çalışır

## Katkıda Bulunma

Proje modüler yapıda olduğu için her modül ayrı ayrı geliştirilebilir:

1. Yeni veri kaynağı eklemek: `data_fetchers.py`
2. Yeni PDF bölümü eklemek: `templates/report_template.html`
3. Stil değişiklikleri: `static/style.css`
4. LLM prompt geliştirme: `llm_service.py`