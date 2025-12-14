"""
JSON to PostgreSQL Importer
Imports extracted gazette JSON files into the database.
"""
import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

# Load environment variables from parent directory
env_path = Path(__file__).resolve().parent.parent / '.env'
print(f"Loading .env from: {env_path} (exists: {env_path.exists()})")
load_dotenv(dotenv_path=str(env_path), override=True)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://kkb_user@127.0.0.1:5432/kkb_db")


def parse_turkish_date(date_str: str) -> Optional[str]:
    """Parse Turkish date format to ISO date string."""
    if not date_str:
        return None
    
    turkish_months = {
        'OCAK': '01', 'ŞUBAT': '02', 'MART': '03', 'NİSAN': '04',
        'MAYIS': '05', 'HAZİRAN': '06', 'TEMMUZ': '07', 'AĞUSTOS': '08',
        'EYLÜL': '09', 'EKİM': '10', 'KASIM': '11', 'ARALIK': '12'
    }
    
    # Pattern: "13 KASIM 2025" or "2 ARALIK 2025"
    match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_str.upper())
    if match:
        day, month, year = match.groups()
        month_num = turkish_months.get(month)
        if month_num:
            return f"{year}-{month_num}-{day.zfill(2)}"
    
    return None


def extract_city_from_registry(registry_office: str) -> Optional[str]:
    """Extract city name from registry office string."""
    if not registry_office:
        return None
    
    # Pattern: "ANKARA TİCARET SİCİLİ MÜDÜRLÜĞÜ" -> "ANKARA"
    match = re.match(r'^(?:T\.?C\.?\s*)?(\w+)\s+TİCARET', registry_office.upper())
    if match:
        return match.group(1)
    return None


def import_json_file(cursor, json_path: Path, source_file: str) -> dict:
    """Import a single JSON file to the database."""
    stats = {'gazettes': 0, 'announcements': 0, 'errors': 0}
    
    try:
        data = json.loads(json_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"  ❌ Failed to read JSON: {e}")
        stats['errors'] += 1
        return stats
    
    gazette_meta = data.get('gazette_metadata', {})
    announcements = data.get('announcements', [])
    filter_settings = data.get('filter_settings', {})
    
    # Parse gazette date
    gazette_date = parse_turkish_date(gazette_meta.get('date'))
    gazette_number = gazette_meta.get('number')
    gazette_page = gazette_meta.get('page')
    
    # Insert gazette (upsert)
    gazette_id = None
    if gazette_number and gazette_page:
        cursor.execute("""
            INSERT INTO gazettes (gazette_date, gazette_number, gazette_page, source_file)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (gazette_number, gazette_page) DO UPDATE SET source_file = EXCLUDED.source_file
            RETURNING id
        """, (gazette_date, gazette_number, gazette_page, source_file))
        gazette_id = cursor.fetchone()[0]
        stats['gazettes'] += 1
    
    # Insert announcements
    for ann in announcements:
        try:
            meta = ann.get('metadata', {})
            content = ann.get('content', {})
            
            # Extract fields
            registry_office = meta.get('registry_office')
            city = extract_city_from_registry(registry_office) or filter_settings.get('city_filter')
            
            # Parse registration date from content
            reg_date = content.get('registration_date')
            if reg_date and isinstance(reg_date, str):
                # Handle various date formats
                if re.match(r'\d{4}-\d{2}-\d{2}', reg_date):
                    registration_date = reg_date
                else:
                    registration_date = parse_turkish_date(reg_date)
            else:
                registration_date = None
            
            cursor.execute("""
                INSERT INTO announcements (
                    gazette_id, registry_office, registry_number, mersis_no,
                    company_name, announcement_number, announcement_type,
                    company_address, registration_date, registered_matters,
                    changes_summary, content, extraction_success, raw_text,
                    city, company_filter, city_filter
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                gazette_id,
                registry_office,
                meta.get('registry_number'),
                meta.get('mersis_no'),
                meta.get('company_name', 'Unknown'),
                meta.get('announcement_number'),
                ann.get('announcement_type', 'unknown'),
                content.get('company_address'),
                registration_date,
                content.get('registered_matters'),
                content.get('changes_summary'),
                Json(content),
                ann.get('extraction_success', True),
                ann.get('raw_text'),
                city,
                filter_settings.get('company_filter'),
                filter_settings.get('city_filter')
            ))
            stats['announcements'] += 1
            
        except Exception as e:
            print(f"    ⚠ Failed to insert announcement: {e}")
            stats['errors'] += 1
    
    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Import gazette JSON files to PostgreSQL')
    parser.add_argument('--json-dir', type=str, default='TTSG_Agent/OCR_outputs/json',
                       help='Directory containing JSON files')
    parser.add_argument('--clear', action='store_true',
                       help='Clear existing data before import')
    args = parser.parse_args()
    
    json_dir = Path(args.json_dir)
    if not json_dir.exists():
        print(f"❌ JSON directory not found: {json_dir}")
        return
    
    json_files = list(json_dir.glob('*.json'))
    if not json_files:
        print(f"❌ No JSON files found in {json_dir}")
        return
    
    print("=" * 60)
    print("📥 JSON to PostgreSQL Importer")
    print("=" * 60)
    print(f"📂 Source: {json_dir}")
    print(f"📊 Files: {len(json_files)}")
    print(f"🔗 Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
    print()
    
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            user=os.getenv("POSTGRES_USER", "kkb_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            dbname=os.getenv("POSTGRES_DB", "kkb_db")
        )
        print(f"🔌 Connecting to {os.getenv('POSTGRES_HOST', '127.0.0.1')}:{os.getenv('POSTGRES_PORT', '5432')} as {os.getenv('POSTGRES_USER', 'kkb_user')}")
        cursor = conn.cursor()
        print("✅ Connected to database")
        
        if args.clear:
            print("🗑 Clearing existing data...")
            cursor.execute("TRUNCATE announcements, gazettes RESTART IDENTITY CASCADE")
            conn.commit()
        
        total_stats = {'gazettes': 0, 'announcements': 0, 'errors': 0}
        
        for json_file in sorted(json_files):
            print(f"\n📄 {json_file.name}")
            stats = import_json_file(cursor, json_file, json_file.name)
            
            for key in total_stats:
                total_stats[key] += stats[key]
            
            print(f"   ✅ +{stats['announcements']} announcements")
        
        conn.commit()
        
        print("\n" + "=" * 60)
        print("📊 IMPORT COMPLETE")
        print("=" * 60)
        print(f"  Gazettes imported:      {total_stats['gazettes']}")
        print(f"  Announcements imported: {total_stats['announcements']}")
        if total_stats['errors'] > 0:
            print(f"  ⚠ Errors:              {total_stats['errors']}")
        print("=" * 60)
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        return


if __name__ == "__main__":
    main()
