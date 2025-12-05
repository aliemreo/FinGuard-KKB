# PDF OCR ve Mizanpaj Analiz Hattı (Pipeline)

Bu proje, PDF belgelerini işleyerek yapılandırılmış veriye (JSON) dönüştüren bir veri akış hattıdır. Sistem; yüksek çözünürlüklü görüntüleme, mizanpaj analizi (Layout Analysis), OCR ve LLM destekli son işlem adımlarını içerir.

## 🔄 Veri Akış Diyagramı

```mermaid
graph TD
    A[PDF Kuyruğu] --> B(Veri Alımı / Ingestion)
    B --> C{Ön İşleme / Preprocessing}
    C -->|Görüntü İyileştirme| D[Mizanpaj Analizi / Layout Worker]
    D -->|Bölge ve Sıra Tespiti| E[Kırpma ve OCR]
    E --> F[Birleştirme ve Son İşleme]
    F -->|Opsiyonel| G[LLM Düzeltmesi]
    G --> H[JSON Çıktısı]
    