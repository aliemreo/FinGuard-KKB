CREATE TABLE IF NOT EXISTS ihale_yasaklilari (
    id SERIAL PRIMARY KEY,
    ihale_kayit_numarasi TEXT,
    yasaklama_karari_veren_bakanlik_kurum TEXT,
    ihaleyi_yapan_idarenin_adi TEXT,
    ortaklar JSONB,
    yasaklama_kanun_dayanagi TEXT,
    yasaklama_kanun_kapsami TEXT,
    yasaklama_suresi TEXT,
    yasaklama_tarihi DATE,
    yasakli JSONB,
    olusturulma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);