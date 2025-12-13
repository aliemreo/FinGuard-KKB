"""
Query PostgreSQL database with proper UTF-8 encoding support

This script provides a Python interface to query the ilanlar database
with automatic UTF-8 encoding handling for Turkish characters.

Requirements:
    pip install psycopg2-binary pandas tabulate python-dotenv
"""

import sys
import io
import os
from pathlib import Path

# Load env from root directory
root_dir = Path(__file__).parent.parent
env_path = root_dir / '.env'
from dotenv import load_dotenv
load_dotenv(dotenv_path=env_path)

import psycopg2
import pandas as pd
from tabulate import tabulate

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'gazette_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432))
}

# İlan türü names mapping
ILAN_TURU_NAMES = {
    1: 'Kuruluş',
    2: 'Yönetim/Temsil',
    3: 'Sermaye/Pay',
    4: 'Sözleşme/Merkez',
    5: 'Yapısal Değişiklik',
    6: 'Şube',
    7: 'Tasfiye',
    8: 'İflas/Konkordato',
    9: 'Devir',
    10: 'Çağrı/Bildirim',
    11: 'Düzeltme'
}

def connect():
    """Connect to database"""
    return psycopg2.connect(**DB_CONFIG)

def run_query(query, params=None):
    """Run a query and return results as DataFrame"""
    conn = connect()
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        conn.close()

def print_df(df, max_rows=None):
    """Print DataFrame with proper formatting"""
    if df.empty:
        print("No results found.")
        return

    if max_rows:
        df = df.head(max_rows)

    print(tabulate(df, headers='keys', tablefmt='grid', showindex=False))
    print(f"\n({len(df)} rows)")

# ============================================================================
# COMMON QUERIES
# ============================================================================

def get_all_ilanlar(limit=10):
    """Get all announcements"""
    query = """
        SELECT
            id,
            unvan,
            ilan_turu,
            mersis_no,
            il,
            gazete_tarihi,
            gazete_sayisi
        FROM ilanlar
        ORDER BY gazete_tarihi DESC NULLS LAST
        LIMIT %s
    """
    return run_query(query, (limit,))

def get_ilanlar_by_type(ilan_turu: int, limit=50):
    """Get announcements by type code (1-11)"""
    query = """
        SELECT
            id,
            unvan,
            mersis_no,
            il,
            gazete_tarihi,
            detaylar
        FROM ilanlar
        WHERE ilan_turu = %s
        ORDER BY gazete_tarihi DESC NULLS LAST
        LIMIT %s
    """
    return run_query(query, (ilan_turu, limit))

def get_kurulular():
    """Get establishment announcements (ilan_turu = 1)"""
    return get_ilanlar_by_type(1)

def get_birlesmeler():
    """Get merger announcements (ilan_turu = 5)"""
    return get_ilanlar_by_type(5)

def get_tasfiyeler():
    """Get liquidation announcements (ilan_turu = 7)"""
    return get_ilanlar_by_type(7)

def get_statistics():
    """Get announcement type statistics"""
    query = """
        SELECT
            ilan_turu,
            COUNT(*) as total_count
        FROM ilanlar
        GROUP BY ilan_turu
        ORDER BY total_count DESC
    """
    df = run_query(query)
    # Add type names
    df['ilan_turu_adi'] = df['ilan_turu'].map(ILAN_TURU_NAMES)
    return df[['ilan_turu', 'ilan_turu_adi', 'total_count']]

def get_statistics_by_city():
    """Get statistics by city"""
    query = """
        SELECT
            il,
            COUNT(*) as total_count
        FROM ilanlar
        GROUP BY il
        ORDER BY total_count DESC
        LIMIT 20
    """
    return run_query(query)

def search_company(company_name):
    """Search for company by name (partial match)"""
    query = """
        SELECT
            id,
            unvan,
            mersis_no,
            ilan_turu,
            il,
            gazete_tarihi
        FROM ilanlar
        WHERE unvan ILIKE %s
        ORDER BY gazete_tarihi DESC NULLS LAST
    """
    return run_query(query, (f'%{company_name}%',))

def get_company_by_mersis(mersis_no):
    """Get all announcements for a company by MERSİS number"""
    query = """
        SELECT
            id,
            unvan,
            ilan_turu,
            gazete_tarihi,
            gazete_sayisi,
            detaylar
        FROM ilanlar
        WHERE mersis_no = %s
        ORDER BY gazete_tarihi DESC NULLS LAST
    """
    return run_query(query, (mersis_no,))

def get_ilanlar_by_city(il_code: int, limit=50):
    """Get announcements by city code (plaka)"""
    query = """
        SELECT
            id,
            unvan,
            ilan_turu,
            mersis_no,
            ilce,
            gazete_tarihi
        FROM ilanlar
        WHERE il = %s
        ORDER BY gazete_tarihi DESC NULLS LAST
        LIMIT %s
    """
    return run_query(query, (il_code, limit))

def get_recent_ilanlar(days=30, limit=100):
    """Get recent announcements from last N days"""
    query = """
        SELECT
            id,
            unvan,
            ilan_turu,
            mersis_no,
            il,
            gazete_tarihi
        FROM ilanlar
        WHERE gazete_tarihi >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY gazete_tarihi DESC
        LIMIT %s
    """
    return run_query(query, (days, limit))

# ============================================================================
# INTERACTIVE MENU
# ============================================================================

def main_menu():
    """Display interactive menu"""
    while True:
        print("\n" + "="*80)
        print("İLANLAR DATABASE QUERY TOOL")
        print("="*80)
        print("\n1.  View all announcements")
        print("2.  View by type (kuruluş, birleşme, tasfiye, etc.)")
        print("3.  View statistics by type")
        print("4.  View statistics by city")
        print("5.  Search company by name")
        print("6.  Search company by MERSİS number")
        print("7.  View by city (plaka code)")
        print("8.  View recent announcements")
        print("9.  Run custom SQL query")
        print("0.  Exit")

        choice = input("\nEnter choice: ").strip()

        if choice == '0':
            print("Goodbye!")
            break
        elif choice == '1':
            limit = input("Number of rows to display (default 10): ").strip() or "10"
            df = get_all_ilanlar(int(limit))
            print_df(df)
        elif choice == '2':
            print("\nİlan Türleri:")
            for code, name in ILAN_TURU_NAMES.items():
                print(f"  {code:2d} = {name}")
            type_code = input("\nEnter type code (1-11): ").strip()
            if type_code.isdigit() and 1 <= int(type_code) <= 11:
                df = get_ilanlar_by_type(int(type_code))
                print_df(df)
        elif choice == '3':
            df = get_statistics()
            print_df(df)
        elif choice == '4':
            df = get_statistics_by_city()
            print_df(df)
        elif choice == '5':
            company_name = input("Enter company name (partial match): ").strip()
            if company_name:
                df = search_company(company_name)
                print_df(df)
        elif choice == '6':
            mersis_no = input("Enter MERSİS number (16 digits): ").strip()
            if mersis_no:
                df = get_company_by_mersis(mersis_no)
                print_df(df)
        elif choice == '7':
            il_code = input("Enter city plaka code (1-81): ").strip()
            if il_code.isdigit() and 1 <= int(il_code) <= 81:
                df = get_ilanlar_by_city(int(il_code))
                print_df(df)
        elif choice == '8':
            days = input("Number of days to look back (default 30): ").strip() or "30"
            df = get_recent_ilanlar(int(days))
            print_df(df)
        elif choice == '9':
            print("\nEnter SQL query (end with semicolon):")
            query_lines = []
            while True:
                line = input()
                query_lines.append(line)
                if line.strip().endswith(';'):
                    break
            query = '\n'.join(query_lines)
            try:
                df = run_query(query)
                print_df(df)
            except Exception as e:
                print(f"Error: {e}")
        else:
            print("Invalid choice. Please try again.")

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Query ilanlar database')
    parser.add_argument('--all', action='store_true', help='Show all announcements')
    parser.add_argument('--type', type=int, choices=range(1, 12), help='Filter by type (1-11)')
    parser.add_argument('--stats', action='store_true', help='Show statistics by type')
    parser.add_argument('--stats-city', action='store_true', help='Show statistics by city')
    parser.add_argument('--company', type=str, help='Search company by name')
    parser.add_argument('--mersis', type=str, help='Search by MERSİS number')
    parser.add_argument('--city', type=int, help='Filter by city plaka code (1-81)')
    parser.add_argument('--recent', type=int, help='Show recent announcements (days)')
    parser.add_argument('--limit', type=int, default=10, help='Limit results')

    args = parser.parse_args()

    # If no arguments, show interactive menu
    if len(sys.argv) == 1:
        main_menu()
        return

    # Handle command line arguments
    if args.all:
        df = get_all_ilanlar(args.limit)
        print_df(df)
    elif args.type:
        df = get_ilanlar_by_type(args.type, args.limit)
        print_df(df)
    elif args.stats:
        df = get_statistics()
        print_df(df)
    elif args.stats_city:
        df = get_statistics_by_city()
        print_df(df)
    elif args.company:
        df = search_company(args.company)
        print_df(df)
    elif args.mersis:
        df = get_company_by_mersis(args.mersis)
        print_df(df)
    elif args.city:
        df = get_ilanlar_by_city(args.city, args.limit)
        print_df(df)
    elif args.recent:
        df = get_recent_ilanlar(args.recent, args.limit)
        print_df(df)

if __name__ == "__main__":
    main()
