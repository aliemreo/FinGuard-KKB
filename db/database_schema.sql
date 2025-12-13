-- Drop existing table if it exists
DROP TABLE IF EXISTS ilanlar CASCADE;

-- ============================================================================
-- İLAN TÜRLERİ (ilan_turu SMALLINT değerleri)
-- ============================================================================
-- 1  = Kuruluş            - Yeni Şirket/İşletme Açılışı
-- 2  = Yönetim/Temsil     - Müdür/YK Atama, İmza Yetkisi, İç Yönerge
-- 3  = Sermaye/Pay        - Sermaye Artırımı/Azaltımı, Hisse Devri
-- 4  = Sözleşme/Merkez    - Adres Değişikliği, Unvan Değişikliği, Tadil
-- 5  = Yapısal Değişiklik - Birleşme, Bölünme, Tür Değiştirme
-- 6  = Şube               - Şube Açılış/Kapanış
-- 7  = Tasfiye            - Tasfiyeye Giriş, Tasfiye Sonu
-- 8  = İflas/Konkordato   - İflas Kararı, Konkordato Mühleti
-- 9  = Devir              - İşletme Devri
-- 10 = Çağrı/Bildirim     - Genel Kurul Çağrısı, Alacaklılara Çağrı
-- 11 = Düzeltme           - Hatalı İlan Düzeltmesi
-- ============================================================================

CREATE TABLE ilanlar (
    id SERIAL PRIMARY KEY,
    ticaret_sicil_no VARCHAR(50),
    ilan_no VARCHAR(50) UNIQUE,
    ilan_turu SMALLINT NOT NULL,          -- 1-11 arası (yukarıdaki açıklamalara bakın)
    mersis_no VARCHAR(16),
    unvan VARCHAR(500) NOT NULL,
    il SMALLINT NOT NULL,                 -- Plaka kodu (1-81)
    ilce VARCHAR(100),
    adres TEXT,
    tescil_tarihi DATE,
    gazete_tarihi DATE,                   -- Ana sıralama bu alana göre yapılacak
    gazete_sayisi VARCHAR(20),
    detaylar JSONB DEFAULT '{}'
);

CREATE INDEX idx_mersis ON ilanlar(mersis_no) WHERE mersis_no IS NOT NULL;
CREATE INDEX idx_unvan ON ilanlar(unvan);
CREATE INDEX idx_gazete_tarihi ON ilanlar(gazete_tarihi DESC NULLS LAST);
