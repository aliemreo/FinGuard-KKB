"""
Parallel Batch Processing Pipeline for Turkish Trade Registry Gazettes
Processes multiple PDF files simultaneously using multiprocessing
Uses subprocess to avoid serialization issues with wrapped file handles
"""
import sys
import os
from pathlib import Path
import json
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import subprocess
import traceback

# Set UTF-8 encoding via environment variable (multiprocessing-safe)
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

import ollama

# ============================================================================
# SINGLE FILE PROCESSOR SCRIPT
# ============================================================================

# Create a standalone processor script that will be called for each file
PROCESSOR_SCRIPT = """
import sys
from pathlib import Path

# Get arguments
pdf_path = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
file_index = int(sys.argv[3])
total_files = int(sys.argv[4])
project_dir = sys.argv[5]  # Parent directory containing batch_process_gazettes.py

# Add project directory to Python path so we can import the module
sys.path.insert(0, project_dir)

# Import processing functions
from batch_process_gazettes import run_ocr_on_pdf, extract_from_markdown
import json

# Setup paths
md_path = output_dir / "markdown" / (pdf_path.stem + ".md")
json_path = output_dir / "json" / (pdf_path.stem + ".json")

print(f"\\n{'='*80}", flush=True)
print(f"🔄 [{file_index}/{total_files}] Processing: {pdf_path.name}", flush=True)
print("="*80, flush=True)

# Step 1: OCR
if md_path.exists():
    print(f"  ⏭ [SKIP] Markdown exists: {md_path.name}", flush=True)
    ocr_success = True
else:
    ocr_success = run_ocr_on_pdf(pdf_path, md_path)

if not ocr_success:
    print(f"  ❌ OCR failed", flush=True)
    sys.exit(1)

# Step 2: Extraction
if json_path.exists():
    print(f"  ⏭ [SKIP] JSON exists: {json_path.name}", flush=True)
    extraction_success = True
else:
    extraction_success = extract_from_markdown(md_path, json_path)

if extraction_success:
    # Get fallback count
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            fallback_count = data.get('extraction_stats', {}).get('fallback_extractions', 0)
            print(f"FALLBACK_COUNT:{fallback_count}", flush=True)
    except:
        pass
    print(f"\\n  ✅ COMPLETE: {pdf_path.name}", flush=True)
    sys.exit(0)
else:
    print(f"  ❌ Extraction failed", flush=True)
    sys.exit(1)
"""

# ============================================================================
# PARALLEL PROCESSING FUNCTIONS
# ============================================================================

def process_single_gazette(args):
    """
    Process a single gazette file using subprocess
    This runs in a separate process and calls another Python subprocess
    """
    pdf_path, output_dir, file_index, total_files, processor_script_path, project_dir = args

    start_time = datetime.now()

    try:
        # Call the processor script as a subprocess
        result = subprocess.run(
            [sys.executable, str(processor_script_path),
             str(pdf_path), str(output_dir), str(file_index), str(total_files), str(project_dir)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # Print the output from the subprocess
        if result.stdout:
            print(result.stdout, flush=True)

        if result.stderr and result.returncode != 0:
            print(result.stderr, flush=True)

        # Parse fallback count from output
        fallback_count = 0
        for line in result.stdout.split('\n'):
            if line.startswith('FALLBACK_COUNT:'):
                try:
                    fallback_count = int(line.split(':')[1])
                except:
                    pass

        duration = (datetime.now() - start_time).total_seconds()

        return {
            'file': pdf_path.name,
            'success': result.returncode == 0,
            'fallback_count': fallback_count,
            'duration': duration,
            'error': None if result.returncode == 0 else f"Exit code: {result.returncode}"
        }

    except Exception as e:
        error_msg = f"Error processing {pdf_path.name}: {str(e)}"
        print(f"\n  ❌ {error_msg}", flush=True)
        traceback.print_exc()

        return {
            'file': pdf_path.name,
            'success': False,
            'error': error_msg,
            'duration': (datetime.now() - start_time).total_seconds(),
            'fallback_count': 0
        }

def print_progress_table(results, total_files):
    """Print a progress table showing all files and their status"""
    print("\n" + "="*80, flush=True)
    print("📊 PARALLEL PROCESSING PROGRESS", flush=True)
    print("="*80, flush=True)

    completed = len(results)
    in_progress = total_files - completed

    print(f"Progress: {completed}/{total_files} files completed ({in_progress} in progress)", flush=True)
    print(f"\nCompleted files:", flush=True)

    for i, result in enumerate(results, 1):
        status = "✅" if result['success'] else "❌"
        duration = result['duration']
        duration_min = int(duration // 60)
        duration_sec = int(duration % 60)

        print(f"  {status} [{i}] {result['file']} - {duration_min}m {duration_sec}s", flush=True)
        if result.get('error'):
            print(f"      Error: {result['error']}", flush=True)

    print("="*80 + "\n", flush=True)

# ============================================================================
# MAIN PARALLEL PROCESSING
# ============================================================================

def main():
    print("="*80)
    print("🚀 PARALLEL Batch Gazette Processing Pipeline")
    print("="*80)
    print(f"⏱ Pipeline started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Configuration
    gazette_dir = Path(r"c:\Users\aliem\Desktop\KKB\gazettes")
    output_dir = Path(r"c:\Users\aliem\Desktop\KKB\gazette_outputs")

    # Number of parallel workers (adjust based on your CPU cores and RAM)
    MAX_WORKERS = 3  # Start with 3 workers, adjust as needed

    print(f"⚙️  Configuration:")
    print(f"   - Max parallel workers: {MAX_WORKERS}")
    print(f"   - This means up to {MAX_WORKERS} PDFs will be processed simultaneously\n")

    # Create directories
    print("📁 Setting up directories...")
    gazette_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    (output_dir / "markdown").mkdir(exist_ok=True)
    (output_dir / "json").mkdir(exist_ok=True)
    print("✅ Directories ready")

    # Create temporary processor script
    temp_processor = output_dir / "_temp_processor.py"
    temp_processor.write_text(PROCESSOR_SCRIPT, encoding='utf-8')
    print(f"✅ Created temporary processor script")

    print(f"\n📂 Input directory: {gazette_dir}")
    print(f"📂 Output directory: {output_dir}")

    # Find all PDF files
    print(f"\n🔍 Scanning for PDF files...")
    pdf_files = list(gazette_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"\n❌ No PDF files found in {gazette_dir}")
        print("   Please add PDF files to the gazettes directory")
        if temp_processor.exists():
            temp_processor.unlink()
        return

    print(f"✅ Found {len(pdf_files)} PDF file(s) to process")
    for i, pdf in enumerate(pdf_files, 1):
        print(f"   {i}. {pdf.name} ({pdf.stat().st_size / 1024:.1f} KB)")

    # Test Ollama connection
    print("\n🔌 Testing Ollama connection...")
    try:
        models = ollama.list()
        print("✅ Ollama server is running")
        print(f"📦 Available models: {len(models.get('models', []))} model(s)")

        model_names = [m.get('name', '') for m in models.get('models', [])]
        if any('qwen2.5:7b' in name for name in model_names):
            print("✅ Target model 'qwen2.5:7b' is available")
        else:
            print("⚠ Warning: 'qwen2.5:7b' not found, extraction may fail")
    except Exception as e:
        print(f"❌ Cannot connect to Ollama: {e}")
        print("   Please ensure Ollama is running: 'ollama serve'")
        if temp_processor.exists():
            temp_processor.unlink()
        return

    # Get project directory (where batch_process_gazettes.py is located)
    project_dir = Path(__file__).parent.absolute()

    # Prepare arguments for parallel processing
    process_args = [
        (pdf_path, output_dir, idx, len(pdf_files), temp_processor, project_dir)
        for idx, pdf_path in enumerate(pdf_files, 1)
    ]

    print("\n" + "="*80)
    print(f"🔄 STARTING PARALLEL PROCESSING ({MAX_WORKERS} workers)")
    print("="*80)
    print(f"⚠️  Note: Output from parallel workers may be interleaved\n")

    start_time = datetime.now()
    results = []

    # Process files in parallel
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(process_single_gazette, args): args[0].name
            for args in process_args
        }

        # Process completed tasks as they finish
        for future in as_completed(future_to_file):
            filename = future_to_file[future]
            try:
                result = future.result()
                results.append(result)

                # Show progress update
                print_progress_table(results, len(pdf_files))

            except Exception as e:
                print(f"❌ Exception processing {filename}: {e}", flush=True)
                traceback.print_exc()
                results.append({
                    'file': filename,
                    'success': False,
                    'error': str(e),
                    'duration': 0,
                    'fallback_count': 0
                })

    # Clean up temporary processor script
    if temp_processor.exists():
        temp_processor.unlink()
        print(f"\n✅ Cleaned up temporary files")

    # Final Summary
    elapsed_time = datetime.now() - start_time
    elapsed_seconds = int(elapsed_time.total_seconds())
    elapsed_minutes = elapsed_seconds // 60
    elapsed_secs = elapsed_seconds % 60

    # Calculate statistics
    successful = sum(1 for r in results if r['success'])
    failed = len(results) - successful
    total_fallbacks = sum(r.get('fallback_count', 0) for r in results)

    # Calculate average time per file
    avg_time = elapsed_seconds / len(pdf_files) if pdf_files else 0
    avg_time_min = int(avg_time // 60)
    avg_time_sec = int(avg_time % 60)

    # Calculate total processing time (sum of all individual times)
    total_processing_time = sum(r['duration'] for r in results)
    total_proc_min = int(total_processing_time // 60)
    total_proc_sec = int(total_processing_time % 60)

    # Calculate speedup
    speedup = total_processing_time / elapsed_seconds if elapsed_seconds > 0 else 1

    print("\n" + "="*80)
    print("╔═══════════════════════════════════════════════════════════════════════════════╗")
    print("║                   PARALLEL BATCH PROCESSING COMPLETE                          ║")
    print("╠═══════════════════════════════════════════════════════════════════════════════╣")
    print(f"║  PDFs found:            {len(pdf_files):3d}                                                  ║")
    print(f"║  ✅ Successful:          {successful:3d}                                                  ║")
    print(f"║  ❌ Failed:              {failed:3d}                                                  ║")
    if total_fallbacks > 0:
        print(f"║  ⚠️  Fallback extractions: {total_fallbacks:3d} (unknown types)                            ║")
    print("╠═══════════════════════════════════════════════════════════════════════════════╣")
    print(f"║  ⏱ Wall-clock time:     {elapsed_minutes}m {elapsed_secs}s                                            ║")
    print(f"║  📊 Total CPU time:      {total_proc_min}m {total_proc_sec}s (sum of all workers)                  ║")
    print(f"║  ⚡ Speedup:             {speedup:.2f}x (parallel efficiency)                      ║")
    print(f"║  📈 Avg time per file:   {avg_time_min}m {avg_time_sec}s                                            ║")
    print(f"║  👥 Workers used:        {MAX_WORKERS}                                                    ║")
    print("╠═══════════════════════════════════════════════════════════════════════════════╣")
    print(f"║  Output Directory: {str(output_dir):<55s} ║")
    print(f"║    → Markdown: {str(output_dir / 'markdown'):<59s} ║")
    print(f"║    → JSON:     {str(output_dir / 'json'):<59s} ║")
    print("╚═══════════════════════════════════════════════════════════════════════════════╝")

    # Show failed files if any
    if failed > 0:
        print(f"\n❌ Failed files ({failed}):")
        for result in results:
            if not result['success']:
                print(f"   - {result['file']}")
                if result.get('error'):
                    print(f"     Error: {result['error']}")

    # Show fallback warning
    if total_fallbacks > 0:
        print(f"\n⚠️  NOTE: {total_fallbacks} announcement(s) used fallback extraction.")
        print("  Review JSON files with '_is_fallback: true' to identify new announcement types.")
        print("  Add them to type_mapping in normalize_announcement_type() for better extraction.")

    print(f"\n{'='*80}")
    print("✅ ALL PARALLEL PROCESSING COMPLETE!")
    print(f"⏱ Completed in: {elapsed_minutes}m {elapsed_secs}s (wall-clock time)")
    print(f"⚡ Parallel speedup: {speedup:.2f}x faster than sequential processing")
    print(f"📊 Success rate: {(successful/len(pdf_files)*100):.1f}% ({successful}/{len(pdf_files)})")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
