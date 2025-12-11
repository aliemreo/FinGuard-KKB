-- ============================================================================
-- Turkish Trade Registry Gazette Database Schema
-- ============================================================================

-- Drop existing tables (cascade to handle dependencies)
DROP TABLE IF EXISTS announcements CASCADE;
DROP TABLE IF EXISTS gazettes CASCADE;

-- ============================================================================
-- GAZETTE TABLE
-- ============================================================================
CREATE TABLE gazettes (
    id SERIAL PRIMARY KEY,
    gazette_number INTEGER NOT NULL,
    gazette_date VARCHAR(100),  -- Turkish date format varies
    page_number INTEGER,
    source_file VARCHAR(255),  -- Original PDF/JSON filename
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure unique gazette numbers
    CONSTRAINT unique_gazette_number UNIQUE (gazette_number, page_number)
);

CREATE INDEX idx_gazette_number ON gazettes(gazette_number);
CREATE INDEX idx_gazette_date ON gazettes(gazette_date);

-- ============================================================================
-- ANNOUNCEMENTS TABLE
-- ============================================================================
CREATE TABLE announcements (
    id SERIAL PRIMARY KEY,
    gazette_id INTEGER NOT NULL REFERENCES gazettes(id) ON DELETE CASCADE,

    -- Common metadata fields
    registry_office VARCHAR(255),
    registry_number VARCHAR(50),
    mersis_no VARCHAR(16),  -- MERSİS numbers are 16 digits
    company_name VARCHAR(500),
    announcement_number VARCHAR(50),

    -- Announcement classification
    announcement_type VARCHAR(100) NOT NULL,

    -- Dynamic content (JSONB for flexibility and querying)
    content JSONB NOT NULL,

    -- Optional fields
    raw_text TEXT,
    extraction_success BOOLEAN DEFAULT TRUE,

    -- Fallback extraction metadata
    is_fallback BOOLEAN DEFAULT FALSE,
    original_detected_type VARCHAR(100),
    extraction_method VARCHAR(50),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_announcement_gazette ON announcements(gazette_id);
CREATE INDEX idx_announcement_type ON announcements(announcement_type);
CREATE INDEX idx_mersis_no ON announcements(mersis_no);
CREATE INDEX idx_company_name ON announcements(company_name);
CREATE INDEX idx_registry_office ON announcements(registry_office);
CREATE INDEX idx_extraction_success ON announcements(extraction_success);
CREATE INDEX idx_is_fallback ON announcements(is_fallback);

-- GIN index for JSONB content querying
CREATE INDEX idx_content_jsonb ON announcements USING GIN (content);

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- View: All successful extractions with gazette info
CREATE VIEW v_successful_announcements AS
SELECT
    a.id,
    g.gazette_number,
    g.gazette_date,
    g.page_number,
    a.announcement_type,
    a.company_name,
    a.mersis_no,
    a.registry_office,
    a.content,
    a.created_at
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.extraction_success = TRUE
ORDER BY g.gazette_number DESC, a.id;

-- View: Fallback extractions needing review
CREATE VIEW v_fallback_extractions AS
SELECT
    a.id,
    g.gazette_number,
    g.gazette_date,
    a.company_name,
    a.original_detected_type,
    a.announcement_type AS placeholder_type,
    a.content,
    a.raw_text
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.is_fallback = TRUE
ORDER BY g.gazette_number DESC;

-- View: Statistics by announcement type
CREATE VIEW v_announcement_type_stats AS
SELECT
    announcement_type,
    COUNT(*) as total_count,
    SUM(CASE WHEN extraction_success THEN 1 ELSE 0 END) as successful_count,
    SUM(CASE WHEN is_fallback THEN 1 ELSE 0 END) as fallback_count,
    COUNT(DISTINCT gazette_id) as gazette_count
FROM announcements
GROUP BY announcement_type
ORDER BY total_count DESC;

-- View: Company activity across gazettes
CREATE VIEW v_company_activity AS
SELECT
    a.company_name,
    a.mersis_no,
    COUNT(*) as announcement_count,
    array_agg(DISTINCT a.announcement_type) as announcement_types,
    array_agg(DISTINCT g.gazette_number ORDER BY g.gazette_number) as gazette_numbers,
    MIN(g.gazette_date) as first_appearance,
    MAX(g.gazette_date) as last_appearance
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.company_name IS NOT NULL
GROUP BY a.company_name, a.mersis_no
ORDER BY announcement_count DESC;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function: Get all announcements for a specific company by MERSİS number
CREATE OR REPLACE FUNCTION get_company_announcements(p_mersis_no VARCHAR)
RETURNS TABLE (
    gazette_number INTEGER,
    gazette_date VARCHAR,
    announcement_type VARCHAR,
    content JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        g.gazette_number,
        g.gazette_date,
        a.announcement_type,
        a.content
    FROM announcements a
    JOIN gazettes g ON a.gazette_id = g.id
    WHERE a.mersis_no = p_mersis_no
    ORDER BY g.gazette_number DESC;
END;
$$ LANGUAGE plpgsql;

-- Function: Search announcements by content (JSONB query)
CREATE OR REPLACE FUNCTION search_announcements_by_content(p_search_key VARCHAR, p_search_value TEXT)
RETURNS TABLE (
    id INTEGER,
    company_name VARCHAR,
    announcement_type VARCHAR,
    content JSONB
) AS $$
BEGIN
    RETURN QUERY
    EXECUTE format('
        SELECT id, company_name, announcement_type, content
        FROM announcements
        WHERE content->>%L = %L
        ORDER BY id DESC
    ', p_search_key, p_search_value);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE gazettes IS 'Stores Turkish Trade Registry Gazette metadata';
COMMENT ON TABLE announcements IS 'Stores individual company announcements from gazettes';

COMMENT ON COLUMN announcements.content IS 'JSONB field storing type-specific announcement data (addresses, capital, mergers, etc.)';
COMMENT ON COLUMN announcements.is_fallback IS 'TRUE if this was extracted using generic fallback (unknown type)';
COMMENT ON COLUMN announcements.extraction_method IS 'Method used: structured, generic_fallback, or failed';

-- ============================================================================
-- SAMPLE QUERIES
-- ============================================================================

-- Query announcements by type
-- SELECT * FROM announcements WHERE announcement_type = 'birleşme';

-- Query merger announcements with acquiring company name
-- SELECT company_name, content->'acquiring_company'->>'name' as acquiring_company
-- FROM announcements
-- WHERE announcement_type = 'birleşme';

-- Query address changes
-- SELECT company_name,
--        content->>'old_address' as old_address,
--        content->>'new_address' as new_address
-- FROM announcements
-- WHERE announcement_type = 'adres_değişikliği';

-- Find all announcements in a specific city
-- SELECT * FROM announcements
-- WHERE content->>'city' = 'ANKARA'
--    OR content->'acquiring_company'->>'city' = 'ANKARA';

-- Get company history
-- SELECT * FROM get_company_announcements('0334053510100016');
