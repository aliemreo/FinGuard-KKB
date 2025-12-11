"""
Query PostgreSQL database with proper UTF-8 encoding support

This script provides a Python interface to query the gazette database
with automatic UTF-8 encoding handling for Turkish characters.

Requirements:
    pip install psycopg2-binary pandas tabulate
"""

import sys
import io
import psycopg2
import pandas as pd
from tabulate import tabulate

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Database configuration
DB_CONFIG = {
    'dbname': 'gazette_db',
    'user': 'postgres',
    'password': '383418',
    'host': 'localhost',
    'port': 5432
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

def get_all_announcements(limit=10):
    """Get all announcements"""
    query = """
        SELECT
            g.gazette_number,
            g.gazette_date,
            a.company_name,
            a.announcement_type,
            a.mersis_no
        FROM announcements a
        JOIN gazettes g ON a.gazette_id = g.id
        ORDER BY g.gazette_number DESC
        LIMIT %s
    """
    return run_query(query, (limit,))

def get_mergers():
    """Get all merger announcements"""
    query = """
        SELECT
            a.company_name,
            a.content->'acquiring_company'->>'name' as acquiring_company,
            a.content->'acquired_company'->>'name' as acquired_company,
            a.content->>'registration_date' as registration_date,
            a.content->>'deadline_for_creditors' as creditor_deadline,
            g.gazette_number
        FROM announcements a
        JOIN gazettes g ON a.gazette_id = g.id
        WHERE a.announcement_type = 'birleşme'
        ORDER BY g.gazette_number DESC
    """
    return run_query(query)

def get_address_changes():
    """Get all address changes"""
    query = """
        SELECT
            a.company_name,
            a.content->>'old_address' as old_address,
            a.content->>'new_address' as new_address,
            a.content->>'change_date' as change_date,
            g.gazette_number
        FROM announcements a
        JOIN gazettes g ON a.gazette_id = g.id
        WHERE a.announcement_type = 'adres_değişikliği'
        ORDER BY g.gazette_number DESC
    """
    return run_query(query)

def get_compound_changes():
    """Get all compound changes"""
    query = """
        SELECT
            a.company_name,
            a.content->>'registered_matters' as registered_matters,
            a.content->>'new_address' as new_address,
            a.content->>'new_capital' as new_capital,
            g.gazette_number
        FROM announcements a
        JOIN gazettes g ON a.gazette_id = g.id
        WHERE a.announcement_type = 'bileşik_değişiklik'
        ORDER BY g.gazette_number DESC
    """
    return run_query(query)

def get_statistics():
    """Get announcement type statistics"""
    query = """
        SELECT
            announcement_type,
            COUNT(*) as total_count,
            SUM(CASE WHEN extraction_success THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN is_fallback THEN 1 ELSE 0 END) as fallback
        FROM announcements
        GROUP BY announcement_type
        ORDER BY total_count DESC
    """
    return run_query(query)

def search_company(company_name):
    """Search for company by name (partial match)"""
    query = """
        SELECT
            a.company_name,
            a.mersis_no,
            a.announcement_type,
            g.gazette_number,
            g.gazette_date
        FROM announcements a
        JOIN gazettes g ON a.gazette_id = g.id
        WHERE a.company_name ILIKE %s
        ORDER BY g.gazette_number DESC
    """
    return run_query(query, (f'%{company_name}%',))

def get_company_by_mersis(mersis_no):
    """Get all announcements for a company by MERSİS number"""
    query = """
        SELECT
            g.gazette_number,
            g.gazette_date,
            a.announcement_type,
            a.content
        FROM announcements a
        JOIN gazettes g ON a.gazette_id = g.id
        WHERE a.mersis_no = %s
        ORDER BY g.gazette_number DESC
    """
    return run_query(query, (mersis_no,))

def get_fallback_extractions():
    """Get announcements that used fallback extraction"""
    query = """
        SELECT
            a.id,
            g.gazette_number,
            a.company_name,
            a.content->>'_original_detected_type' as original_type,
            a.announcement_type as placeholder_type
        FROM announcements a
        JOIN gazettes g ON a.gazette_id = g.id
        WHERE a.is_fallback = TRUE
        ORDER BY g.gazette_number DESC
    """
    return run_query(query)

def get_company_activity():
    """Get companies with multiple announcements"""
    query = """
        SELECT
            company_name,
            mersis_no,
            COUNT(*) as announcement_count,
            string_agg(DISTINCT announcement_type, ', ') as announcement_types
        FROM announcements
        WHERE company_name IS NOT NULL
        GROUP BY company_name, mersis_no
        HAVING COUNT(*) > 1
        ORDER BY announcement_count DESC
    """
    return run_query(query)

# ============================================================================
# INTERACTIVE MENU
# ============================================================================

def main_menu():
    """Display interactive menu"""
    while True:
        print("\n" + "="*80)
        print("GAZETTE DATABASE QUERY TOOL")
        print("="*80)
        print("\n1.  View all announcements")
        print("2.  View merger announcements (birleşme)")
        print("3.  View address changes (adres_değişikliği)")
        print("4.  View compound changes (bileşik_değişiklik)")
        print("5.  View statistics by type")
        print("6.  Search company by name")
        print("7.  Search company by MERSİS number")
        print("8.  View fallback extractions")
        print("9.  View companies with multiple announcements")
        print("10. Run custom SQL query")
        print("0.  Exit")

        choice = input("\nEnter choice: ").strip()

        if choice == '0':
            print("Goodbye!")
            break
        elif choice == '1':
            limit = input("Number of rows to display (default 10): ").strip() or "10"
            df = get_all_announcements(int(limit))
            print_df(df)
        elif choice == '2':
            df = get_mergers()
            print_df(df)
        elif choice == '3':
            df = get_address_changes()
            print_df(df)
        elif choice == '4':
            df = get_compound_changes()
            print_df(df)
        elif choice == '5':
            df = get_statistics()
            print_df(df)
        elif choice == '6':
            company_name = input("Enter company name (partial match): ").strip()
            if company_name:
                df = search_company(company_name)
                print_df(df)
        elif choice == '7':
            mersis_no = input("Enter MERSİS number (16 digits): ").strip()
            if mersis_no:
                df = get_company_by_mersis(mersis_no)
                print_df(df)
        elif choice == '8':
            df = get_fallback_extractions()
            print_df(df)
        elif choice == '9':
            df = get_company_activity()
            print_df(df)
        elif choice == '10':
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

    parser = argparse.ArgumentParser(description='Query gazette database')
    parser.add_argument('--all', action='store_true', help='Show all announcements')
    parser.add_argument('--mergers', action='store_true', help='Show merger announcements')
    parser.add_argument('--address', action='store_true', help='Show address changes')
    parser.add_argument('--compound', action='store_true', help='Show compound changes')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--company', type=str, help='Search company by name')
    parser.add_argument('--mersis', type=str, help='Search by MERSİS number')
    parser.add_argument('--fallback', action='store_true', help='Show fallback extractions')
    parser.add_argument('--activity', action='store_true', help='Show company activity')
    parser.add_argument('--limit', type=int, default=10, help='Limit results')

    args = parser.parse_args()

    # If no arguments, show interactive menu
    if len(sys.argv) == 1:
        main_menu()
        return

    # Handle command line arguments
    if args.all:
        df = get_all_announcements(args.limit)
        print_df(df)
    elif args.mergers:
        df = get_mergers()
        print_df(df)
    elif args.address:
        df = get_address_changes()
        print_df(df)
    elif args.compound:
        df = get_compound_changes()
        print_df(df)
    elif args.stats:
        df = get_statistics()
        print_df(df)
    elif args.company:
        df = search_company(args.company)
        print_df(df)
    elif args.mersis:
        df = get_company_by_mersis(args.mersis)
        print_df(df)
    elif args.fallback:
        df = get_fallback_extractions()
        print_df(df)
    elif args.activity:
        df = get_company_activity()
        print_df(df)

if __name__ == "__main__":
    main()
