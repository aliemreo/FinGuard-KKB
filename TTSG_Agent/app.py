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


def run_scraper(office: str, name: str, start_date: str = None, end_date: str = None):
    print("\n" + "="*80)
    print("STEP 1: SCRAPING GAZETTES")
    print("="*80)
    
    python_exe = sys.executable
    scraper_script = os.path.join(os.getcwd(), "ticaret_sicil_scraper.py")
    gazette_dir = os.getenv("GAZETTE_DIR", "scraped_pdf_files")

    # FIX: Construct a single string command with quotes for safety
    cmd_str = f'"{python_exe}" "{scraper_script}" --office "{office}" --title "{name}" --download-pdf --pdf-output-dir "{gazette_dir}"'
    
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

def run_batch_processor(name: str):
    print("\n" + "="*80)
    print("STEP 2: BATCH PROCESSING")
    print("="*80)
    
    
    python_exe = sys.executable
    script_name = "batch_process_gazettes.py"
    script_path = os.path.join(os.getcwd(), script_name)
    
    # FIX: Construct a single string command
    cmd_str = f'"{python_exe}" "{script_path}" --name {name}'
    
    
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

  python app.py --office ANKARA --title TURKCELL --start-date 2024-01-01 --end-date 2024-12-31

"""
    )
    

    parser.add_argument('--office', type=str,
                        help='Registry office name (e.g., ANKARA)')
    parser.add_argument('--name', type=str,
                        help='Trade registry name (e.g., TURKCELL)')
    parser.add_argument('--start-date', type=str,
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str,
                        help='End date (YYYY-MM-DD)')
    
    
    args = parser.parse_args()

    if not args.office or not args.name:
        parser.error("--office and --name required")
    
    
    # Print pipeline configuration
    print("="*80)
    print("GAZETTE PROCESSING PIPELINE")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nConfiguration:")
    print(f"  Gazette Directory: {os.getenv('GAZETTE_DIR', 'scraped_pdf_files')}")
    print(f"  Output Directory:  {os.getenv('OUTPUT_DIR', 'OCR_outputs')}")

    print("="*80)
    
    success = True
    
    # Step 1: Scraping

    success = run_scraper(
            args.office,
            args.name,
            args.start_date,
            args.end_date
        )
    if not success:
        sys.exit(1)
    else:
        success2 = run_batch_processor(args.name)
        if not success2:
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
