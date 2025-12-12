# Trade Registry Gazette Pipeline

Automated pipeline for scraping, OCR processing, and extracting structured data from Turkish Trade Registry Gazettes.

## Quick Start

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Tesseract OCR**
   - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
   - Linux: `sudo apt-get install tesseract-ocr tesseract-ocr-tur`
   - macOS: `brew install tesseract tesseract-lang`

3. **Install Surya OCR (for complex layouts)**
   ```bash
   # For GPU support:
   pip install surya-ocr torch torchvision --index-url https://download.pytorch.org/whl/cu118
   
   # For CPU only:
   pip install surya-ocr
   ```

4. **Configure `.env` file**
   ```env
   # Required
   GAZETTE_DIR=scraped_pdf_files
   OUTPUT_DIR=OCR_outputs
   EMAIL=your_email@example.com
   PASSWORD=your_password
   OPENAI_API_KEY=sk-XXXX
   OPENAI_API_BASE=https://mia.csp.kloudeks.com/v1
   OPENAI_MODEL=gpt-oss-120b
   ```

5. **Run the pipeline**
   ```bash
   # Full pipeline (scrape + process)
   python app.py --office ANKARA --number 31177 --start-date 2024-01-01 --end-date 2024-12-31
   
   # Only processing (PDFs already exist)
   python app.py --process-only
   
   # Parallel processing (faster)
   python app.py --process-only --parallel
   
   # Debug mode
   python app.py --process-only --debug
   ```

## Pipeline Steps

1. **Scraping** (`ticaret_sicil_scraper.py`)
   - Logs into Trade Registry website
   - **⚠️ MANUAL CAPTCHA REQUIRED**: You must solve the CAPTCHA in the browser window
   - Downloads gazette PDFs automatically after login
   - Saves to `GAZETTE_DIR`

2. **Processing** (`batch_process_gazettes.py` or `parallel_batch_process.py`)
   - OCR extraction from PDFs
   - Layout detection (simple 2-column or complex Surya-based)
   - LLM-powered structured data extraction
   - Outputs: Markdown + JSON

## Outputs

- **PDFs**: `GAZETTE_DIR/`
- **Markdown**: `OUTPUT_DIR/markdown/`
- **JSON**: `OUTPUT_DIR/json/`

## Notes

- Scraper requires **manual CAPTCHA solving** in browser
- Complex layouts use Surya OCR (GPU recommended)
- OpenAI-compatible API used for data extraction
- Parallel mode processes multiple PDFs simultaneously
