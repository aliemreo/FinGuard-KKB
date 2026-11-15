# 📄 İhale Yasaklıları Veri İşleme Hattı (Pipeline)

Bu proje, kamu ihale yasaklılarına ait belgeleri OCR ve Yapay Zeka (LLM) kullanarak işleyen, yapılandırılmış veriye dönüştüren ve PostgreSQL veritabanına kaydeden konteyner tabanlı bir uygulamadır.

## 🛠️ Teknolojiler

* **Python 3.10** (PaddleOCR, Pandas, Psycopg2)
* **PostgreSQL 15** (Veritabanı)
* **Docker & Docker Compose** (Konteynerizasyon)
* **LLM Entegrasyonu** (Veri ayıklama ve yapılandırma)

---

## 🚀 Kurulum ve Çalıştırma

Projeyi yerel ortamınızda ayağa kaldırmak için aşağıdaki adımları sırasıyla uygulayın.

### 1. Ortam Değişkenlerini Ayarlayın (.env)
Projenin ana dizininde `.env` adında bir dosya oluşturun ve aşağıdaki ayarları yapıştırın.

> **Önemli:** `API_KEY` alanına kendi geçerli LLM API anahtarınızı girmelisiniz.

```env
# --- LLM API Ayarları ---
API_KEY=sk-BURAYA_KENDI_API_ANAHTARINI_YAZ
BASE_URL=https://mia.csp.kloudeks.com/v1
MODEL=gpt-oss-120b

# --- Veritabanı Ayarları ---
# Docker içinde host ismi servis adı olan 'db' olmalıdır.
DB_HOST=db
DB_NAME=ihale_db
DB_USER=myusername
DB_PASSWORD=mypassword
```
Terminal:
```
docker-compose up -d --build

docker exec -it ihale_container_final bash
```
Konteyner içerisindeyken:
```
python pipeline.py --mode all --start-date 2024-07-20 --end-date 2024-07-20
```
