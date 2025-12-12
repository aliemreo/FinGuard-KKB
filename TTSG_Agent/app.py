#!/usr/bin/env python3
"""
Main Pipeline Orchestrator for Turkish Trade Registry Gazette Processing

Workflow:
1. Scrape PDFs from Trade Registry website
2. Process PDFs with OCR and extract structured data
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import subprocess

# Load environment variables
load_dotenv()


def run_scraper(office: str, number: str, start_date: str = None, end_date: str = None):
    print("\n" + "="*80)
    print("STEP 1: SCRAPING GAZETTES")
    print("="*80)
    
    python_exe = sys.executable
    scraper_script = os.path.join(os.getcwd(), "ticaret_sicil_scraper.py")
    gazette_dir = os.getenv("GAZETTE_DIR", "scraped_pdf_files")

    # FIX: Construct a single string command with quotes for safety
    cmd_str = f'"{python_exe}" "{scraper_script}" --office "{office}" --number "{number}" --download-pdf --pdf-output-dir "{gazette_dir}"'
    
    if start_date and end_date:
        cmd_str += f' --start-date "{start_date}" --end-date "{end_date}"'
    
    print(f"Running command: {cmd_str}")
    
    # FIX: Use shell=True with the string command
    result = subprocess.run(cmd_str, shell=True)
    
    if result.returncode != 0:
        print("\n❌ Scraping failed!")
        return False
    
    print("\n✅ Scraping completed!")
    return True

def run_batch_processor(parallel: bool = False, debug: bool = False):
    print("\n" + "="*80)
    print("STEP 2: BATCH PROCESSING")
    print("="*80)
    
    if debug:
        os.environ['DEBUG_MODE'] = 'true'
    
    python_exe = sys.executable
    script_name = "parallel_batch_process.py" if parallel else "batch_process_gazettes.py"
    script_path = os.path.join(os.getcwd(), script_name)
    
    # FIX: Construct a single string command
    cmd_str = f'"{python_exe}" "{script_path}"'
    
    if parallel:
        print("Running: Parallel batch processing")
    else:
        print("Running: Sequential batch processing")
    
    # FIX: Use shell=True with the string command
    result = subprocess.run(cmd_str, shell=True)
    
    if result.returncode != 0:
        print("\n❌ Batch processing failed!")
        return False
    
    print("\n✅ Batch processing completed!")
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Turkish Trade Registry Gazette Processing Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline: scrape and process
  python app.py --office ANKARA --number 31177 --start-date 2024-01-01 --end-date 2024-12-31
  
  # Only scraping
  python app.py --office ANKARA --number 31177 --scrape-only
  
  # Only processing (assumes PDFs already exist)
  python app.py --process-only
  
  # Use parallel processing for faster execution
  python app.py --process-only --parallel
  
  # Enable debug mode for detailed output
  python app.py --process-only --debug
"""
    )
    
    # Mode selection
    parser.add_argument('--scrape-only', action='store_true',
                        help='Only run the scraper, skip processing')
    parser.add_argument('--process-only', action='store_true',
                        help='Only run processing, skip scraping')
    
    # Scraper arguments
    parser.add_argument('--office', type=str,
                        help='Registry office name (e.g., ANKARA)')
    parser.add_argument('--number', type=str,
                        help='Trade registry number (e.g., 31177)')
    parser.add_argument('--start-date', type=str,
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str,
                        help='End date (YYYY-MM-DD)')
    
    # Processing arguments
    parser.add_argument('--parallel', action='store_true',
                        help='Use parallel processing (faster for multiple PDFs)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode (saves intermediate outputs)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.scrape_only and not args.process_only:
        # Full pipeline mode - need scraper args
        if not args.office or not args.number:
            parser.error("--office and --number required for scraping (or use --process-only)")
    
    if args.scrape_only and (not args.office or not args.number):
        parser.error("--office and --number required when using --scrape-only")
    
    # Print pipeline configuration
    print("="*80)
    print("GAZETTE PROCESSING PIPELINE")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nConfiguration:")
    print(f"  Gazette Directory: {os.getenv('GAZETTE_DIR', 'scraped_pdf_files')}")
    print(f"  Output Directory:  {os.getenv('OUTPUT_DIR', 'OCR_outputs')}")
    if args.parallel:
        print(f"  Processing Mode:   Parallel")
    else:
        print(f"  Processing Mode:   Sequential")
    if args.debug:
        print(f"  Debug Mode:        Enabled")
    print("="*80)
    
    success = True
    
    # Step 1: Scraping
    if not args.process_only:
        success = run_scraper(
            args.office,
            args.number,
            args.start_date,
            args.end_date
        )
        if not success:
            sys.exit(1)
    
    # Step 2: Processing
    if not args.scrape_only:
        success = run_batch_processor(
            parallel=args.parallel,
            debug=args.debug
        )
        if not success:
            sys.exit(1)
    
    # Final summary
    print("\n" + "="*80)
    print("✅ PIPELINE COMPLETED SUCCESSFULLY!")
    print("="*80)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nOutputs:")
    print(f"  PDFs:     {os.getenv('GAZETTE_DIR', 'scraped_pdf_files')}/")
    print(f"  Markdown: {os.getenv('OUTPUT_DIR', 'OCR_outputs')}/markdown/")
    print(f"  JSON:     {os.getenv('OUTPUT_DIR', 'OCR_outputs')}/json/")
    print("="*80)

if __name__ == "__main__":
    main()
