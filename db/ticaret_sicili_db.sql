CREATE TABLE ilanlar (
    id SERIAL PRIMARY KEY,
    ticaret_sicil_no VARCHAR(50),
    ilan_no VARCHAR(50) UNIQUE,
    ilan_turu SMALLINT NOT NULL,          -- 1-11 arası
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
