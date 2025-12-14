# TTSG_Agent Pipeline Documentation

Automated pipeline for scraping, OCR processing, and extracting structured data from Turkish Trade Registry Gazettes (TTSG).

---

## 📊 Pipeline Architecture Overview

```mermaid
flowchart TB
    subgraph INPUT["🎯 INPUT"]
        CLI["CLI Arguments<br/>--office --name<br/>--start-date --end-date"]
    end

    subgraph ORCHESTRATOR["🔄 ORCHESTRATOR (app.py)"]
        direction TB
        MAIN["main()"]
        CHECK["check_crawl_history_str()"]
        GAP["Gap Detection"]
        LOOP["Gap Processing Loop"]
    end

    subgraph SCRAPING["📥 SCRAPING (ticaret_sicil_scraper.py)"]
        direction TB
        LOGIN["TicaretSicilLogin"]
        CAPTCHA["solve_captcha_with_vlm()"]
        SEARCH["fetch_trade_registry_announcement()"]
        FILTER["filter_results_by_date()"]
        DOWNLOAD["download_pdf_from_results()"]
    end

    subgraph PROCESSING["⚙️ BATCH PROCESSING (batch_process_gazettes.py)"]
        direction TB
        OCR["run_ocr_on_pdf()<br/>PyMuPDF + Tesseract"]
        DETECT["detect_announcement_types()<br/>LLM Stage 1"]
        EXTRACT["extract_announcement_fields()<br/>LLM Stage 2"]
        FALLBACK["extract_generic_fallback()"]
    end

    subgraph CONVERSION["🔄 DATA CONVERSION (json_to_ilanlar.py)"]
        direction TB
        PARSE["process_json_file()"]
        ANNO["process_announcement()"]
        CONVERT["convert_json_to_ilanlar()"]
    end

    subgraph DATABASE["🗄️ DATABASE (db/)"]
        direction TB
        IMPORT["import_to_postgres.py"]
        UTILS["db_utils.py"]
        PG[("PostgreSQL<br/>gazette_db")]
    end

    subgraph REPORT["📄 REPORT (report-ofe/)"]
        GENERATOR["generator.py"]
        HTML["Final_Report.html"]
    end

    CLI --> MAIN
    MAIN --> CHECK
    CHECK --> GAP
    GAP --> LOOP
    LOOP --> |"For each gap"| SCRAPING
    SCRAPING --> PROCESSING
    PROCESSING --> CONVERSION
    CONVERSION --> DATABASE
    DATABASE --> REPORT
    IMPORT --> PG
    UTILS --> PG
    GENERATOR --> HTML
```

---

## 🔄 Main Orchestrator Flow (`app.py`)

### Entry Point: `main()`

```mermaid
flowchart TD
    START([Start]) --> PARSE["Parse CLI Arguments<br/>--office, --name, --start-date, --end-date"]
    PARSE --> STEP1["<b>STEP 1:</b> Check Crawling History<br/>check_crawl_history_str()"]
    
    STEP1 --> GAPS{Gaps Found?}
    
    GAPS -->|No| EXPORT["Export existing data<br/>fetch_ilanlar_by_date_range()"]
    EXPORT --> END1([End - Data Already Exists])
    
    GAPS -->|Yes| CLEANUP["initial_cleanup()<br/>Reset ilanlar.json"]
    CLEANUP --> STEP25["<b>STEP 2.5:</b> Fetch Existing Data<br/>from database for existing ranges"]
    
    STEP25 --> GAPLOOP["<b>GAP PROCESSING LOOP</b><br/>for gap_idx, gap in enumerate(gaps)"]
    
    subgraph LOOP["Gap Processing Loop"]
        GAPLOOP --> CLEAN["clean_gap_directories()<br/>Clear PDF & OCR folders"]
        CLEAN --> SCRAPE["run_scraper()<br/>ticaret_sicil_scraper.py"]
        SCRAPE --> BATCH["run_batch_processor()<br/>batch_process_gazettes.py"]
        BATCH --> META["create_crawl_metadata()"]
        META --> JSON["run_json_converter()<br/>json_to_ilanlar.py"]
        JSON --> RECORD["insert_crawl_history_str()<br/>Record in database"]
        RECORD --> NEXT{More Gaps?}
        NEXT -->|Yes| GAPLOOP
    end
    
    NEXT -->|No| STEP4["<b>STEP 4:</b> run_import_to_postgres()"]
    STEP4 --> STEP5["<b>STEP 5:</b> run_report_generator()"]
    STEP5 --> SUMMARY["Print Final Summary"]
    SUMMARY --> END2([End - Pipeline Complete])
```

### Key Functions in `app.py`

| Function | Purpose | Called By |
|----------|---------|-----------|
| `main()` | Main orchestrator entry point | CLI |
| `initial_cleanup()` | Reset `ilanlar.json` to empty array | `main()` |
| `clean_gap_directories()` | Clear PDF and OCR output folders | Gap loop |
| `create_crawl_metadata()` | Create `crawl_metadata.json` | Gap loop |
| `run_scraper()` | Execute web scraper subprocess | Gap loop |
| `run_batch_processor()` | Execute OCR + extraction subprocess | Gap loop |
| `run_json_converter()` | Execute JSON format converter | Gap loop |
| `run_import_to_postgres()` | Import data to PostgreSQL | `main()` |
| `run_report_generator()` | Generate HTML report | `main()` |

---

## 📥 Web Scraping Module (`ticaret_sicil_scraper.py`)

### Class: `TicaretSicilLogin`

```mermaid
flowchart TD
    subgraph INIT["Initialization"]
        SETUP["setup_driver()<br/>Chrome WebDriver"]
    end
    
    subgraph AUTH["Authentication"]
        LOGIN["login()"]
        CAPTCHA["solve_captcha_with_vlm()<br/>Ollama VLM (minicpm-v)"]
        PDFCAP["solve_pdf_captcha()"]
    end
    
    subgraph SEARCH["Search & Filter"]
        FETCH["fetch_trade_registry_announcement()<br/>Navigate to results"]
        FILTER["filter_results_by_date()<br/>Apply date range"]
        SET["set_items_per_page(100)"]
    end
    
    subgraph PAGINATION["Pagination Loop"]
        HAS["has_next_page()"]
        NEXT["go_to_next_page()"]
        COLLECT["collect_pdf_urls_from_current_page()"]
    end
    
    subgraph DOWNLOAD["PDF Download"]
        ALL["collect_all_pdf_urls()"]
        META["extract_pdf_metadata_from_table()"]
        DL["download_pdf_from_results()"]
        REQ["download_pdf_with_requests()"]
    end
    
    INIT --> AUTH
    AUTH --> SEARCH
    SEARCH --> PAGINATION
    PAGINATION --> DOWNLOAD
```

### Key Methods

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__()` | 34-41 | Initialize driver, credentials |
| `setup_driver()` | 43-79 | Configure Chrome WebDriver |
| `solve_captcha_with_vlm()` | 235-478 | VLM-based CAPTCHA solving |
| `login()` | 555-729 | Website authentication |
| `fetch_trade_registry_announcement()` | 751-972 | Search for announcements |
| `filter_results_by_date()` | 974-1218 | Apply date filtering |
| `extract_pdf_metadata_from_table()` | 1275-1351 | Get PDF metadata |
| `download_pdf_from_results()` | 1599-1812 | Download all PDFs |

---

## ⚙️ Batch Processing Module (`batch_process_gazettes.py`)

### Processing Pipeline

```mermaid
flowchart TD
    subgraph MAIN["main() - Batch Loop"]
        SCAN["Scan for PDF files<br/>gazette_dir.glob('*.pdf')"]
        PDFLOOP["FOR each pdf_path in pdf_files"]
    end
    
    subgraph OCR["OCR Stage"]
        RUNOC["run_ocr_on_pdf()"]
        STRUCT["structure_gazette_text()"]
        SAVE_MD["Save .md file"]
    end
    
    subgraph EXTRACT["Extraction Stages"]
        EXTMD["extract_from_markdown()"]
        
        subgraph STAGE0["Stage 0: Metadata"]
            META["extract_gazette_metadata_llm()<br/>Date, Number, Page"]
        end
        
        subgraph STAGE1["Stage 1: Pre-filter"]
            FILTER["find_relevant_sections()<br/>Fuzzy company matching"]
        end
        
        subgraph STAGE2["Stage 2: Detection"]
            DETECT["detect_announcement_types()<br/>LLM identifies types"]
            SPLIT["split_gazette_into_sections()"]
        end
        
        subgraph STAGE3["Stage 3: Extraction"]
            LOOP["FOR each detected_announcement"]
            GETPROMPT["get_extraction_prompt_for_type()"]
            EXTFIELDS["extract_announcement_fields()<br/>LLM extracts structured data"]
            FALLBACK["extract_generic_fallback()<br/>For unknown types"]
        end
    end
    
    subgraph OUTPUT["Output"]
        SAVE_JSON["Save .json file"]
        STATS["Extraction Statistics"]
    end
    
    SCAN --> PDFLOOP
    PDFLOOP --> RUNOC
    RUNOC --> STRUCT
    STRUCT --> SAVE_MD
    SAVE_MD --> EXTMD
    EXTMD --> STAGE0
    STAGE0 --> STAGE1
    STAGE1 --> STAGE2
    STAGE2 --> STAGE3
    STAGE3 --> SAVE_JSON
    SAVE_JSON --> STATS
    STATS --> |Next PDF| PDFLOOP
```

### Data Models (Pydantic)

| Model | Purpose |
|-------|---------|
| `UniversalMetadata` | Registry office, MERSİS no, company name |
| `AnnouncementType` | Enum of 11 announcement types |
| `GazetteAnnouncement` | Complete announcement with metadata + content |
| `DetectedAnnouncement` | LLM detection result |
| `MergerAnnouncement` | Merger-specific fields |
| `BranchEstablishmentAnnouncement` | Branch setup fields |
| `AddressChangeAnnouncement` | Address change fields |
| `CompoundAnnouncement` | Mixed/complex announcements |
| `UnknownAnnouncement` | Fallback for unknown types |

### Announcement Types (`AnnouncementType` Enum)

```python
COMMODITY_SALE      = "şirket_emtiası_satışı"   # 1
CAPITAL_DECREASE    = "sermaye_azaltımı"        # 2
ASSET_TRANSFER      = "mal_varlığı_devri"       # 3
LIQUIDATION         = "tasfiye"                  # 4
SHARE_EXCHANGE      = "pay_senedi_değişimi"     # 5
MEETING_CALL        = "toplantı_çağrısı"        # 6
CAPITAL_COMMITMENT  = "sermaye_taahhüdü"        # 7
MERGER              = "birleşme"                 # 8
BRANCH_ESTABLISHMENT= "şube_kuruluşu"           # 9
ADDRESS_CHANGE      = "adres_değişikliği"       # 10
COMPOUND            = "bileşik_değişiklik"      # 11
UNKNOWN             = "unknown"
```

---

## 🔄 Data Conversion Module (`json_to_ilanlar.py`)

### Conversion Flow

```mermaid
flowchart LR
    subgraph INPUT["OCR Output JSONs"]
        JSON1["gazette_1.json"]
        JSON2["gazette_2.json"]
        JSONN["gazette_N.json"]
    end
    
    subgraph PROCESS["Processing"]
        CONVERT["convert_json_to_ilanlar()"]
        PROCFILE["process_json_file()"]
        PROCANNO["process_announcement()"]
        PARSEDATE["parse_turkish_date()"]
    end
    
    subgraph OUTPUT["Database Input"]
        ILANLAR["ilanlar.json"]
    end
    
    JSON1 --> CONVERT
    JSON2 --> CONVERT
    JSONN --> CONVERT
    CONVERT --> PROCFILE
    PROCFILE --> PROCANNO
    PROCANNO --> PARSEDATE
    PARSEDATE --> ILANLAR
```

### Key Transformations

| Source Field | Target Field | Transformation |
|--------------|--------------|----------------|
| `announcement_type` | `ilan_turu` | String → Integer mapping |
| `gazette_metadata.date` | `ilan_tarihi` | Turkish → ISO date |
| `filter_settings.city_filter` | `il` | City name → Plaka code |
| `metadata.announcement_number` | `ilan_no` | Direct mapping |
| `metadata.company_name` | `unvan` | Direct mapping |
| `raw_text` | `metin` | Full announcement text |

---

## 🗄️ Database Module (`db/`)

### `db_utils.py` - Core Utilities

```mermaid
flowchart TD
    subgraph POOL["Connection Pool"]
        GETPOOL["_get_pool()"]
        CONNECT["connect_to_db()"]
        RELEASE["release_connection()"]
    end
    
    subgraph HISTORY["Crawling History"]
        CHECK["check_crawl_history()<br/>Find existing/missing ranges"]
        INSERT["insert_crawl_history()<br/>Record new crawl"]
    end
    
    subgraph FETCH["Data Retrieval"]
        FETCHIL["fetch_ilanlar_by_date_range()<br/>Export existing records"]
    end
    
    subgraph MODELS["Data Models"]
        RANGE["DateRange<br/>start, end dates"]
        RESULT["CrawlRangeResult<br/>existing_ranges, missing_ranges"]
    end
    
    POOL --> HISTORY
    POOL --> FETCH
    HISTORY --> MODELS
```

### `import_to_postgres.py` - Data Import

```mermaid
flowchart TD
    MAIN["main()"] --> CREATE["create_database_if_not_exists()"]
    CREATE --> INIT["initialize_schema()<br/>database_schema.sql"]
    INIT --> LOADMETA["load_crawl_metadata()"]
    LOADMETA --> LOADIL["load_ilanlar()"]
    LOADIL --> RECORD["record_crawl_history()"]
    RECORD --> IMPORT["import_ilanlar()<br/>Loop: insert_ilan()"]
    IMPORT --> STATS["print_database_stats()"]
```

---

## 📁 Directory Structure

```
TTSG_Agent/
├── app.py                      # 🔄 Main orchestrator
├── ticaret_sicil_scraper.py    # 📥 Web scraper (2050 lines)
├── batch_process_gazettes.py   # ⚙️ OCR + extraction (1536 lines)
├── json_to_ilanlar.py          # 🔄 Data converter (375 lines)
├── layout_detector.py          # 📐 Layout detection
├── scrapped_pdf_files/         # 📄 Downloaded PDFs
└── OCR_outputs/
    ├── markdown/               # 📝 OCR text output
    └── json/                   # 📊 Structured data

db/
├── db_utils.py                 # 🔧 Database utilities
├── import_to_postgres.py       # 📥 Data importer
├── database_schema.sql         # 🗄️ Schema definition
└── db_Input/
    ├── crawl_metadata.json     # 📋 Crawl session info
    └── ilanlar.json            # 📊 Announcements data

report-ofe/
└── generator.py                # 📄 Report generator
```

---

## 🚀 Quick Start

```bash
# Full pipeline execution
python app.py --office ANKARA --name TURKCELL --start-date 2024-01-01 --end-date 2024-12-31

# Only batch processing (PDFs already downloaded)
python batch_process_gazettes.py --name "MICROSOFT"

# Only JSON conversion
python json_to_ilanlar.py

# Only database import
python ../db/import_to_postgres.py
```

---

## ⚙️ Configuration (`.env`)

```env
# Scraper credentials
EMAIL=your_email@example.com
PASSWORD=your_password

# Directories
GAZETTE_DIR=scrapped_pdf_files
OUTPUT_DIR=OCR_outputs

# LLM API
OPENAI_API_KEY=sk-XXXX
OPENAI_API_BASE=https://mia.csp.kloudeks.com/v1
OPENAI_MODEL=gpt-oss-120b

# Database
POSTGRES_DB=gazette_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=1234
DB_HOST=localhost
POSTGRES_PORT=5432
```

---

## 📊 Data Flow Summary

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Web Portal    │────▶│   PDF Files     │────▶│   Markdown      │
│  ticaretsicil   │     │  (.pdf)         │     │  (.md)          │
│   .gov.tr       │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │                       │                       │
        ▼                       ▼                       ▼
   CAPTCHA SOLVE           OCR (PyMuPDF            LLM EXTRACTION
   + DOWNLOAD              + Tesseract)            (OpenAI API)
                                                        │
                                                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   PostgreSQL    │◀────│  ilanlar.json   │◀────│   JSON Files    │
│   gazette_db    │     │  (converted)    │     │  (structured)   │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐
│  HTML Report    │
│  Final_Report   │
└─────────────────┘
```

---

## 🔑 Key Processing Loops

### 1. Gap Processing Loop (`app.py:403-434`)
```
FOR each gap in gaps:
    1. clean_gap_directories()
    2. run_scraper(office, name, gap_start, gap_end)
    3. run_batch_processor(name)
    4. create_crawl_metadata(...)
    5. run_json_converter()
    6. insert_crawl_history_str(...)
```

### 2. PDF Processing Loop (`batch_process_gazettes.py:1428-1486`)
```
FOR each pdf_path in pdf_files:
    1. run_ocr_on_pdf(pdf_path, md_path)
    2. extract_from_markdown(md_path, json_path, company_filter)
```

### 3. Announcement Extraction Loop (`batch_process_gazettes.py:1116-1222`)
```
FOR each detected in detected_announcements:
    1. normalize_announcement_type()
    2. Find relevant_section
    3. extract_announcement_fields()
    4. IF validation fails → extract_generic_fallback()
    5. Append to final_announcements
```

### 4. Pagination Loop (`ticaret_sicil_scraper.py:1447-1481`)
```
WHILE has_next_page():
    1. collect_pdf_urls_from_current_page()
    2. go_to_next_page()
```

---

## 📝 Notes

- **CAPTCHA**: Requires manual solving or VLM (Ollama minicpm-v model)
- **OCR**: Uses PyMuPDF for rendering + Tesseract for text extraction
- **LLM**: OpenAI-compatible API for announcement detection and field extraction
- **Database**: PostgreSQL with connection pooling via psycopg2
