"""
Database Utility Functions for Gazette Crawling

Provides utility functions to work with the PostgreSQL database,
including checking crawling history for existing/missing date ranges.

Requirements:
    pip install psycopg2-binary python-dotenv
"""

import os
from pathlib import Path
from datetime import date
from typing import List, Tuple, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load env from root directory (2 levels up)
root_dir = Path(__file__).parent.parent
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

import psycopg2

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'gazette_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '1234'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432))
}


@dataclass
class DateRange:
    """Represents a date range [start, end)"""
    start: date
    end: date
    
    def __str__(self):
        return f"[{self.start}, {self.end})"
    
    def is_empty(self) -> bool:
        return self.start >= self.end


@dataclass
class CrawlRangeResult:
    """Result of checking crawl history for a date range"""
    existing_ranges: List[DateRange]   # Ranges already in crawling_history
    missing_ranges: List[DateRange]    # Ranges that need to be crawled


def connect_to_db():
    """Connect to PostgreSQL database"""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


def check_crawl_history(
    start_date: date,
    end_date: date,
    il: str,
    sirket_sorgusu: str
) -> CrawlRangeResult:
    """
    Check if the requested date range has already been crawled.
    
    Uses PostgreSQL's daterange and range_agg functions to efficiently
    calculate the overlap between the requested range and existing 
    crawling_history records.
    
    Args:
        start_date: Start of the requested date range (inclusive)
        end_date: End of the requested date range (exclusive)
        il: City/office string (e.g., "İstanbul" or "34")
        sirket_sorgusu: Company name search query string
    
    Returns:
        CrawlRangeResult containing:
        - existing_ranges: List of DateRange objects already in DB
        - missing_ranges: List of DateRange objects that need crawling
    
    Example:
        >>> result = check_crawl_history(
        ...     date(2024, 1, 1), date(2024, 12, 31),
        ...     "İstanbul", "ABC Şirketi"
        ... )
        >>> print("Already crawled:", result.existing_ranges)
        >>> print("Need to crawl:", result.missing_ranges)
    """
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        # Query to get existing ranges that overlap with the target range
        # Uses range intersection to find the actual overlap
        existing_query = """
            SELECT 
                lower(fetched_period * daterange(%s, %s, '[)')) as overlap_start,
                upper(fetched_period * daterange(%s, %s, '[)')) as overlap_end
            FROM crawling_history
            WHERE sirket_sorgusu = %s 
              AND il = %s
              AND fetched_period && daterange(%s, %s, '[)')
            ORDER BY lower(fetched_period)
        """
        
        cursor.execute(existing_query, (
            start_date, end_date,  # for intersection
            start_date, end_date,  # for intersection
            sirket_sorgusu, il,
            start_date, end_date   # for overlap check
        ))
        
        existing_ranges = []
        for row in cursor.fetchall():
            if row[0] and row[1]:  # Both dates exist
                existing_ranges.append(DateRange(start=row[0], end=row[1]))
        
        # Query to calculate missing ranges using multirange subtraction
        # PostgreSQL 14+ supports range_agg and multirange operations
        missing_query = """
            SELECT unnest(
                datemultirange(daterange(%s, %s, '[)')) - 
                COALESCE(range_agg(fetched_period), datemultirange())
            ) as missing_range
            FROM crawling_history
            WHERE sirket_sorgusu = %s 
              AND il = %s
              AND fetched_period && daterange(%s, %s, '[)')
        """
        
        cursor.execute(missing_query, (
            start_date, end_date,  # target range
            sirket_sorgusu, il,
            start_date, end_date   # for overlap filter
        ))
        
        missing_ranges = []
        rows = cursor.fetchall()
        
        # If no rows or null result, the entire range is missing
        if not rows or (len(rows) == 1 and rows[0][0] is None):
            # Check if there are ANY existing overlapping ranges
            if not existing_ranges:
                # No overlap at all - entire range is missing
                missing_ranges.append(DateRange(start=start_date, end=end_date))
        else:
            for row in rows:
                if row[0]:  # Range exists
                    # PostgreSQL returns range as string like '[2024-01-01,2024-06-01)'
                    # But with proper cursor types it might be a range object
                    range_val = row[0]
                    if hasattr(range_val, 'lower') and hasattr(range_val, 'upper'):
                        missing_ranges.append(DateRange(
                            start=range_val.lower, 
                            end=range_val.upper
                        ))
                    else:
                        # Parse string format if needed
                        range_str = str(range_val)
                        # Format: [YYYY-MM-DD,YYYY-MM-DD)
                        import re
                        match = re.match(r'\[(\d{4}-\d{2}-\d{2}),(\d{4}-\d{2}-\d{2})\)', range_str)
                        if match:
                            from datetime import datetime
                            start = datetime.strptime(match.group(1), '%Y-%m-%d').date()
                            end = datetime.strptime(match.group(2), '%Y-%m-%d').date()
                            missing_ranges.append(DateRange(start=start, end=end))
        
        return CrawlRangeResult(
            existing_ranges=existing_ranges,
            missing_ranges=missing_ranges
        )
        
    finally:
        cursor.close()
        conn.close()


# Convenience function with string date inputs
def check_crawl_history_str(
    start_date_str: str,
    end_date_str: str,
    il: str,
    sirket_sorgusu: str
) -> CrawlRangeResult:
    """
    Same as check_crawl_history but accepts date strings in YYYY-MM-DD format.
    
    Args:
        start_date_str: Start date as "YYYY-MM-DD" string
        end_date_str: End date as "YYYY-MM-DD" string  
        il: City/office string
        sirket_sorgusu: Company name search query
    
    Returns:
        CrawlRangeResult with existing and missing ranges
    """
    from datetime import datetime
    start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    return check_crawl_history(start, end, il, sirket_sorgusu)


def insert_crawl_history(
    start_date: date,
    end_date: date,
    il: str,
    sirket_sorgusu: str
) -> bool:
    """
    Insert a new crawl history record into the database.
    
    Args:
        start_date: Start of the crawled date range (inclusive)
        end_date: End of the crawled date range (exclusive)
        il: City/office string (e.g., "ANKARA")
        sirket_sorgusu: Company name search query string
    
    Returns:
        True if successful, False otherwise
    """
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO crawling_history (sirket_sorgusu, il, fetched_period)
            VALUES (%s, %s, daterange(%s, %s, '[)'))
        """
        cursor.execute(query, (sirket_sorgusu, il, start_date, end_date))
        conn.commit()
        print(f"[✓] Recorded crawl history: [{start_date}, {end_date}) for {sirket_sorgusu} in {il}")
        return True
    except Exception as e:
        print(f"[✗] Error inserting crawl history: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def insert_crawl_history_str(
    start_date_str: str,
    end_date_str: str,
    il: str,
    sirket_sorgusu: str
) -> bool:
    """
    Same as insert_crawl_history but accepts date strings in YYYY-MM-DD format.
    """
    from datetime import datetime
    start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    return insert_crawl_history(start, end, il, sirket_sorgusu)


def fetch_ilanlar_by_date_range(
    start_date: date,
    end_date: date,
    il: str,
    sirket_sorgusu: str
) -> List[dict]:
    """
    Fetch existing ilanlar records from database for a given date range.
    
    Args:
        start_date: Start date (inclusive)
        end_date: End date (exclusive)
        il: City/office string (e.g., "ANKARA")
        sirket_sorgusu: Company name search query string
    
    Returns:
        List of dictionaries in ilanlar.json format
    """
    conn = connect_to_db()
    cursor = conn.cursor()
    
    try:
        query = """
            SELECT 
                ilan_no, ilan_turu, ticaret_sicil_no, mersis_no, unvan,
                sirket_sorgusu, il, adres, tescil_tarihi, gazete_tarihi,
                gazete_sayisi, detaylar
            FROM ilanlar
            WHERE gazete_tarihi >= %s 
              AND gazete_tarihi < %s
              AND il = %s
              AND sirket_sorgusu = %s
            ORDER BY gazete_tarihi
        """
        cursor.execute(query, (start_date, end_date, il, sirket_sorgusu))
        
        rows = cursor.fetchall()
        results = []
        
        for row in rows:
            entry = {
                "ilan_no": row[0],
                "ilan_turu": row[1],
                "ticaret_sicil_no": row[2],
                "mersis_no": row[3],
                "unvan": row[4],
                "sirket_sorgusu": row[5],
                "il": row[6],
                "adres": row[7],
                "tescil_tarihi": row[8].isoformat() if row[8] else None,
                "gazete_tarihi": row[9].isoformat() if row[9] else None,
                "gazete_sayisi": row[10],
                "detaylar": row[11] if row[11] else {}
            }
            results.append(entry)
        
        print(f"[✓] Fetched {len(results)} existing records for {sirket_sorgusu} in {il} [{start_date}, {end_date})")
        return results
        
    except Exception as e:
        print(f"[✗] Error fetching ilanlar: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def fetch_ilanlar_by_date_range_str(
    start_date_str: str,
    end_date_str: str,
    il: str,
    sirket_sorgusu: str
) -> List[dict]:
    """
    Same as fetch_ilanlar_by_date_range but accepts date strings in YYYY-MM-DD format.
    """
    from datetime import datetime
    start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    return fetch_ilanlar_by_date_range(start, end, il, sirket_sorgusu)
