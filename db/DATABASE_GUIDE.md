# PostgreSQL Database Guide

This guide explains how to set up and use the PostgreSQL database for storing Turkish Trade Registry Gazette data.

## Database Schema

### Tables

#### 1. `gazettes`
Stores gazette metadata (one row per gazette page).

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| gazette_number | INTEGER | Gazette issue number |
| gazette_date | VARCHAR(100) | Publication date (Turkish format) |
| page_number | INTEGER | Page number |
| source_file | VARCHAR(255) | Original JSON filename |
| processed_at | TIMESTAMP | Import timestamp |

#### 2. `announcements`
Stores individual company announcements.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| gazette_id | INTEGER | Foreign key to gazettes |
| registry_office | VARCHAR(255) | Trade registry office |
| registry_number | VARCHAR(50) | Registry number |
| mersis_no | VARCHAR(16) | MERSİS identification number |
| company_name | VARCHAR(500) | Company name |
| announcement_number | VARCHAR(50) | Announcement number |
| announcement_type | VARCHAR(100) | Type (merger, address change, etc.) |
| **content** | **JSONB** | **Type-specific data (flexible)** |
| raw_text | TEXT | Original OCR text (if available) |
| extraction_success | BOOLEAN | Extraction succeeded? |
| is_fallback | BOOLEAN | Used fallback extractor? |
| original_detected_type | VARCHAR(100) | Original type (if fallback) |
| extraction_method | VARCHAR(50) | Extraction method used |
| created_at | TIMESTAMP | Import timestamp |

## Setup Instructions

### 1. Install PostgreSQL

**Windows:**
```bash
# Download from: https://www.postgresql.org/download/windows/
# Or use chocolatey:
choco install postgresql
```

**Linux:**
```bash
sudo apt-get install postgresql postgresql-contrib
```

**macOS:**
```bash
brew install postgresql
```

### 2. Install Python Dependencies

```bash
pip install psycopg2-binary
```

### 3. Configure Database

Edit `import_to_postgres.py` and update database credentials:

```python
DB_CONFIG = {
    'dbname': 'gazette_db',
    'user': 'postgres',
    'password': 'your_password',  # ← Change this
    'host': 'localhost',
    'port': 5432
}
```

### 4. Initialize Database

Run the import script with schema initialization:

```bash
python import_to_postgres.py
```

When prompted, type `y` to initialize the schema:
```
Initialize schema (will drop existing tables)? [y/N]: y
```

This will:
1. Create database `gazette_db` if it doesn't exist
2. Create tables (`gazettes`, `announcements`)
3. Create indexes for performance
4. Create views for common queries
5. Import all JSON files from `gazette_outputs/json/`

## Usage Examples

### Connect to Database

```bash
# Using psql command-line tool
psql -U postgres -d gazette_db
```

### Basic Queries

#### 1. View All Announcements
```sql
SELECT * FROM v_successful_announcements
ORDER BY gazette_number DESC
LIMIT 10;
```

#### 2. Find Company by MERSİS Number
```sql
SELECT * FROM get_company_announcements('0334053510100016');
```

#### 3. Get Merger Announcements
```sql
SELECT
    company_name,
    content->'acquiring_company'->>'name' as acquiring_company,
    content->'acquired_company'->>'name' as acquired_company,
    content->>'registration_date' as registration_date
FROM announcements
WHERE announcement_type = 'birleşme'
ORDER BY id DESC;
```

#### 4. Get Address Changes
```sql
SELECT
    company_name,
    mersis_no,
    content->>'old_address' as old_address,
    content->>'new_address' as new_address,
    content->>'change_date' as change_date
FROM announcements
WHERE announcement_type = 'adres_değişikliği'
ORDER BY id DESC;
```

#### 5. Find Companies in a Specific City
```sql
SELECT DISTINCT
    company_name,
    mersis_no,
    announcement_type
FROM announcements
WHERE content->>'city' = 'ANKARA'
   OR content->'acquiring_company'->>'city' = 'ANKARA'
   OR content->'acquired_company'->>'city' = 'ANKARA';
```

#### 6. Get Compound Changes
```sql
SELECT
    company_name,
    content->>'registered_matters' as registered_matters,
    content->>'old_address' as old_address,
    content->>'new_address' as new_address,
    content->>'old_capital' as old_capital,
    content->>'new_capital' as new_capital
FROM announcements
WHERE announcement_type = 'bileşik_değişiklik'
ORDER BY id DESC;
```

#### 7. Search by Company Name
```sql
SELECT
    a.company_name,
    a.announcement_type,
    g.gazette_number,
    g.gazette_date,
    a.content
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
WHERE a.company_name ILIKE '%BAYKAR%'
ORDER BY g.gazette_number DESC;
```

#### 8. View Fallback Extractions (Unknown Types)
```sql
SELECT * FROM v_fallback_extractions;
```

#### 9. Get Statistics by Announcement Type
```sql
SELECT * FROM v_announcement_type_stats;
```

#### 10. Company Activity Over Time
```sql
SELECT * FROM v_company_activity
WHERE announcement_count > 1
ORDER BY announcement_count DESC;
```

### Advanced JSONB Queries

#### 1. Search for Specific Capital Amount
```sql
SELECT company_name, content
FROM announcements
WHERE announcement_type = 'bileşik_değişiklik'
  AND content->'new_capital'->>'amount' IS NOT NULL
  AND (content->'new_capital'->>'amount')::NUMERIC > 1000000;
```

#### 2. Find All Shareholders
```sql
SELECT
    company_name,
    jsonb_array_elements(content->'shareholders')->>'name' as shareholder_name
FROM announcements
WHERE content ? 'shareholders'
ORDER BY company_name;
```

#### 3. Search by Notary Info
```sql
SELECT company_name, content
FROM announcements
WHERE content->'notary_info'->>'notary_name' ILIKE '%Beyoğlu%';
```

#### 4. Get All Announcements with Specific Field
```sql
-- Find all announcements that have a 'deadline_for_creditors' field
SELECT company_name, content->>'deadline_for_creditors' as deadline
FROM announcements
WHERE content ? 'deadline_for_creditors';
```

### Export Data

#### 1. Export to CSV
```sql
\copy (SELECT company_name, mersis_no, announcement_type FROM announcements) TO 'announcements.csv' WITH CSV HEADER;
```

#### 2. Export Specific Type to JSON
```sql
\copy (SELECT row_to_json(t) FROM (SELECT * FROM announcements WHERE announcement_type = 'birleşme') t) TO 'mergers.json';
```

## Views Reference

### 1. `v_successful_announcements`
All successfully extracted announcements with gazette info.

```sql
SELECT * FROM v_successful_announcements;
```

### 2. `v_fallback_extractions`
Announcements extracted using generic fallback (unknown types).

```sql
SELECT * FROM v_fallback_extractions;
```

### 3. `v_announcement_type_stats`
Statistics grouped by announcement type.

```sql
SELECT * FROM v_announcement_type_stats;
```

### 4. `v_company_activity`
Company activity summary across all gazettes.

```sql
SELECT * FROM v_company_activity
WHERE company_name ILIKE '%ENERGY%';
```

## Functions Reference

### 1. `get_company_announcements(mersis_no)`
Get all announcements for a specific company.

```sql
SELECT * FROM get_company_announcements('0334053510100016');
```

### 2. `search_announcements_by_content(key, value)`
Search announcements by JSONB content field.

```sql
SELECT * FROM search_announcements_by_content('city', 'ANKARA');
```

## Performance Tips

1. **Use Indexes**: All common query fields are indexed
2. **JSONB Queries**: Use `->>` for text, `->` for JSON objects
3. **GIN Index**: The `content` JSONB column has a GIN index for fast searches
4. **Views**: Use pre-defined views for common queries

## Data Analysis Examples

### 1. Most Active Companies
```sql
SELECT company_name, COUNT(*) as announcement_count
FROM announcements
WHERE company_name IS NOT NULL
GROUP BY company_name
HAVING COUNT(*) > 1
ORDER BY announcement_count DESC
LIMIT 20;
```

### 2. Announcements by Month
```sql
SELECT
    DATE_TRUNC('month', created_at) as month,
    COUNT(*) as announcement_count
FROM announcements
GROUP BY month
ORDER BY month DESC;
```

### 3. Registry Office Activity
```sql
SELECT
    registry_office,
    COUNT(*) as total_announcements,
    COUNT(DISTINCT company_name) as unique_companies
FROM announcements
GROUP BY registry_office
ORDER BY total_announcements DESC;
```

### 4. Extraction Quality Report
```sql
SELECT
    g.source_file,
    COUNT(*) as total,
    SUM(CASE WHEN a.extraction_success AND NOT a.is_fallback THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN a.is_fallback THEN 1 ELSE 0 END) as fallback,
    SUM(CASE WHEN NOT a.extraction_success THEN 1 ELSE 0 END) as failed
FROM announcements a
JOIN gazettes g ON a.gazette_id = g.id
GROUP BY g.source_file
ORDER BY g.source_file;
```

## Maintenance

### Re-import Updated Data

To re-import after fixing extraction issues:

```bash
# 1. Drop and recreate schema
python import_to_postgres.py
# → Answer 'y' when prompted

# 2. Or manually clear data
psql -U postgres -d gazette_db -c "TRUNCATE announcements, gazettes CASCADE;"
```

### Backup Database

```bash
# Backup entire database
pg_dump -U postgres gazette_db > gazette_db_backup.sql

# Restore from backup
psql -U postgres gazette_db < gazette_db_backup.sql
```

### Check Database Size

```sql
SELECT
    pg_size_pretty(pg_database_size('gazette_db')) as database_size;
```

## Troubleshooting

### Connection Issues

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql  # Linux
brew services list                 # macOS

# Start PostgreSQL
sudo systemctl start postgresql    # Linux
brew services start postgresql     # macOS
```

### Permission Issues

```bash
# Grant user permissions
psql -U postgres
CREATE USER your_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE gazette_db TO your_user;
```

### JSONB Query Issues

```sql
-- Check JSONB structure
SELECT jsonb_pretty(content) FROM announcements LIMIT 1;

-- List all keys in content
SELECT DISTINCT jsonb_object_keys(content) FROM announcements;
```

## Next Steps

After importing data, you can:

1. **Build dashboards** - Connect Power BI, Tableau, or Grafana
2. **Create APIs** - Build REST APIs using Flask/FastAPI
3. **Data analysis** - Use Python with pandas + SQLAlchemy
4. **Reports** - Generate automated reports with SQL queries
5. **Monitoring** - Track new announcements and changes over time

## Example Python Integration

```python
import psycopg2
import pandas as pd

# Connect
conn = psycopg2.connect(
    dbname='gazette_db',
    user='postgres',
    password='your_password',
    host='localhost'
)

# Query to DataFrame
df = pd.read_sql_query("""
    SELECT
        a.company_name,
        a.announcement_type,
        g.gazette_date,
        a.content
    FROM announcements a
    JOIN gazettes g ON a.gazette_id = g.id
    WHERE a.announcement_type = 'birleşme'
""", conn)

print(df)
conn.close()
```
