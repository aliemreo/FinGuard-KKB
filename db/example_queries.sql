-- ============================================================================
-- EXAMPLE QUERIES FOR GAZETTE DATABASE
-- ============================================================================
-- Copy and paste these queries into psql or your SQL client

-- ============================================================================
-- BASIC QUERIES
-- ============================================================================

-- 1. Get all announcements (with gazette info)
SELECT * FROM v_successful_announcements
ORDER BY gazette_number DESC
LIMIT 10;

-- 2. Count announcements by type
SELECT announcement_type, COUNT(*) as count
FROM announcements
GROUP BY announcement_type
ORDER BY count DESC;

-- 3. Get all announcements from a specific gazette
SELECT a.company_name, a.announcement_type, a.content
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE g.gazette_number = 10344
ORDER BY a.id;

-- ============================================================================
-- MERGER ANNOUNCEMENTS (birleşme)
-- ============================================================================

-- 4. Get all merger announcements with company details
SELECT
    a.company_name as announced_by,
    a.content->'acquiring_company'->>'name' as acquiring_company,
    a.content->'acquired_company'->>'name' as acquired_company,
    a.content->>'registration_date' as registration_date,
    a.content->>'deadline_for_creditors' as creditor_deadline,
    g.gazette_number,
    g.gazette_date
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.announcement_type = 'birleşme'
ORDER BY g.gazette_number DESC;

-- 5. Find mergers in a specific city
SELECT
    a.company_name,
    a.content->'acquiring_company'->>'name' as acquiring_company,
    a.content->'acquiring_company'->>'city' as city
FROM announcements a
WHERE a.announcement_type = 'birleşme'
  AND a.content->'acquiring_company'->>'city' = 'ANKARA';

-- ============================================================================
-- ADDRESS CHANGES (adres_değişikliği)
-- ============================================================================

-- 6. Get all address changes with old and new addresses
SELECT
    a.company_name,
    a.mersis_no,
    a.content->>'old_address' as old_address,
    a.content->>'new_address' as new_address,
    a.content->>'change_date' as change_date,
    g.gazette_number
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.announcement_type = 'adres_değişikliği'
ORDER BY g.gazette_number DESC;

-- 7. Find companies that moved to a specific district
SELECT
    company_name,
    content->>'new_address' as new_address
FROM announcements
WHERE announcement_type = 'adres_değişikliği'
  AND content->>'new_address' ILIKE '%Çankaya%';

-- ============================================================================
-- COMPOUND CHANGES (bileşik_değişiklik)
-- ============================================================================

-- 8. Get all compound changes with details
SELECT
    a.company_name,
    a.content->>'registered_matters' as registered_matters,
    a.content->>'new_address' as new_address,
    a.content->>'new_capital' as new_capital,
    g.gazette_number
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.announcement_type = 'bileşik_değişiklik'
ORDER BY g.gazette_number DESC;

-- 9. Find capital increases in compound changes
SELECT
    company_name,
    content->>'old_capital' as old_capital,
    content->>'new_capital' as new_capital,
    content->'new_capital'->>'amount' as new_capital_amount
FROM announcements
WHERE announcement_type = 'bileşik_değişiklik'
  AND content ? 'new_capital'
  AND content->'new_capital' IS NOT NULL;

-- ============================================================================
-- BRANCH ESTABLISHMENTS (şube_kuruluşu)
-- ============================================================================

-- 10. Get all branch establishments
SELECT
    a.company_name,
    a.content->>'branch_name' as branch_name,
    a.content->>'branch_address' as branch_address,
    g.gazette_number
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.announcement_type = 'şube_kuruluşu'
ORDER BY g.gazette_number DESC;

-- ============================================================================
-- COMPANY SEARCH
-- ============================================================================

-- 11. Search company by name (partial match)
SELECT
    a.company_name,
    a.mersis_no,
    a.announcement_type,
    g.gazette_number,
    g.gazette_date
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.company_name ILIKE '%BAYKAR%'
ORDER BY g.gazette_number DESC;

-- 12. Get all announcements for a specific MERSİS number
SELECT * FROM get_company_announcements('0334053510100016');

-- 13. Find companies with multiple announcements
SELECT
    company_name,
    mersis_no,
    COUNT(*) as announcement_count,
    array_agg(DISTINCT announcement_type) as types
FROM announcements
WHERE company_name IS NOT NULL
GROUP BY company_name, mersis_no
HAVING COUNT(*) > 1
ORDER BY announcement_count DESC;

-- ============================================================================
-- STATISTICS & ANALYTICS
-- ============================================================================

-- 14. Announcement statistics by type
SELECT * FROM v_announcement_type_stats;

-- 15. Most active companies
SELECT * FROM v_company_activity
ORDER BY announcement_count DESC
LIMIT 20;

-- 16. Registry office activity
SELECT
    registry_office,
    COUNT(*) as total_announcements,
    COUNT(DISTINCT company_name) as unique_companies,
    COUNT(DISTINCT announcement_type) as announcement_types
FROM announcements
WHERE registry_office IS NOT NULL
GROUP BY registry_office
ORDER BY total_announcements DESC;

-- 17. Gazette publication volume
SELECT
    gazette_number,
    gazette_date,
    COUNT(*) as announcement_count
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
GROUP BY gazette_number, gazette_date
ORDER BY gazette_number DESC;

-- ============================================================================
-- EXTRACTION QUALITY
-- ============================================================================

-- 18. View fallback extractions (unknown types)
SELECT * FROM v_fallback_extractions;

-- 19. Extraction quality summary
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN extraction_success AND NOT is_fallback THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN is_fallback THEN 1 ELSE 0 END) as fallback,
    SUM(CASE WHEN NOT extraction_success THEN 1 ELSE 0 END) as failed,
    ROUND(100.0 * SUM(CASE WHEN extraction_success AND NOT is_fallback THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM announcements;

-- 20. Quality by source file
SELECT
    g.source_file,
    COUNT(*) as total,
    SUM(CASE WHEN a.extraction_success AND NOT a.is_fallback THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN a.is_fallback THEN 1 ELSE 0 END) as fallback
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
GROUP BY g.source_file
ORDER BY g.source_file;

-- ============================================================================
-- ADVANCED JSONB QUERIES
-- ============================================================================

-- 21. Find all unique keys in content JSONB
SELECT DISTINCT jsonb_object_keys(content) as content_keys
FROM announcements
ORDER BY content_keys;

-- 22. Pretty print JSONB content for a specific announcement
SELECT
    company_name,
    jsonb_pretty(content) as formatted_content
FROM announcements
WHERE id = 1;

-- 23. Search for announcements with specific JSONB field
SELECT company_name, content
FROM announcements
WHERE content ? 'deadline_for_creditors'  -- Has this field
ORDER BY id DESC;

-- 24. Extract shareholders from compound changes
SELECT
    company_name,
    jsonb_array_elements(content->'shareholders')->>'name' as shareholder_name,
    jsonb_array_elements(content->'shareholders')->>'shares' as shares
FROM announcements
WHERE content ? 'shareholders'
  AND jsonb_typeof(content->'shareholders') = 'array';

-- 25. Search by notary information
SELECT
    company_name,
    content->'notary_info'->>'notary_name' as notary,
    content->'notary_info'->>'document_date' as document_date
FROM announcements
WHERE content->'notary_info' IS NOT NULL
  AND content->'notary_info'->>'notary_name' ILIKE '%Beyoğlu%';

-- ============================================================================
-- TIME-BASED QUERIES
-- ============================================================================

-- 26. Announcements imported today
SELECT COUNT(*) FROM announcements
WHERE DATE(created_at) = CURRENT_DATE;

-- 27. Import timeline
SELECT
    DATE(created_at) as import_date,
    COUNT(*) as announcements_imported
FROM announcements
GROUP BY DATE(created_at)
ORDER BY import_date DESC;

-- ============================================================================
-- DATA EXPORT EXAMPLES
-- ============================================================================

-- 28. Export mergers to CSV (run in psql)
-- \copy (SELECT company_name, content->'acquiring_company'->>'name' as acquiring_company, content->>'registration_date' as registration_date FROM announcements WHERE announcement_type = 'birleşme') TO 'mergers.csv' WITH CSV HEADER;

-- 29. Export all announcements for a company
-- \copy (SELECT * FROM get_company_announcements('0334053510100016')) TO 'company_announcements.csv' WITH CSV HEADER;

-- ============================================================================
-- USEFUL UTILITY QUERIES
-- ============================================================================

-- 30. Database size
SELECT pg_size_pretty(pg_database_size('gazette_db')) as database_size;

-- 31. Table row counts
SELECT
    'gazettes' as table_name,
    COUNT(*) as row_count
FROM gazettes
UNION ALL
SELECT
    'announcements' as table_name,
    COUNT(*) as row_count
FROM announcements;

-- 32. Index usage statistics
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
