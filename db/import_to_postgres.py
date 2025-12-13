"""
Import Gazette JSON into PostgreSQL database

Reads from db_input folder:
  - crawl_metadata.json: Search query metadata for crawling_history
  - ilanlar.json: Array of announcements to import

Requirements:
    pip install psycopg2-binary python-dotenv
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load env from root directory (2 levels up)
root_dir = Path(__file__).parent.parent
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

import psycopg2
from psycopg2.extras import Json
from typing import Dict, Any, Optional

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'gazette_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432))
}

# Input folder path (db/db_Input/)
INPUT_DIR = Path(__file__).parent / 'db_Input'

def connect_to_db():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print(f"[✓] Connected to database: {DB_CONFIG['dbname']}")
        return conn
    except Exception as e:
        print(f"[✗] Database connection failed: {e}")
        raise

def create_database_if_not_exists():
    """Create the database if it doesn't exist"""
    try:
        conn = psycopg2.connect(
            dbname='postgres',
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port']
        )
        conn.autocommit = True
        cursor = conn.cursor()

        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_CONFIG['dbname']}'")
        exists = cursor.fetchone()

        if not exists:
            cursor.execute(f"CREATE DATABASE {DB_CONFIG['dbname']}")
            print(f"[✓] Created database: {DB_CONFIG['dbname']}")
        else:
            print(f"[→] Database already exists: {DB_CONFIG['dbname']}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[✗] Error checking/creating database: {e}")
        raise

def initialize_schema(conn):
    """Initialize database schema from SQL file"""
    try:
        schema_path = Path(__file__).parent / 'database_schema.sql'

        if not schema_path.exists():
            print(f"[✗] Schema file not found: {schema_path}")
            return False

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        cursor.close()

        print(f"[✓] Database schema initialized")
        return True
    except Exception as e:
        print(f"[✗] Schema initialization failed: {e}")
        conn.rollback()
        return False

def load_crawl_metadata() -> Optional[Dict[str, Any]]:
    """Load crawl_metadata.json from db_input folder"""
    metadata_path = INPUT_DIR / 'crawl_metadata.json'
    if not metadata_path.exists():
        print(f"[!] Warning: crawl_metadata.json not found")
        print(f"    Crawling history will NOT be recorded.")
        return None
    
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        print(f"[✓] Loaded crawl_metadata.json: {metadata.get('sirket_sorgusu', 'N/A')} (il={metadata.get('il', 'N/A')})")
        return metadata
    except Exception as e:
        print(f"[✗] Error loading crawl_metadata.json: {e}")
        return None

def load_ilanlar() -> Optional[list]:
    """Load ilanlar.json from db_input folder"""
    ilanlar_path = INPUT_DIR / 'ilanlar.json'
    if not ilanlar_path.exists():
        print(f"[✗] ilanlar.json not found in {INPUT_DIR}")
        return None
    
    try:
        with open(ilanlar_path, 'r', encoding='utf-8') as f:
            ilanlar = json.load(f)
        print(f"[✓] Loaded ilanlar.json: {len(ilanlar)} announcements")
        return ilanlar
    except Exception as e:
        print(f"[✗] Error loading ilanlar.json: {e}")
        return None

def record_crawl_history(conn, crawl_metadata: Dict[str, Any]) -> bool:
    """Insert the crawl period into crawling_history table"""
    try:
        sirket_sorgusu = crawl_metadata.get('sirket_sorgusu')
        il = crawl_metadata.get('il')
        search_period = crawl_metadata.get('search_period', {})
        start_date = search_period.get('start')
        end_date = search_period.get('end')
        
        if not all([sirket_sorgusu, il, start_date, end_date]):
            print(f"[!] Incomplete crawl metadata, skipping history record")
            return False
        
        cursor = conn.cursor()
        query = """
            INSERT INTO crawling_history (sirket_sorgusu, il, fetched_period)
            VALUES (%s, %s, daterange(%s, %s, '[)'))
        """
        cursor.execute(query, (sirket_sorgusu, il, start_date, end_date))
        conn.commit()
        cursor.close()
        
        print(f"[✓] Recorded crawl history: [{start_date}, {end_date}) for {sirket_sorgusu}")
        return True
    except Exception as e:
        print(f"[✗] Error recording crawl history: {e}")
        conn.rollback()
        return False

def insert_ilan(cursor, ilan: Dict[str, Any]) -> Optional[int]:
    """Insert a single ilan into the ilanlar table."""
    
    ilan_no = ilan.get('ilan_no')
    if not ilan_no:
        return None
    
    query = """
        INSERT INTO ilanlar (
            ticaret_sicil_no, ilan_no, ilan_turu, mersis_no, unvan, sirket_sorgusu,
            il, adres, tescil_tarihi, gazete_tarihi, gazete_sayisi, detaylar
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ilan_no) DO UPDATE SET
            ticaret_sicil_no = EXCLUDED.ticaret_sicil_no,
            ilan_turu = EXCLUDED.ilan_turu,
            mersis_no = EXCLUDED.mersis_no,
            unvan = EXCLUDED.unvan,
            sirket_sorgusu = EXCLUDED.sirket_sorgusu,
            il = EXCLUDED.il,
            adres = EXCLUDED.adres,
            tescil_tarihi = EXCLUDED.tescil_tarihi,
            gazete_tarihi = EXCLUDED.gazete_tarihi,
            gazete_sayisi = EXCLUDED.gazete_sayisi,
            detaylar = EXCLUDED.detaylar
        RETURNING id
    """

    detaylar = ilan.get('detaylar', {})
    
    cursor.execute(query, (
        ilan.get('ticaret_sicil_no'),
        ilan_no,
        ilan.get('ilan_turu', 11),
        ilan.get('mersis_no'),
        ilan.get('unvan', 'Bilinmiyor'),
        ilan.get('sirket_sorgusu', 'N/A'),
        ilan.get('il', 34),
        ilan.get('adres'),
        ilan.get('tescil_tarihi'),
        ilan.get('gazete_tarihi'),
        ilan.get('gazete_sayisi'),
        Json(detaylar) if detaylar else Json({})
    ))

    return cursor.fetchone()[0]

def import_ilanlar(conn, ilanlar: list) -> Dict[str, int]:
    """Import all ilanlar into the database"""
    cursor = conn.cursor()
    
    stats = {
        'total': len(ilanlar),
        'imported': 0,
        'skipped_no_ilan_no': 0,
        'errors': 0
    }

    for ilan in ilanlar:
        try:
            result = insert_ilan(cursor, ilan)
            if result is None:
                stats['skipped_no_ilan_no'] += 1
            else:
                stats['imported'] += 1
        except Exception as e:
            print(f"    [!] Error: {e}")
            stats['errors'] += 1

    conn.commit()
    cursor.close()
    return stats

def print_database_stats(conn):
    """Print statistics about imported data"""
    cursor = conn.cursor()

    print("\n" + "="*60)
    print("DATABASE STATISTICS")
    print("="*60)

    cursor.execute("SELECT COUNT(*) FROM ilanlar")
    print(f"\nTotal İlanlar: {cursor.fetchone()[0]}")

    cursor.execute("SELECT COUNT(*) FROM crawling_history")
    print(f"Crawl History Records: {cursor.fetchone()[0]}")

    cursor.execute("""
        SELECT ilan_turu, COUNT(*) as count
        FROM ilanlar GROUP BY ilan_turu ORDER BY count DESC
    """)

    ilan_turu_names = {
        1: 'Kuruluş', 2: 'Yönetim/Temsil', 3: 'Sermaye/Pay',
        4: 'Sözleşme/Merkez', 5: 'Yapısal Değişiklik', 6: 'Şube',
        7: 'Tasfiye', 8: 'İflas/Konkordato', 9: 'Devir',
        10: 'Çağrı/Bildirim', 11: 'Düzeltme'
    }

    print("\nİlanlar by Type:")
    for row in cursor.fetchall():
        type_name = ilan_turu_names.get(row[0], f'Unknown ({row[0]})')
        print(f"  {type_name:<25s}: {row[1]:3d}")

    cursor.close()
    print("="*60 + "\n")

def main():
    print("="*60)
    print("GAZETTE JSON → POSTGRESQL IMPORT TOOL")
    print("="*60)

    if not INPUT_DIR.exists():
        print(f"[✗] Input directory not found: {INPUT_DIR}")
        return

    print(f"\nInput Directory: {INPUT_DIR}")
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    
    # Load input files
    crawl_metadata = load_crawl_metadata()
    ilanlar = load_ilanlar()
    
    if not ilanlar:
        print("[✗] No ilanlar to import. Aborting.")
        return

    print(f"\n[!] Note: Records with null ilan_no will be skipped.\n")

    response = input("Initialize schema (will drop existing tables)? [y/N]: ")
    initialize_schema_flag = response.lower() == 'y'

    try:
        create_database_if_not_exists()
        conn = connect_to_db()

        if initialize_schema_flag:
            if not initialize_schema(conn):
                print("[✗] Schema initialization failed. Aborting.")
                return

        # Import ilanlar
        stats = import_ilanlar(conn, ilanlar)

        print("\n" + "="*60)
        print("IMPORT SUMMARY")
        print("="*60)
        print(f"Total announcements:   {stats['total']}")
        print(f"  ✓ Imported:          {stats['imported']}")
        print(f"  ⊘ Skipped (no ID):   {stats['skipped_no_ilan_no']}")
        print(f"  ✗ Errors:            {stats['errors']}")
        print("="*60)

        # Record crawl history if metadata exists and import was successful
        if crawl_metadata and stats['imported'] > 0:
            record_crawl_history(conn, crawl_metadata)

        print_database_stats(conn)

        conn.close()
        print("[✓] Import complete. Database connection closed.")

    except Exception as e:
        print(f"\n[✗] Import process failed: {e}")
        raise

if __name__ == "__main__":
    main()
