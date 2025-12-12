"""
Import Gazette JSON files into PostgreSQL database

This script reads JSON files from gazette_outputs/json/ and imports them
into a PostgreSQL database following the schema defined in database_schema.sql

Requirements:
    pip install psycopg2-binary python-dotenv
"""

import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv

# Load env from root directory (2 levels up)
root_dir = Path(__file__).parent.parent
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from typing import Dict, Any, Optional

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'gazette_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432))
}

ILAN_TURU_MAP = {
    # 1 = Kuruluş
    'kuruluş': 1, 'kurulus': 1, 'yeni_kayit': 1, 'açılış': 1,
    # 2 = Yönetim/Temsil
    'yönetim': 2, 'temsil': 2, 'müdür_atama': 2, 'imza_yetkisi': 2, 'iç_yönerge': 2,
    # 3 = Sermaye/Pay
    'sermaye': 3, 'sermaye_artırımı': 3, 'sermaye_azaltımı': 3, 'pay_devri': 3,
    # 4 = Sözleşme/Merkez
    'adres_değişikliği': 4, 'unvan_değişikliği': 4, 'merkez_nakli': 4, 'tadil': 4,
    'bileşik_değişiklik': 4,
    # 5 = Yapısal Değişiklik
    'birleşme': 5, 'bölünme': 5, 'tür_değiştirme': 5, 'yapısal_değişiklik': 5,
    # 6 = Şube
    'şube': 6, 'şube_açılış': 6, 'şube_kapanış': 6, 'şube_kuruluşu': 6,
    # 7 = Tasfiye
    'tasfiye': 7, 'tasfiyeye_giriş': 7, 'tasfiye_sonu': 7, 'sona_erme': 7,
    # 8 = İflas/Konkordato
    'iflas': 8, 'konkordato': 8, 'iflas_kararı': 8, 'konkordato_mühleti': 8,
    # 9 = Devir
    'devir': 9, 'işletme_devri': 9,
    # 10 = Çağrı/Bildirim
    'genel_kurul': 10, 'çağrı': 10, 'bildirim': 10, 'alacaklılara_çağrı': 10,
    'toplantı_çağrısı': 10,
    # 11 = Düzeltme
    'düzeltme': 11, 'ilan_düzeltme': 11,
}

TURKISH_MONTHS = {
    'OCAK': 1, 'ŞUBAT': 2, 'MART': 3, 'NİSAN': 4, 'NISAN': 4,
    'MAYIS': 5, 'HAZİRAN': 6, 'HAZIRAN': 6, 'TEMMUZ': 7, 'AĞUSTOS': 8, 'AGUSTOS': 8,
    'EYLÜL': 9, 'EYLUL': 9, 'EKİM': 10, 'EKIM': 10, 'KASIM': 11, 'ARALIK': 12
}

IL_KODLARI = {
    'adana': 1, 'adıyaman': 2, 'afyon': 3, 'afyonkarahisar': 3, 'ağrı': 4,
    'amasya': 5, 'ankara': 6, 'antalya': 7, 'artvin': 8, 'aydın': 9,
    'balıkesir': 10, 'bilecik': 11, 'bingöl': 12, 'bitlis': 13, 'bolu': 14,
    'burdur': 15, 'bursa': 16, 'çanakkale': 17, 'çankırı': 18, 'çorum': 19,
    'denizli': 20, 'diyarbakır': 21, 'edirne': 22, 'elazığ': 23, 'erzincan': 24,
    'erzurum': 25, 'eskişehir': 26, 'gaziantep': 27, 'giresun': 28, 'gümüşhane': 29,
    'hakkari': 30, 'hatay': 31, 'isparta': 32, 'mersin': 33, 'içel': 33,
    'istanbul': 34, 'İstanbul': 34, 'izmir': 35, 'İzmir': 35, 'kars': 36, 
    'kastamonu': 37, 'kayseri': 38, 'kırklareli': 39, 'kırşehir': 40, 
    'kocaeli': 41, 'konya': 42, 'kütahya': 43, 'malatya': 44, 'manisa': 45, 
    'kahramanmaraş': 46, 'mardin': 47, 'muğla': 48, 'muş': 49, 'nevşehir': 50, 
    'niğde': 51, 'ordu': 52, 'rize': 53, 'sakarya': 54, 'samsun': 55, 
    'siirt': 56, 'sinop': 57, 'sivas': 58, 'tekirdağ': 59, 'tokat': 60, 
    'trabzon': 61, 'tunceli': 62, 'şanlıurfa': 63, 'uşak': 64, 'van': 65, 
    'yozgat': 66, 'zonguldak': 67, 'aksaray': 68, 'bayburt': 69, 'karaman': 70, 
    'kırıkkale': 71, 'batman': 72, 'şırnak': 73, 'bartın': 74, 'ardahan': 75, 
    'iğdır': 76, 'yalova': 77, 'karabük': 78, 'kilis': 79, 'osmaniye': 80, 
    'düzce': 81
}

def get_ilan_turu_code(announcement_type: str) -> int:
    """Convert announcement type string to SMALLINT code (1-11)"""
    if not announcement_type:
        return 11
    normalized = announcement_type.lower().strip().replace(' ', '_')
    return ILAN_TURU_MAP.get(normalized, 11)

def get_il_code(city_name: str) -> int:
    """Convert city name to plaka code (1-81)"""
    if not city_name:
        return 34  # Default to Istanbul
    normalized = city_name.lower().strip()
    return IL_KODLARI.get(normalized, 34)

def extract_city_from_registry_office(registry_office: str) -> str:
    """Extract city name from registry office string like 'T.C. İSTANBUL TİCARET SİCİLİ MÜDÜRLÜĞÜ'"""
    if not registry_office:
        return ''
    
    # Remove common prefixes
    text = registry_office.upper()
    text = re.sub(r'^T\.?C\.?\s*', '', text)  # Remove T.C. prefix
    
    # Try to find a known city name
    for city in IL_KODLARI.keys():
        city_upper = city.upper()
        if city_upper in text:
            return city
    
    # Fallback: take first word
    words = text.split()
    if words:
        return words[0].lower()
    return ''

def parse_turkish_date(date_str: str) -> Optional[str]:
    """Parse Turkish date format like '30 EKIM 2024' to 'YYYY-MM-DD'"""
    if not date_str:
        return None
    
    # Try pattern: "DD MONTH YYYY"
    match = re.match(r'(\d{1,2})\s+([A-ZÇĞİÖŞÜa-zçğıöşü]+)\s+(\d{4})', date_str.strip())
    if match:
        day, month_name, year = match.groups()
        month_num = TURKISH_MONTHS.get(month_name.upper())
        if month_num:
            return f"{year}-{month_num:02d}-{int(day):02d}"
    
    return None

def parse_date(date_str: Optional[str]) -> Optional[str]:
    """Parse various date formats to YYYY-MM-DD"""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try Turkish format first (e.g., "30 EKIM 2024")
    turkish_result = parse_turkish_date(date_str)
    if turkish_result:
        return turkish_result
    
    # Try standard formats
    formats = [
        '%Y-%m-%d',      # 2024-10-30
        '%d.%m.%Y',      # 30.10.2024
        '%d/%m/%Y',      # 30/10/2024
        '%Y/%m/%d',      # 2024/10/30
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    return None

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

def insert_ilan(cursor, announcement: Dict[str, Any], gazette_metadata: Dict[str, Any]) -> Optional[int]:
    """Insert a single ilan (announcement) into the ilanlar table.
    Returns None if ilan_no is missing (record skipped)."""
    
    metadata = announcement.get('metadata', {})
    content = announcement.get('content', {})
    
    # ilan_no is REQUIRED - skip if null
    ilan_no = metadata.get('announcement_number')
    if not ilan_no:
        return None  # Skip this record
    
    # Extract fields
    ticaret_sicil_no = metadata.get('registry_number')
    if ticaret_sicil_no == 'Unknown':
        ticaret_sicil_no = None
        
    ilan_turu = get_ilan_turu_code(announcement.get('announcement_type'))
    
    mersis_no = metadata.get('mersis_no')
    if mersis_no == 'Unknown':
        mersis_no = None
        
    unvan = metadata.get('company_name') or 'Bilinmiyor'
    
    # Get city from registry_office
    registry_office = metadata.get('registry_office', '')
    city = content.get('city') or extract_city_from_registry_office(registry_office)
    il = get_il_code(city)
    
    ilce = content.get('district')
    adres = content.get('new_address') or content.get('address')
    tescil_tarihi = parse_date(content.get('registration_date') or content.get('change_date'))
    gazete_tarihi = parse_date(gazette_metadata.get('date'))
    gazete_sayisi = str(gazette_metadata.get('number', ''))
    
    # Store remaining content as detaylar JSONB
    excluded_keys = {'city', 'district', 'new_address', 'address', 'registration_date', 'change_date'}
    detaylar = {k: v for k, v in content.items() 
                if k not in excluded_keys and not k.startswith('_') and v is not None}
    
    query = """
        INSERT INTO ilanlar (
            ticaret_sicil_no, ilan_no, ilan_turu, mersis_no, unvan,
            il, ilce, adres, tescil_tarihi, gazete_tarihi, gazete_sayisi, detaylar
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ilan_no) DO UPDATE SET
            ticaret_sicil_no = EXCLUDED.ticaret_sicil_no,
            ilan_turu = EXCLUDED.ilan_turu,
            mersis_no = EXCLUDED.mersis_no,
            unvan = EXCLUDED.unvan,
            il = EXCLUDED.il,
            ilce = EXCLUDED.ilce,
            adres = EXCLUDED.adres,
            tescil_tarihi = EXCLUDED.tescil_tarihi,
            gazete_tarihi = EXCLUDED.gazete_tarihi,
            gazete_sayisi = EXCLUDED.gazete_sayisi,
            detaylar = EXCLUDED.detaylar
        RETURNING id
    """

    cursor.execute(query, (
        ticaret_sicil_no,
        ilan_no,
        ilan_turu,
        mersis_no,
        unvan,
        il,
        ilce,
        adres,
        tescil_tarihi,
        gazete_tarihi,
        gazete_sayisi,
        Json(detaylar) if detaylar else Json({})
    ))

    return cursor.fetchone()[0]

def import_json_file(conn, json_path: Path) -> Dict[str, int]:
    """Import a single JSON file into the database"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        cursor = conn.cursor()
        gazette_metadata = data.get('gazette_metadata', {})
        announcements = data.get('announcements', [])
        
        stats = {
            'total': len(announcements),
            'imported': 0,
            'skipped_no_ilan_no': 0,
            'errors': 0
        }

        for announcement in announcements:
            try:
                result = insert_ilan(cursor, announcement, gazette_metadata)
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

    except Exception as e:
        print(f"[✗] Error importing {json_path.name}: {e}")
        conn.rollback()
        raise

def import_all_json_files(conn, json_dir: Path):
    """Import all JSON files from directory"""
    json_files = sorted(json_dir.glob('*.json'))

    if not json_files:
        print(f"[!] No JSON files found in {json_dir}")
        return None

    print(f"\n[→] Found {len(json_files)} JSON file(s) to import\n")

    total_stats = {
        'files': 0,
        'total': 0,
        'imported': 0,
        'skipped_no_ilan_no': 0,
        'errors': 0
    }

    for idx, json_path in enumerate(json_files, 1):
        print(f"[{idx}/{len(json_files)}] Importing: {json_path.name}")

        try:
            stats = import_json_file(conn, json_path)

            print(f"    ✓ Imported:        {stats['imported']}")
            print(f"    ⊘ Skipped (no ID): {stats['skipped_no_ilan_no']}")
            print(f"    ✗ Errors:          {stats['errors']}")
            print(f"    Total:             {stats['total']}\n")

            total_stats['files'] += 1
            total_stats['total'] += stats['total']
            total_stats['imported'] += stats['imported']
            total_stats['skipped_no_ilan_no'] += stats['skipped_no_ilan_no']
            total_stats['errors'] += stats['errors']

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

    cursor.execute("SELECT COUNT(*) FROM ilanlar")
    ilan_count = cursor.fetchone()[0]
    print(f"\nTotal İlanlar: {ilan_count}")

    cursor.execute("""
        SELECT ilan_turu, COUNT(*) as count
        FROM ilanlar
        GROUP BY ilan_turu
        ORDER BY count DESC
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

    cursor.execute("""
        SELECT il, COUNT(*) as count
        FROM ilanlar
        GROUP BY il
        ORDER BY count DESC
        LIMIT 10
    """)

    print("\nTop 10 Cities (by plaka code):")
    for row in cursor.fetchall():
        print(f"  İl {row[0]:2d}: {row[1]:3d}")

    cursor.close()
    print("="*80 + "\n")

def main():
    print("="*80)
    print("GAZETTE JSON → POSTGRESQL IMPORT TOOL")
    print("="*80)

    script_dir = Path(__file__).parent
    default_json_dir = script_dir.parent / 'TTSG_Agent' / 'OCR_outputs' / 'json'
    
    json_dir_env = os.getenv("GAZETTE_JSON_DIR")
    json_dir = Path(json_dir_env) if json_dir_env else default_json_dir

    if not json_dir.exists():
        print(f"[✗] JSON directory not found: {json_dir}")
        return

    print(f"\nJSON Directory: {json_dir}")
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    print(f"\n[!] Note: Records with null announcement_number will be skipped.\n")

    response = input("Initialize schema (will drop existing table)? [y/N]: ")
    initialize_schema_flag = response.lower() == 'y'

    try:
        create_database_if_not_exists()
        conn = connect_to_db()

        if initialize_schema_flag:
            if not initialize_schema(conn):
                print("[✗] Schema initialization failed. Aborting.")
                return

        total_stats = import_all_json_files(conn, json_dir)

        if total_stats:
            print("\n" + "="*80)
            print("IMPORT SUMMARY")
            print("="*80)
            print(f"Files processed:       {total_stats['files']}")
            print(f"Total announcements:   {total_stats['total']}")
            print(f"  ✓ Imported:          {total_stats['imported']}")
            print(f"  ⊘ Skipped (no ID):   {total_stats['skipped_no_ilan_no']}")
            print(f"  ✗ Errors:            {total_stats['errors']}")
            print("="*80)

        print_database_stats(conn)

        conn.close()
        print("[✓] Import complete. Database connection closed.")

    except Exception as e:
        print(f"\n[✗] Import process failed: {e}")
        raise

if __name__ == "__main__":
    main()
