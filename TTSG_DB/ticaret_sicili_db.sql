CREATE EXTENSION IF NOT EXISTS "pg_trgm";

CREATE TABLE ilanlar (
    id SERIAL PRIMARY KEY,
    
    -- Temel
    ilan_no VARCHAR(50) NOT NULL,
    ilan_turu SMALLINT NOT NULL,          -- 1-52 arası
    
    -- Şirket
    mersis_no VARCHAR(16),
    unvan VARCHAR(500) NOT NULL,
    
    -- Lokasyon
    il SMALLINT NOT NULL,                 -- Plaka kodu (1-81)
    ilce VARCHAR(100),
    adres TEXT,
    
    -- Tarihler
    tescil_tarihi DATE NOT NULL,
    gazete_tarihi DATE,
    gazete_sayisi VARCHAR(20),
    
    -- Detaylar
    detaylar JSONB DEFAULT '{}'
);

-- İndeksler
CREATE INDEX idx_il ON ilanlar(il);
CREATE INDEX idx_unvan ON ilanlar USING gin(unvan gin_trgm_ops);
CREATE INDEX idx_mersis ON ilanlar(mersis_no) WHERE mersis_no IS NOT NULL;
CREATE INDEX idx_tescil ON ilanlar(tescil_tarihi DESC);
CREATE INDEX idx_detaylar ON ilanlar USING gin(detaylar);