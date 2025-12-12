# PostgreSQL Database Guide

This guide explains how to set up and use the PostgreSQL database for storing Turkish Trade Registry Gazette data.

## Database Schema

### Table: `ilanlar`

A single table storing all gazette announcements.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| ticaret_sicil_no | VARCHAR(50) | Trade registry number |
| ilan_no | VARCHAR(50) | Unique announcement number |
| ilan_turu | SMALLINT | Announcement type (1-11) |
| mersis_no | VARCHAR(16) | MERSİS identification number |
| unvan | VARCHAR(500) | Company name |
| il | SMALLINT | City code (plaka: 1-81) |
| ilce | VARCHAR(100) | District |
| adres | TEXT | Address |
| tescil_tarihi | DATE | Registration date |
| gazete_tarihi | DATE | Gazette publication date |
| gazete_sayisi | VARCHAR(20) | Gazette issue number |
| detaylar | JSONB | Additional details (flexible) |

### İlan Türleri (Announcement Types)

| Code | Category | Description |
|------|----------|-------------|
| 1 | Kuruluş | Yeni Şirket/İşletme Açılışı |
| 2 | Yönetim/Temsil | Müdür/YK Atama, İmza Yetkisi, İç Yönerge |
| 3 | Sermaye/Pay | Sermaye Artırımı/Azaltımı, Hisse Devri |
| 4 | Sözleşme/Merkez | Adres Değişikliği, Unvan Değişikliği, Tadil |
| 5 | Yapısal Değişiklik | Birleşme, Bölünme, Tür Değiştirme |
| 6 | Şube | Şube Açılış/Kapanış |
| 7 | Tasfiye | Tasfiyeye Giriş, Tasfiye Sonu |
| 8 | İflas/Konkordato | İflas Kararı, Konkordato Mühleti |
| 9 | Devir | İşletme Devri |
| 10 | Çağrı/Bildirim | Genel Kurul Çağrısı, Alacaklılara Çağrı |
| 11 | Düzeltme | Hatalı İlan Düzeltmesi |

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
pip install -r requirements_database.txt
```

### 3. Configure Database

Create a `.env` file in the project root with your database credentials:

```env
DB_NAME=gazette_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

### 4. Initialize Database

Run the import script with schema initialization:

```bash
python import_to_postgres.py
```

When prompted, type `y` to initialize the schema:
```
Initialize schema (will drop existing table)? [y/N]: y
```

This will:
1. Create database `gazette_db` if it doesn't exist
2. Create the `ilanlar` table and indexes
3. Import all JSON files from the configured directory

## Usage Examples

### Connect to Database

```bash
# Using psql command-line tool
psql -U postgres -d gazette_db

# Or use the provided batch file (Windows)
connect_db.bat
```

### Basic Queries

#### 1. View All Announcements
```sql
SELECT * FROM ilanlar
ORDER BY gazete_tarihi DESC NULLS LAST
LIMIT 10;
```

#### 2. Find Company by MERSİS Number
```sql
SELECT * FROM ilanlar
WHERE mersis_no = '0334053510100016'
ORDER BY gazete_tarihi DESC;
```

#### 3. Get Announcements by Type
```sql
-- Get all establishment announcements (kuruluş)
SELECT unvan, mersis_no, gazete_tarihi
FROM ilanlar
WHERE ilan_turu = 1
ORDER BY gazete_tarihi DESC;

-- Get all mergers (yapısal değişiklik)
SELECT unvan, mersis_no, gazete_tarihi, detaylar
FROM ilanlar
WHERE ilan_turu = 5
ORDER BY gazete_tarihi DESC;
```

#### 4. Get Announcements by City
```sql
-- Get all announcements from Istanbul (plaka 34)
SELECT unvan, ilan_turu, gazete_tarihi
FROM ilanlar
WHERE il = 34
ORDER BY gazete_tarihi DESC;

-- Get all announcements from Ankara (plaka 6)
SELECT unvan, ilan_turu, gazete_tarihi
FROM ilanlar
WHERE il = 6
ORDER BY gazete_tarihi DESC;
```

#### 5. Search by Company Name
```sql
SELECT unvan, mersis_no, ilan_turu, gazete_tarihi
FROM ilanlar
WHERE unvan ILIKE '%BAYKAR%'
ORDER BY gazete_tarihi DESC;
```

#### 6. Get Statistics by Type
```sql
SELECT ilan_turu, COUNT(*) as count
FROM ilanlar
GROUP BY ilan_turu
ORDER BY count DESC;
```

#### 7. Get Statistics by City
```sql
SELECT il, COUNT(*) as count
FROM ilanlar
GROUP BY il
ORDER BY count DESC
LIMIT 20;
```

### Advanced JSONB Queries

#### 1. Search in detaylar JSONB
```sql
-- Find announcements with specific field in detaylar
SELECT unvan, detaylar
FROM ilanlar
WHERE detaylar ? 'deadline_for_creditors';

-- Pretty print JSONB content
SELECT unvan, jsonb_pretty(detaylar)
FROM ilanlar
WHERE id = 1;
```

#### 2. List All Keys in detaylar
```sql
SELECT DISTINCT jsonb_object_keys(detaylar) as keys
FROM ilanlar
ORDER BY keys;
```

### Export Data

#### 1. Export to CSV
```sql
\copy (SELECT unvan, mersis_no, ilan_turu, il, gazete_tarihi FROM ilanlar) TO 'ilanlar.csv' WITH CSV HEADER;
```

#### 2. Export Specific Type to JSON
```sql
\copy (SELECT row_to_json(t) FROM (SELECT * FROM ilanlar WHERE ilan_turu = 5) t) TO 'yapisal_degisiklik.json';
```

## Python Query Interface

Use the provided `query_db.py` for easy querying:

```bash
# Interactive menu
python query_db.py

# Command line options
python query_db.py --all --limit 20
python query_db.py --type 1                # Filter by type
python query_db.py --city 34              # Filter by city
python query_db.py --company "BAYKAR"     # Search company
python query_db.py --mersis "0334053510100016"
python query_db.py --stats                # Statistics by type
python query_db.py --stats-city           # Statistics by city
python query_db.py --recent 30            # Last 30 days
```

## Data Analysis Examples

### 1. Most Active Companies
```sql
SELECT unvan, COUNT(*) as announcement_count
FROM ilanlar
GROUP BY unvan
HAVING COUNT(*) > 1
ORDER BY announcement_count DESC
LIMIT 20;
```

### 2. Announcements by Month
```sql
SELECT
    DATE_TRUNC('month', gazete_tarihi) as month,
    COUNT(*) as announcement_count
FROM ilanlar
WHERE gazete_tarihi IS NOT NULL
GROUP BY month
ORDER BY month DESC;
```

### 3. Type Distribution by City
```sql
SELECT
    il,
    ilan_turu,
    COUNT(*) as count
FROM ilanlar
GROUP BY il, ilan_turu
ORDER BY il, count DESC;
```

## Maintenance

### Re-import Updated Data

```bash
# Drop and recreate schema
python import_to_postgres.py
# → Answer 'y' when prompted

# Or manually clear data
psql -U postgres -d gazette_db -c "TRUNCATE ilanlar CASCADE;"
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
SELECT pg_size_pretty(pg_database_size('gazette_db')) as database_size;

SELECT COUNT(*) as total_ilanlar FROM ilanlar;
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

```sql
-- Grant user permissions
CREATE USER your_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE gazette_db TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
```

### JSONB Query Issues

```sql
-- Check JSONB structure
SELECT jsonb_pretty(detaylar) FROM ilanlar LIMIT 1;

-- List all keys in detaylar
SELECT DISTINCT jsonb_object_keys(detaylar) FROM ilanlar;
```

## Example Python Integration

```python
import psycopg2
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()

# Connect
conn = psycopg2.connect(
    dbname=os.getenv('DB_NAME', 'gazette_db'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD'),
    host=os.getenv('DB_HOST', 'localhost')
)

# Query to DataFrame
df = pd.read_sql_query("""
    SELECT
        unvan,
        ilan_turu,
        mersis_no,
        il,
        gazete_tarihi,
        detaylar
    FROM ilanlar
    WHERE ilan_turu = 5  -- Yapısal değişiklik (birleşme, bölünme)
    ORDER BY gazete_tarihi DESC
    LIMIT 100
""", conn)

print(df)
conn.close()
```
