#!/usr/bin/env python3
"""
Main Pipeline Orchestrator for Turkish Trade Registry Gazette Processing

Workflow:
1. Check database for existing crawled date ranges
2. Calculate gaps (missing periods) that need to be scraped
3. For each gap:
   - Clean working directories
   - Scrape PDFs
   - Run OCR and extract structured data  
   - Convert to ilanlar.json format
   - Record crawl history
4. Import all data to PostgreSQL
"""

import argparse
import sys
import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import subprocess

# Add parent directory to path for db imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()


def initial_cleanup():
    """Reset ilanlar.json once at the start of the pipeline."""
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent
    
    ilanlar_path = root_dir / "db" / "db_Input" / "ilanlar.json"
    
    print("\n" + "="*60)
    print("🧹 INITIAL CLEANUP")
    print("="*60)
    
    # Reset ilanlar.json to empty array (only once at start)
    ilanlar_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ilanlar_path, 'w', encoding='utf-8') as f:
        json.dump([], f)
    print(f"  ✓ Reset: {ilanlar_path.name}")
    
    print("="*60)


def clean_gap_directories():
    """Clean PDF and OCR output directories before processing each gap.
    
    Note: Does NOT reset ilanlar.json - we want to append data from multiple gaps.
    """
    script_dir = Path(__file__).parent
    
    # Directories to clean (but NOT ilanlar.json)
    dirs_to_clean = [
        script_dir / os.getenv("GAZETTE_DIR", "scrapped_pdf_files"),
        script_dir / "OCR_outputs" / "markdown",
        script_dir / "OCR_outputs" / "json",
    ]
    
    print("\n" + "="*60)
    print("🧹 CLEANING GAP DIRECTORIES")
    print("="*60)
    
    for dir_path in dirs_to_clean:
        if dir_path.exists():
            # Delete all files in directory
            for file in dir_path.iterdir():
                if file.is_file():
                    file.unlink()
            print(f"  ✓ Cleaned: {dir_path}")
        else:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ Created: {dir_path}")
    
    print("="*60)


def create_crawl_metadata(office: str, name: str, start_date: str, end_date: str):
    """Create crawl_metadata.json in db/db_Input/ folder."""
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent
    
    metadata = {
        "sirket_sorgusu": name,
        "il": office,
        "search_period": {
            "start": start_date,
            "end": end_date
        },
        "created_at": datetime.now().isoformat()
    }
    
    # Write to db/db_Input/
    db_input_dir = root_dir / "db" / "db_Input"
    db_input_dir.mkdir(parents=True, exist_ok=True)
    
    metadata_path = db_input_dir / "crawl_metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Created crawl_metadata.json: {name} in {office} [{start_date}, {end_date})")
    return metadata_path


def run_scraper(office: str, name: str, start_date: str, end_date: str):
    """Run the web scraper to download PDFs."""
    print("\n" + "="*80)
    print("STEP: SCRAPING GAZETTES")
    print("="*80)
    
    python_exe = sys.executable
    scraper_script = os.path.join(os.getcwd(), "ticaret_sicil_scraper copy.py")
    gazette_dir = os.getenv("GAZETTE_DIR", "scrapped_pdf_files")

    cmd_str = f'"{python_exe}" "{scraper_script}" --office "{office}" --title "{name}" --download-pdf --pdf-output-dir "{gazette_dir}"'
    
    if start_date and end_date:
        cmd_str += f' --start-date "{start_date}" --end-date "{end_date}"'
    
    print(f"Running command: {cmd_str}")
    
    result = subprocess.run(cmd_str, shell=True)
    
    if result.returncode != 0:
        print("\n❌ Scraping failed!")
        return False
    
    print("\n✅ Scraping completed!")
    return True


def run_batch_processor(name: str):
    """Run OCR and data extraction on downloaded PDFs."""
    print("\n" + "="*80)
    print("STEP: BATCH PROCESSING (OCR + EXTRACTION)")
    print("="*80)
    
    python_exe = sys.executable
    script_name = "batch_process_gazettes.py"
    script_path = os.path.join(os.getcwd(), script_name)
    
    cmd_str = f'"{python_exe}" "{script_path}" --name {name}'
    
    result = subprocess.run(cmd_str, shell=True)
    
    if result.returncode != 0:
        print("\n❌ Batch processing failed!")
        return False
    
    print("\n✅ Batch processing completed!")
    return True


def run_json_converter():
    """Run json_to_ilanlar.py to convert OCR outputs to ilanlar.json format."""
    print("\n" + "="*80)
    print("STEP: CONVERTING JSON TO ILANLAR FORMAT")
    print("="*80)
    
    python_exe = sys.executable
    script_path = os.path.join(os.getcwd(), "json_to_ilanlar.py")
    
    cmd_str = f'"{python_exe}" "{script_path}"'
    
    result = subprocess.run(cmd_str, shell=True)
    
    if result.returncode != 0:
        print("\n❌ JSON conversion failed!")
        return False
    
    print("\n✅ JSON conversion completed!")
    return True


def run_import_to_postgres():
    """Run import_to_postgres.py to import data to database."""
    print("\n" + "="*80)
    print("STEP: IMPORTING TO POSTGRESQL")
    print("="*80)
    
    python_exe = sys.executable
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent
    script_path = root_dir / "db" / "import_to_postgres.py"
    
    cmd_str = f'"{python_exe}" "{script_path}"'
    
    result = subprocess.run(cmd_str, shell=True, cwd=str(root_dir / "db"))
    
    if result.returncode != 0:
        print("\n❌ Database import failed!")
        return False
    
    print("\n✅ Database import completed!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Turkish Trade Registry Gazette Processing Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  python app.py --office ANKARA --name TURKCELL --start-date 2024-01-01 --end-date 2024-12-31

"""
    )
    
    parser.add_argument('--office', type=str, required=True,
                        help='Registry office name (e.g., ANKARA)')
    parser.add_argument('--name', type=str, required=True,
                        help='Trade registry name (e.g., TURKCELL)')
    parser.add_argument('--start-date', type=str, required=True,
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, required=True,
                        help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()

    # Print pipeline configuration
    print("="*80)
    print("🔄 GAZETTE PROCESSING PIPELINE")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nConfiguration:")
    print(f"  Office:           {args.office}")
    print(f"  Company:          {args.name}")
    print(f"  Date Range:       {args.start_date} to {args.end_date}")
    print(f"  Gazette Directory: {os.getenv('GAZETTE_DIR', 'scrapped_pdf_files')}")
    print(f"  Output Directory:  {os.getenv('OUTPUT_DIR', 'OCR_outputs')}")
    print("="*80)
    
    # =========================================================================
    # STEP 1: CHECK CRAWLING HISTORY FOR GAPS
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 1: CHECKING CRAWLING HISTORY")
    print("="*80)
    
    try:
        from db.db_utils import check_crawl_history_str, insert_crawl_history_str
        
        result = check_crawl_history_str(
            args.start_date, 
            args.end_date, 
            args.office, 
            args.name
        )
        
        print(f"\nExisting crawled ranges: {len(result.existing_ranges)}")
        for r in result.existing_ranges:
            print(f"  ✓ {r}")
        
        print(f"\nMissing ranges (gaps): {len(result.missing_ranges)}")
        for r in result.missing_ranges:
            print(f"  ⚠ {r}")
        
        gaps = result.missing_ranges
        
    except Exception as e:
        print(f"\n⚠ Could not check crawling history: {e}")
        print("  → Proceeding with full date range")
        from db.db_utils import DateRange, insert_crawl_history_str
        from datetime import datetime as dt
        gaps = [DateRange(
            start=dt.strptime(args.start_date, '%Y-%m-%d').date(),
            end=dt.strptime(args.end_date, '%Y-%m-%d').date()
        )]
        result = None  # No existing ranges info available
    
    # =========================================================================
    # STEP 2: CHECK IF ALL DATA ALREADY CRAWLED → STILL EXPORT EXISTING DATA
    # =========================================================================
    if not gaps:
        print("\n" + "="*80)
        print("✅ ALL DATA ALREADY IN DATABASE")
        print("="*80)
        print("No gaps found - all data has been previously scraped.")
        print("Exporting existing data to ilanlar.json...")
        
        # Fetch existing data and export
        from db.db_utils import fetch_ilanlar_by_date_range
        
        script_dir = Path(__file__).parent
        root_dir = script_dir.parent
        ilanlar_path = root_dir / "db" / "db_Input" / "ilanlar.json"
        
        all_records = []
        if result and result.existing_ranges:
            for existing_range in result.existing_ranges:
                records = fetch_ilanlar_by_date_range(
                    existing_range.start,
                    existing_range.end,
                    args.office,
                    args.name
                )
                all_records.extend(records)
        
        # Save to ilanlar.json
        ilanlar_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ilanlar_path, 'w', encoding='utf-8') as f:
            json.dump(all_records, f, indent=4, ensure_ascii=False)
        
        print(f"\n✓ Exported {len(all_records)} existing records to {ilanlar_path.name}")
        print("="*80)
        return
    
    print(f"\n📋 Will process {len(gaps)} gap(s)")
    
    # Initial cleanup - reset ilanlar.json once at start
    initial_cleanup()
    
    # =========================================================================
    # STEP 2.5: FETCH EXISTING DATA FOR ALREADY-CRAWLED RANGES
    # =========================================================================
    if result and result.existing_ranges:
        print("\n" + "="*80)
        print("STEP 2.5: FETCHING EXISTING DATA FROM DATABASE")
        print("="*80)
        
        from db.db_utils import fetch_ilanlar_by_date_range
        
        script_dir = Path(__file__).parent
        root_dir = script_dir.parent
        ilanlar_path = root_dir / "db" / "db_Input" / "ilanlar.json"
        
        # Load current ilanlar.json (should be empty after initial_cleanup)
        existing_entries = []
        if ilanlar_path.exists():
            with open(ilanlar_path, 'r', encoding='utf-8') as f:
                existing_entries = json.load(f)
        
        # Fetch records for each existing range
        total_fetched = 0
        for existing_range in result.existing_ranges:
            records = fetch_ilanlar_by_date_range(
                existing_range.start,
                existing_range.end,
                args.office,
                args.name
            )
            existing_entries.extend(records)
            total_fetched += len(records)
        
        # Save to ilanlar.json
        with open(ilanlar_path, 'w', encoding='utf-8') as f:
            json.dump(existing_entries, f, indent=4, ensure_ascii=False)
        
        print(f"\n✓ Fetched {total_fetched} existing records from database")
        print(f"✓ Saved to {ilanlar_path.name}")
    
    # =========================================================================
    # STEP 3: PROCESS EACH GAP
    # =========================================================================
    for gap_idx, gap in enumerate(gaps, 1):
        gap_start = gap.start.strftime('%Y-%m-%d')
        gap_end = gap.end.strftime('%Y-%m-%d')
        
        print("\n" + "="*80)
        print(f"🔄 PROCESSING GAP {gap_idx}/{len(gaps)}: [{gap_start}, {gap_end})")
        print("="*80)
        
        # 3a. Clean working directories
        clean_gap_directories()
        
        # 3b. Run scraper
        if not run_scraper(args.office, args.name, gap_start, gap_end):
            print(f"\n❌ Failed to scrape gap {gap_idx}. Continuing to next gap...")
            continue
        
        # 3c. Run batch processor
        if not run_batch_processor(args.name):
            print(f"\n⚠ Batch processing failed for gap {gap_idx}.")
            # Still record crawl history to avoid re-scraping
        
        # 3d. Create crawl metadata
        create_crawl_metadata(args.office, args.name, gap_start, gap_end)
        
        # 3e. Run JSON converter
        run_json_converter()
        
        # 3f. Record crawl history in database
        print("\n" + "="*60)
        print("RECORDING CRAWL HISTORY")
        print("="*60)
        insert_crawl_history_str(gap_start, gap_end, args.office, args.name)
    
    # =========================================================================
    # STEP 4: IMPORT TO POSTGRESQL
    # =========================================================================
    run_import_to_postgres()
    
    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print("\n" + "="*80)
    print("✅ PIPELINE COMPLETED SUCCESSFULLY!")
    print("="*80)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nProcessed {len(gaps)} gap(s):")
    for gap in gaps:
        print(f"  • [{gap.start}, {gap.end})")
    print(f"\nOutputs:")
    print(f"  PDFs:     {os.getenv('GAZETTE_DIR', 'scrapped_pdf_files')}/")
    print(f"  Markdown: {os.getenv('OUTPUT_DIR', 'OCR_outputs')}/markdown/")
    print(f"  JSON:     {os.getenv('OUTPUT_DIR', 'OCR_outputs')}/json/")
    print(f"  Database: gazette_db.ilanlar")
    print("="*80)


if __name__ == "__main__":
    main()
