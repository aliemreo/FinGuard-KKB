"""
Import Gazette JSON files into PostgreSQL database

This script reads JSON files from gazette_outputs/json/ and imports them
into a PostgreSQL database following the schema defined in database_schema.sql

Requirements:
    pip install psycopg2-binary
"""

import json
import psycopg2
from psycopg2.extras import Json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Update these with your PostgreSQL credentials
DB_CONFIG = {
    'dbname': 'gazette_db',
    'user': 'postgres',
    'password': '383418',
    'host': 'localhost',
    'port': 5432
}

# ============================================================================
# IMPORT FUNCTIONS
# ============================================================================

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
        # Connect to default 'postgres' database
        conn = psycopg2.connect(
            dbname='postgres',
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port']
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Check if database exists
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

def insert_gazette(cursor, gazette_metadata: Dict[str, Any], source_file: str) -> int:
    """Insert gazette metadata and return gazette_id"""
    query = """
        INSERT INTO gazettes (gazette_number, gazette_date, page_number, source_file)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (gazette_number, page_number)
        DO UPDATE SET
            gazette_date = EXCLUDED.gazette_date,
            source_file = EXCLUDED.source_file
        RETURNING id
    """

    cursor.execute(query, (
        gazette_metadata.get('number'),
        gazette_metadata.get('date'),
        gazette_metadata.get('page'),
        source_file
    ))

    gazette_id = cursor.fetchone()[0]
    return gazette_id

def insert_announcement(cursor, gazette_id: int, announcement: Dict[str, Any]):
    """Insert a single announcement"""
    metadata = announcement.get('metadata', {})
    content = announcement.get('content', {})

    # Check if this is a fallback extraction
    is_fallback = content.get('_is_fallback', False)
    original_type = content.get('_original_detected_type')
    extraction_method = content.get('_extraction_method')

    query = """
        INSERT INTO announcements (
            gazette_id,
            registry_office,
            registry_number,
            mersis_no,
            company_name,
            announcement_number,
            announcement_type,
            content,
            raw_text,
            extraction_success,
            is_fallback,
            original_detected_type,
            extraction_method
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    cursor.execute(query, (
        gazette_id,
        metadata.get('registry_office'),
        metadata.get('registry_number'),
        metadata.get('mersis_no'),
        metadata.get('company_name'),
        metadata.get('announcement_number'),
        announcement.get('announcement_type'),
        Json(content),  # Convert dict to JSONB
        announcement.get('raw_text'),
        announcement.get('extraction_success', True),
        is_fallback,
        original_type,
        extraction_method
    ))

    announcement_id = cursor.fetchone()[0]
    return announcement_id

def import_json_file(conn, json_path: Path) -> Dict[str, int]:
    """Import a single JSON file into the database"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        cursor = conn.cursor()

        # Insert gazette metadata
        gazette_id = insert_gazette(
            cursor,
            data.get('gazette_metadata', {}),
            json_path.name
        )

        # Insert announcements
        announcements = data.get('announcements', [])
        stats = {
            'total': len(announcements),
            'successful': 0,
            'fallback': 0,
            'failed': 0
        }

        for announcement in announcements:
            announcement_id = insert_announcement(cursor, gazette_id, announcement)

            if announcement.get('extraction_success', True):
                if announcement.get('content', {}).get('_is_fallback', False):
                    stats['fallback'] += 1
                else:
                    stats['successful'] += 1
            else:
                stats['failed'] += 1

        conn.commit()
        cursor.close()

        return stats

    except Exception as e:
        print(f"[✗] Error importing {json_path.name}: {e}")
        conn.rollback()
        raise

def import_all_json_files(conn, json_dir: Path):
    """Import all JSON files from directory"""
    json_files = sorted(json_dir.glob('*.json'))

    if not json_files:
        print(f"[!] No JSON files found in {json_dir}")
        return

    print(f"\n[→] Found {len(json_files)} JSON file(s) to import\n")

    total_stats = {
        'files': 0,
        'total_announcements': 0,
        'successful': 0,
        'fallback': 0,
        'failed': 0
    }

    for idx, json_path in enumerate(json_files, 1):
        print(f"[{idx}/{len(json_files)}] Importing: {json_path.name}")

        try:
            stats = import_json_file(conn, json_path)

            print(f"    ✓ Successful:  {stats['successful']}")
            print(f"    ⚠ Fallback:    {stats['fallback']}")
            print(f"    ✗ Failed:      {stats['failed']}")
            print(f"    Total:         {stats['total']}\n")

            total_stats['files'] += 1
            total_stats['total_announcements'] += stats['total']
            total_stats['successful'] += stats['successful']
            total_stats['fallback'] += stats['fallback']
            total_stats['failed'] += stats['failed']

        except Exception as e:
            print(f"    [✗] Import failed: {e}\n")
            continue

    return total_stats

def print_database_stats(conn):
    """Print statistics about imported data"""
    cursor = conn.cursor()

    print("\n" + "="*80)
    print("DATABASE STATISTICS")
    print("="*80)

    # Total gazettes
    cursor.execute("SELECT COUNT(*) FROM gazettes")
    gazette_count = cursor.fetchone()[0]
    print(f"\nTotal Gazettes: {gazette_count}")

    # Total announcements
    cursor.execute("SELECT COUNT(*) FROM announcements")
    announcement_count = cursor.fetchone()[0]
    print(f"Total Announcements: {announcement_count}")

    # Announcements by type
    cursor.execute("""
        SELECT announcement_type, COUNT(*) as count
        FROM announcements
        GROUP BY announcement_type
        ORDER BY count DESC
    """)

    print("\nAnnouncements by Type:")
    for row in cursor.fetchall():
        print(f"  {row[0]:<30s}: {row[1]:3d}")

    # Extraction stats
    cursor.execute("""
        SELECT
            SUM(CASE WHEN extraction_success AND NOT is_fallback THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN is_fallback THEN 1 ELSE 0 END) as fallback,
            SUM(CASE WHEN NOT extraction_success THEN 1 ELSE 0 END) as failed
        FROM announcements
    """)

    row = cursor.fetchone()
    print("\nExtraction Quality:")
    print(f"  ✓ Successful: {row[0]:3d}")
    print(f"  ⚠ Fallback:   {row[1]:3d}")
    print(f"  ✗ Failed:     {row[2]:3d}")

    # Top companies by announcement count
    cursor.execute("""
        SELECT company_name, COUNT(*) as count
        FROM announcements
        WHERE company_name IS NOT NULL
        GROUP BY company_name
        ORDER BY count DESC
        LIMIT 10
    """)

    print("\nTop 10 Companies by Announcements:")
    for idx, row in enumerate(cursor.fetchall(), 1):
        company_name = row[0][:60] + '...' if len(row[0]) > 60 else row[0]
        print(f"  {idx:2d}. {company_name:<60s}: {row[1]:2d}")

    cursor.close()
    print("="*80 + "\n")

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("="*80)
    print("GAZETTE JSON → POSTGRESQL IMPORT TOOL")
    print("="*80)

    # Determine paths
    script_dir = Path(__file__).parent
    json_dir = script_dir / 'gazette_outputs' / 'json'

    if not json_dir.exists():
        print(f"[✗] JSON directory not found: {json_dir}")
        return

    print(f"\nJSON Directory: {json_dir}")
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}\n")

    # Ask for confirmation
    response = input("Initialize schema (will drop existing tables)? [y/N]: ")
    initialize_schema_flag = response.lower() == 'y'

    try:
        # Create database if needed
        create_database_if_not_exists()

        # Connect to database
        conn = connect_to_db()

        # Initialize schema if requested
        if initialize_schema_flag:
            if not initialize_schema(conn):
                print("[✗] Schema initialization failed. Aborting.")
                return

        # Import JSON files
        total_stats = import_all_json_files(conn, json_dir)

        if total_stats:
            print("\n" + "="*80)
            print("IMPORT SUMMARY")
            print("="*80)
            print(f"Files imported:       {total_stats['files']}")
            print(f"Total announcements:  {total_stats['total_announcements']}")
            print(f"  ✓ Successful:       {total_stats['successful']}")
            print(f"  ⚠ Fallback:         {total_stats['fallback']}")
            print(f"  ✗ Failed:           {total_stats['failed']}")
            print("="*80)

        # Print database statistics
        print_database_stats(conn)

        # Close connection
        conn.close()
        print("[✓] Import complete. Database connection closed.")

    except Exception as e:
        print(f"\n[✗] Import process failed: {e}")
        raise

if __name__ == "__main__":
    main()
