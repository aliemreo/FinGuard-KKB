-- Drop existing tables if they exist
DROP TABLE IF EXISTS announcements CASCADE;
DROP TABLE IF EXISTS gazettes CASCADE;
DROP TABLE IF EXISTS crawling_history CASCADE;

-- =============================================================================
-- GAZETTES TABLE - Stores gazette-level metadata
-- =============================================================================
CREATE TABLE gazettes (
    id SERIAL PRIMARY KEY,
    gazette_date DATE,                      -- e.g., "13 KASIM 2025" parsed to DATE
    gazette_number INTEGER,                 -- e.g., 11457
    gazette_page INTEGER,                   -- e.g., 704
    source_file VARCHAR(255),               -- Original PDF/MD filename
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(gazette_number, gazette_page)    -- Unique constraint on gazette+page
);

CREATE INDEX idx_gazette_date ON gazettes(gazette_date DESC);
CREATE INDEX idx_gazette_number ON gazettes(gazette_number);

-- =============================================================================
-- ANNOUNCEMENTS TABLE - Stores individual announcements from gazettes
-- =============================================================================
-- İLAN TÜRLERİ (announcement_type values from batch_process_gazettes.py):
--   birleşme           - Merger
--   sermaye_azaltımı   - Capital decrease
--   tasfiye            - Liquidation
--   mal_varlığı_devri  - Asset transfer
--   şube_kuruluşu      - Branch establishment
--   adres_değişikliği  - Address change
--   toplantı_çağrısı   - Meeting call
--   pay_senedi_değişimi - Share exchange
--   sermaye_taahhüdü   - Capital commitment
--   bileşik_değişiklik - Compound (multiple types in one announcement)
--   unknown            - Unrecognized type (e.g., Yönetim Kurulu, Denetçiler)

CREATE TABLE announcements (
    id SERIAL PRIMARY KEY,
    gazette_id INTEGER REFERENCES gazettes(id) ON DELETE CASCADE,
    
    -- Metadata from batch_process_gazettes.py "metadata" object
    registry_office VARCHAR(255),           -- e.g., "ANKARA TİCARET SİCİLİ MÜDÜRLÜĞÜ"
    registry_number VARCHAR(50),            -- e.g., "149-Akyurt" (ticaret_sicil_no)
    mersis_no VARCHAR(20),                  -- e.g., "0843000232400028" (16 digits)
    company_name VARCHAR(500) NOT NULL,     -- e.g., "HAVELSAN TEKNOLOJİ RADAR..."
    announcement_number VARCHAR(50),        -- İlan Sıra No, e.g., "70975"
    
    -- Announcement type from batch_process_gazettes.py
    announcement_type VARCHAR(50) NOT NULL, -- e.g., "unknown", "birleşme", etc.
    
    -- Content fields (commonly extracted)
    company_address TEXT,                   -- From content.company_address
    registration_date DATE,                 -- Tescil tarihi
    registered_matters TEXT,                -- Tescil Edilen Hususlar
    changes_summary TEXT,                   -- Turkish summary of changes
    
    -- Full content as JSONB for flexible storage of type-specific fields
    content JSONB DEFAULT '{}',             -- Stores all extraction fields
    
    -- Extraction metadata
    extraction_success BOOLEAN DEFAULT TRUE,
    raw_text TEXT,                          -- Optional raw text for failed extractions
    
    -- City/location derived from registry_office
    city VARCHAR(50),                       -- Extracted from registry_office (e.g., "ANKARA")
    
    -- Search/filter fields (populated from filter_settings)
    company_filter VARCHAR(500),            -- Search term used
    city_filter VARCHAR(50),                -- City filter used
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_ann_mersis ON announcements(mersis_no) WHERE mersis_no IS NOT NULL;
CREATE INDEX idx_ann_company ON announcements(company_name);
CREATE INDEX idx_ann_type ON announcements(announcement_type);
CREATE INDEX idx_ann_city ON announcements(city);
CREATE INDEX idx_ann_gazette ON announcements(gazette_id);
CREATE INDEX idx_ann_announcement_no ON announcements(announcement_number);
CREATE INDEX idx_ann_content ON announcements USING GIN (content);

-- =============================================================================
-- CRAWLING HISTORY - Tracks successfully fetched date ranges
-- =============================================================================
-- Used to avoid redundant fetching by calculating missing intervals:
--   SELECT datemultirange(target_range) - range_agg(fetched_period)
--   FROM crawling_history WHERE company_filter = ? AND city_filter = ?

CREATE TABLE crawling_history (
    id SERIAL PRIMARY KEY,
    company_filter VARCHAR(500) NOT NULL,   -- Search term used (matches filter_settings.company_filter)
    city_filter VARCHAR(50),                -- City filter (matches filter_settings.city_filter)
    fetched_period DATERANGE NOT NULL,      -- The date range that was successfully scraped
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_period CHECK (NOT isempty(fetched_period))
);

-- Composite index for efficient lookups by company + city
CREATE INDEX idx_crawling_company_city ON crawling_history(company_filter, city_filter);

-- =============================================================================
-- HELPER FUNCTION: Extract city from registry_office
-- =============================================================================
CREATE OR REPLACE FUNCTION extract_city_from_registry(registry_office TEXT)
RETURNS VARCHAR(50) AS $$
BEGIN
    -- Pattern: "T.C. ANKARA TİCARET SİCİLİ MÜDÜRLÜĞÜ" -> "ANKARA"
    -- Or: "ANKARA TİCARET SİCİLİ MÜDÜRLÜĞÜ" -> "ANKARA"
    RETURN UPPER(TRIM(
        REGEXP_REPLACE(
            REGEXP_REPLACE(registry_office, '^T\.?C\.?\s*', '', 'i'),
            '\s*TİCARET\s+SİCİLİ\s+MÜDÜRLÜĞÜ.*$', '', 'i'
        )
    ));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =============================================================================
-- VIEW: Flattened view for easy querying
-- =============================================================================
CREATE OR REPLACE VIEW v_announcements AS
SELECT 
    a.id,
    a.announcement_number,
    a.announcement_type,
    a.company_name,
    a.mersis_no,
    a.registry_office,
    a.registry_number,
    a.city,
    a.company_address,
    a.registration_date,
    a.registered_matters,
    a.changes_summary,
    a.extraction_success,
    g.gazette_date,
    g.gazette_number,
    g.gazette_page,
    a.content,
    a.company_filter,
    a.city_filter,
    a.created_at
FROM announcements a
LEFT JOIN gazettes g ON a.gazette_id = g.id;

-- =============================================================================
-- COMMENTS for documentation
-- =============================================================================
COMMENT ON TABLE gazettes IS 'Gazette-level metadata from gazette_metadata in JSON output';
COMMENT ON TABLE announcements IS 'Individual announcements extracted from gazettes';
COMMENT ON COLUMN announcements.content IS 'Full JSONB content for type-specific fields like key_people, notary_info, etc.';
COMMENT ON COLUMN announcements.announcement_type IS 'Type from LLM detection: birleşme, tasfiye, adres_değişikliği, unknown, etc.';
