-- ============================================================================
-- EXAMPLE QUERIES FOR İLANLAR DATABASE
-- ============================================================================
-- Copy and paste these queries into psql or your SQL client
--
-- İlan Türleri (1-11):
--   1 = Kuruluş           6 = Şube
--   2 = Yönetim/Temsil    7 = Tasfiye
--   3 = Sermaye/Pay       8 = İflas/Konkordato
--   4 = Sözleşme/Merkez   9 = Devir
--   5 = Yapısal Değişiklik 10 = Çağrı/Bildirim
--                         11 = Düzeltme

-- ============================================================================
-- BASIC QUERIES
-- ============================================================================

-- 1. Get all announcements (newest first)
SELECT id, unvan, ilan_turu, mersis_no, il, gazete_tarihi
FROM ilanlar
ORDER BY gazete_tarihi DESC NULLS LAST
LIMIT 20;

-- 2. Count announcements by type
SELECT ilan_turu, COUNT(*) as count
FROM ilanlar
GROUP BY ilan_turu
ORDER BY count DESC;

-- 3. Get all announcements from a specific gazette
SELECT unvan, ilan_turu, mersis_no, detaylar
FROM ilanlar
WHERE gazete_sayisi = '10344'
ORDER BY id;

-- ============================================================================
-- FILTER BY ANNOUNCEMENT TYPE (ilan_turu)
-- ============================================================================

-- 4. Get establishment announcements (kuruluş - type 1)
SELECT unvan, mersis_no, il, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 1
ORDER BY gazete_tarihi DESC NULLS LAST
LIMIT 50;

-- 5. Get management/representation changes (yönetim/temsil - type 2)
SELECT unvan, mersis_no, il, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 2
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 6. Get capital changes (sermaye/pay - type 3)
SELECT unvan, mersis_no, il, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 3
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 7. Get address/contract changes (sözleşme/merkez - type 4)
SELECT unvan, mersis_no, il, ilce, adres, gazete_tarihi
FROM ilanlar
WHERE ilan_turu = 4
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 8. Get structural changes: mergers, splits (yapısal değişiklik - type 5)
SELECT unvan, mersis_no, il, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 5
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 9. Get branch operations (şube - type 6)
SELECT unvan, mersis_no, il, ilce, adres, gazete_tarihi
FROM ilanlar
WHERE ilan_turu = 6
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 10. Get liquidation announcements (tasfiye - type 7)
SELECT unvan, mersis_no, il, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 7
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 11. Get bankruptcy/concordato announcements (iflas/konkordato - type 8)
SELECT unvan, mersis_no, il, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 8
ORDER BY gazete_tarihi DESC NULLS LAST;

-- ============================================================================
-- FILTER BY CITY (il - plaka codes 1-81)
-- ============================================================================

-- 12. Get all announcements from Istanbul (plaka 34)
SELECT unvan, ilan_turu, mersis_no, ilce, gazete_tarihi
FROM ilanlar
WHERE il = 34
ORDER BY gazete_tarihi DESC NULLS LAST
LIMIT 50;

-- 13. Get all announcements from Ankara (plaka 6)
SELECT unvan, ilan_turu, mersis_no, ilce, gazete_tarihi
FROM ilanlar
WHERE il = 6
ORDER BY gazete_tarihi DESC NULLS LAST
LIMIT 50;

-- 14. Get all announcements from Izmir (plaka 35)
SELECT unvan, ilan_turu, mersis_no, ilce, gazete_tarihi
FROM ilanlar
WHERE il = 35
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 15. Statistics by city
SELECT il, COUNT(*) as count
FROM ilanlar
GROUP BY il
ORDER BY count DESC
LIMIT 20;

-- ============================================================================
-- COMPANY SEARCH
-- ============================================================================

-- 16. Search company by name (partial match)
SELECT id, unvan, mersis_no, ilan_turu, il, gazete_tarihi
FROM ilanlar
WHERE unvan ILIKE '%BAYKAR%'
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 17. Get all announcements for a specific MERSİS number
SELECT id, unvan, ilan_turu, gazete_tarihi, gazete_sayisi, detaylar
FROM ilanlar
WHERE mersis_no = '0334053510100016'
ORDER BY gazete_tarihi DESC NULLS LAST;

-- 18. Find companies with multiple announcements
SELECT
    unvan,
    mersis_no,
    COUNT(*) as announcement_count,
    array_agg(DISTINCT ilan_turu) as types
FROM ilanlar
GROUP BY unvan, mersis_no
HAVING COUNT(*) > 1
ORDER BY announcement_count DESC
LIMIT 20;

-- 19. Get company by registry number
SELECT id, unvan, mersis_no, ilan_turu, gazete_tarihi
FROM ilanlar
WHERE ticaret_sicil_no = '12345'
ORDER BY gazete_tarihi DESC;

-- ============================================================================
-- STATISTICS & ANALYTICS
-- ============================================================================

-- 20. Total count
SELECT COUNT(*) as total_ilanlar FROM ilanlar;

-- 21. Announcement statistics by type with names
SELECT
    ilan_turu,
    CASE ilan_turu
        WHEN 1 THEN 'Kuruluş'
        WHEN 2 THEN 'Yönetim/Temsil'
        WHEN 3 THEN 'Sermaye/Pay'
        WHEN 4 THEN 'Sözleşme/Merkez'
        WHEN 5 THEN 'Yapısal Değişiklik'
        WHEN 6 THEN 'Şube'
        WHEN 7 THEN 'Tasfiye'
        WHEN 8 THEN 'İflas/Konkordato'
        WHEN 9 THEN 'Devir'
        WHEN 10 THEN 'Çağrı/Bildirim'
        WHEN 11 THEN 'Düzeltme'
        ELSE 'Bilinmiyor'
    END as ilan_turu_adi,
    COUNT(*) as count
FROM ilanlar
GROUP BY ilan_turu
ORDER BY count DESC;

-- 22. Most active cities
SELECT
    il,
    COUNT(*) as total_announcements,
    COUNT(DISTINCT unvan) as unique_companies
FROM ilanlar
GROUP BY il
ORDER BY total_announcements DESC
LIMIT 15;

-- 23. Gazette publication volume
SELECT
    gazete_sayisi,
    gazete_tarihi,
    COUNT(*) as announcement_count
FROM ilanlar
WHERE gazete_sayisi IS NOT NULL
GROUP BY gazete_sayisi, gazete_tarihi
ORDER BY gazete_tarihi DESC NULLS LAST
LIMIT 20;

-- 24. Monthly distribution
SELECT
    DATE_TRUNC('month', gazete_tarihi) as month,
    COUNT(*) as announcement_count
FROM ilanlar
WHERE gazete_tarihi IS NOT NULL
GROUP BY month
ORDER BY month DESC;

-- 25. Type distribution by city (top 5 cities)
SELECT
    il,
    ilan_turu,
    COUNT(*) as count
FROM ilanlar
WHERE il IN (34, 6, 35, 16, 7)  -- Istanbul, Ankara, Izmir, Bursa, Antalya
GROUP BY il, ilan_turu
ORDER BY il, count DESC;

-- ============================================================================
-- ADVANCED JSONB QUERIES
-- ============================================================================

-- 26. Find all unique keys in detaylar JSONB
SELECT DISTINCT jsonb_object_keys(detaylar) as detaylar_keys
FROM ilanlar
WHERE detaylar IS NOT NULL AND detaylar != '{}'
ORDER BY detaylar_keys;

-- 27. Pretty print JSONB content for a specific announcement
SELECT
    unvan,
    jsonb_pretty(detaylar) as formatted_detaylar
FROM ilanlar
WHERE id = 1;

-- 28. Search for announcements with specific JSONB field
SELECT unvan, detaylar
FROM ilanlar
WHERE detaylar ? 'deadline_for_creditors'
ORDER BY id DESC;

-- 29. Get value from JSONB field
SELECT
    unvan,
    detaylar->>'acquiring_company' as acquiring_company,
    detaylar->>'registration_date' as registration_date
FROM ilanlar
WHERE ilan_turu = 5  -- Yapısal değişiklik
  AND detaylar ? 'acquiring_company';

-- 30. Search in nested JSONB
SELECT
    unvan,
    detaylar->'acquiring_company'->>'name' as acquiring_company_name
FROM ilanlar
WHERE detaylar->'acquiring_company'->>'name' IS NOT NULL;

-- ============================================================================
-- DATE-BASED QUERIES
-- ============================================================================

-- 31. Recent announcements (last 30 days)
SELECT id, unvan, ilan_turu, il, gazete_tarihi
FROM ilanlar
WHERE gazete_tarihi >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY gazete_tarihi DESC;

-- 32. Announcements in a date range
SELECT id, unvan, ilan_turu, il, gazete_tarihi
FROM ilanlar
WHERE gazete_tarihi BETWEEN '2024-01-01' AND '2024-12-31'
ORDER BY gazete_tarihi DESC;

-- 33. Announcements by day of week
SELECT
    EXTRACT(DOW FROM gazete_tarihi) as day_of_week,
    COUNT(*) as count
FROM ilanlar
WHERE gazete_tarihi IS NOT NULL
GROUP BY day_of_week
ORDER BY day_of_week;

-- ============================================================================
-- DATA EXPORT EXAMPLES
-- ============================================================================

-- 34. Export to CSV (run in psql)
-- \copy (SELECT unvan, mersis_no, ilan_turu, il, gazete_tarihi FROM ilanlar) TO 'ilanlar.csv' WITH CSV HEADER;

-- 35. Export specific type to CSV
-- \copy (SELECT * FROM ilanlar WHERE ilan_turu = 1) TO 'kurulus_ilanlari.csv' WITH CSV HEADER;

-- 36. Export for a specific city
-- \copy (SELECT * FROM ilanlar WHERE il = 34) TO 'istanbul_ilanlari.csv' WITH CSV HEADER;

-- ============================================================================
-- USEFUL UTILITY QUERIES
-- ============================================================================

-- 37. Database size
SELECT pg_size_pretty(pg_database_size('gazette_db')) as database_size;

-- 38. Table row count and size
SELECT
    pg_size_pretty(pg_total_relation_size('ilanlar')) as table_size,
    (SELECT COUNT(*) FROM ilanlar) as row_count;

-- 39. Index usage statistics
SELECT
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read
FROM pg_stat_user_indexes
WHERE tablename = 'ilanlar'
ORDER BY idx_scan DESC;

-- 40. Find duplicate entries (by ilan_no)
SELECT ilan_no, COUNT(*) as count
FROM ilanlar
WHERE ilan_no IS NOT NULL
GROUP BY ilan_no
HAVING COUNT(*) > 1;

-- ============================================================================
-- COMBINED FILTERS
-- ============================================================================

-- 41. Establishments in Istanbul in the last year
SELECT unvan, mersis_no, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 1
  AND il = 34
  AND gazete_tarihi >= CURRENT_DATE - INTERVAL '1 year'
ORDER BY gazete_tarihi DESC;

-- 42. Liquidations in Ankara
SELECT unvan, mersis_no, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 7
  AND il = 6
ORDER BY gazete_tarihi DESC;

-- 43. All changes for companies starting with specific letter
SELECT unvan, ilan_turu, mersis_no, gazete_tarihi
FROM ilanlar
WHERE unvan LIKE 'A%'
ORDER BY unvan, gazete_tarihi DESC;
