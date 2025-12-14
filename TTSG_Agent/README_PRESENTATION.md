# TTSG Pipeline — Presentation Overview

> Agentic pipeline for automated extraction and structuring of Turkish Trade Registry Gazettes.

---

## 📊 Data Flow At-a-Glance

```mermaid
flowchart LR
    GOV["🌐 Gov Site<br/>(CAPTCHA)"] --> PDF["📄 PDFs"]
    PDF --> MD["📝 Markdown<br/>(OCR)"]
    MD --> LLM["🤖 LLM<br/>Extraction"]
    LLM --> JSON["📊 Structured<br/>JSON"]
    JSON --> DB[("🗄️ PostgreSQL<br/>Database")]
    DB --> REPORT["📋 HTML<br/>Report"]
```

---

## 🌐 Schema 1: General Pipeline Overview

This schema shows the high-level flow from user input to final database storage and reporting.

```mermaid
flowchart TB
    subgraph INPUT["🎯 User Input"]
        direction LR
        CLI["Command Line<br/>Office, Company<br/>Date Range"]
    end

    subgraph ORCHESTRATOR["🧠 Central Orchestrator"]
        direction TB
        HISTORY["Check History<br/>(Gap Detection)"]
        LOOP["Process Each Gap"]
    end

    subgraph SCRAPING["📥 Web Acquisition"]
        FETCH["Authenticate &<br/>Download PDFs"]
    end

    subgraph INTELLIGENCE["🤖 Agentic Processing"]
        direction TB
        OCR["Document OCR"]
        STAGE1["Type Detection<br/>(LLM Stage 1)"]
        STAGE2["Field Extraction<br/>(LLM Stage 2)"]
    end

    subgraph STORAGE["🗄️ Data Layer"]
        direction LR
        CONVERT["Format<br/>Conversion"]
        DB[("PostgreSQL<br/>Database")]
        REPORT["📊 HTML Report"]
    end

    CLI --> HISTORY
    HISTORY --> |"Gaps Found"| LOOP
    HISTORY --> |"No Gaps"| DB
    LOOP --> FETCH
    FETCH --> OCR
    OCR --> STAGE1
    STAGE1 --> STAGE2
    STAGE2 --> CONVERT
    CONVERT --> DB
    DB --> REPORT
```

### 🔌 External Dependencies

| Purpose | Technology |
|---------|------------|
| LLM Intelligence | GPT-OSS-120B (OpenAI API) |
| Database | PostgreSQL + psycopg2 |

---

## 🧠 Schema 2: Orchestrator Agent (`app.py`)

This schema illustrates the intelligent orchestration logic that coordinates the entire pipeline.

```mermaid
flowchart TD
    START([Start]) --> PARSE["Parse User Arguments"]
    PARSE --> HISTORY["Query Crawl History"]
    
    HISTORY --> CHECK{Gaps in<br/>Coverage?}
    
    CHECK --> |"No"| EXPORT["Export Existing Data"]
    EXPORT --> END1([Complete])
    
    CHECK --> |"Yes"| INIT["Initialize<br/>Clean State"]
    
    INIT --> GAPLOOP["🔄 FOR EACH GAP"]
    
    subgraph GAP_PROCESSING["Gap Processing Cycle"]
        GAPLOOP --> CLEAN["Clear Temp<br/>Directories"]
        CLEAN --> SCRAPE["▶ Execute<br/>Web Scraper"]
        SCRAPE --> BATCH["▶ Execute<br/>Batch Processor"]
        BATCH --> META["Generate<br/>Metadata"]
        META --> CONVERT["▶ Execute<br/>JSON Converter"]
        CONVERT --> RECORD["Record to<br/>History Database"]
        RECORD --> NEXT{More<br/>Gaps?}
        NEXT --> |"Yes"| GAPLOOP
    end
    
    NEXT --> |"No"| IMPORT["▶ Import to<br/>PostgreSQL"]
    IMPORT --> REPORT["▶ Generate<br/>HTML Report"]
    REPORT --> SUMMARY["Print Summary"]
    SUMMARY --> END2([Pipeline Complete])
```

### 🔌 External Dependencies

| Purpose | Technology |
|---------|------------|
| Database Queries | PostgreSQL + psycopg2 |

---

## 🌐 Schema 3: Web Acquisition (Minimal)

A simplified view of the web scraping authentication and download process.

```mermaid
flowchart LR
    subgraph AUTH["🔐 Authentication"]
        direction TB
        INIT["Initialize<br/>WebDriver"]
        CAPTCHA["Solve CAPTCHA<br/>(VLM Agent)"]
        LOGIN["Submit<br/>Credentials"]
    end

    subgraph SEARCH["🔍 Search"]
        QUERY["Execute Query"]
        FILTER["Apply Filters<br/>(Date, Office)"]
    end

    subgraph DOWNLOAD["📥 Acquisition"]
        PAGINATE["Paginate<br/>Results"]
        SAVE["Download<br/>PDF Files"]
    end

    INIT --> CAPTCHA
    CAPTCHA --> LOGIN
    LOGIN --> QUERY
    QUERY --> FILTER
    FILTER --> PAGINATE
    PAGINATE --> SAVE
```

### 🔌 External Dependencies

| Purpose | Technology |
|---------|------------|
| CAPTCHA Solving | Ollama VLM (minicpm-v) |
| Browser Automation | Selenium WebDriver |

---

## 🤖 Schema 4: Agentic Batch Processor (`batch_process_gazettes.py`)

This is the **core intelligence layer** — a multi-stage LLM-powered extraction pipeline.

```mermaid
flowchart TD
    START["📄 PDF Documents"] --> SCAN["Scan Directory"]
    SCAN --> PDFLOOP["🔄 FOR EACH PDF"]
    
    subgraph OCR_STAGE["📖 Document Understanding"]
        PDFLOOP --> RENDER["Render Pages<br/>(PyMuPDF)"]
        RENDER --> EXTRACT_TEXT["Extract Text<br/>(Tesseract OCR)"]
        EXTRACT_TEXT --> STRUCTURE["Structure as<br/>Markdown"]
    end
    
    subgraph LLM_STAGE_0["🔍 Stage 0: Metadata Extraction"]
        STRUCTURE --> META_LLM["LLM: Extract<br/>Gazette Metadata"]
        META_LLM --> META_OUT["Date, Number,<br/>Page Info"]
    end
    
    subgraph PREFILTER["📋 Stage 1: Pre-filtering"]
        META_OUT --> FUZZY["Fuzzy Company<br/>Name Matching"]
        FUZZY --> RELEVANT["Identify Relevant<br/>Sections"]
    end
    
    subgraph LLM_STAGE_1["🧠 Stage 2: Type Detection"]
        RELEVANT --> DETECT_LLM["LLM: Classify<br/>Announcement Type"]
        DETECT_LLM --> TYPES["11 Announcement<br/>Categories"]
        TYPES --> SPLIT["Split into<br/>Sections"]
    end
    
    subgraph LLM_STAGE_2["🎯 Stage 3: Field Extraction"]
        SPLIT --> LOOP["🔄 FOR EACH<br/>ANNOUNCEMENT"]
        LOOP --> PROMPT["Select Type-Specific<br/>Prompt Template"]
        PROMPT --> EXTRACT_LLM["LLM: Extract<br/>Structured Fields"]
        EXTRACT_LLM --> VALIDATE{Valid?}
        VALIDATE --> |"No"| FALLBACK["Generic<br/>Fallback Extraction"]
        VALIDATE --> |"Yes"| COLLECT["Collect Result"]
        FALLBACK --> COLLECT
    end
    
    COLLECT --> SAVE["💾 Save JSON"]
    SAVE --> STATS["Update Statistics"]
    STATS --> |"Next PDF"| PDFLOOP
    STATS --> END["✅ Complete"]
```

### 🏷️ Announcement Type Categories

| # | Type | Description |
|---|------|-------------|
| 1 | Commodity Sale | Sale of company goods |
| 2 | Capital Decrease | Reduction in capital |
| 3 | Asset Transfer | Transfer of assets |
| 4 | Liquidation | Company dissolution |
| 5 | Share Exchange | Stock exchange |
| 6 | Meeting Call | Shareholder meeting |
| 7 | Capital Commitment | Capital pledges |
| 8 | Merger | Company merger |
| 9 | Branch Establishment | New branch |
| 10 | Address Change | Location update |
| 11 | Compound | Multiple changes |

### 🔌 External Dependencies

| Purpose | Technology |
|---------|------------|
| PDF Rendering | PyMuPDF (fitz) |
| Text Extraction | Tesseract OCR |
| LLM Intelligence | GPT-OSS-120B (OpenAI API) |
| Data Validation | Pydantic |

---

## 🗄️ Database Schema

### Entity Relationship Diagram

```mermaid
erDiagram
    GAZETTES ||--o{ ANNOUNCEMENTS : contains
    CRAWLING_HISTORY ||--o| GAZETTES : tracks

    GAZETTES {
        int id PK
        date gazette_date
        int gazette_number
        int gazette_page
        varchar source_file
        timestamp created_at
    }

    ANNOUNCEMENTS {
        int id PK
        int gazette_id FK
        varchar registry_office
        varchar registry_number
        varchar mersis_no
        varchar company_name
        varchar announcement_number
        varchar announcement_type
        text company_address
        date registration_date
        text changes_summary
        jsonb content
        varchar city
        timestamp created_at
    }

    CRAWLING_HISTORY {
        int id PK
        varchar company_filter
        varchar city_filter
        daterange fetched_period
        timestamp created_at
    }
```

### Table Descriptions

| Table | Purpose |
|-------|---------|
| `gazettes` | Stores gazette-level metadata (date, number, page) |
| `announcements` | Individual announcements with company info and extracted fields |
| `crawling_history` | Tracks previously fetched date ranges to avoid redundant scraping |

### Key Fields in `announcements`

| Field | Description |
|-------|-------------|
| `mersis_no` | 16-digit unique company identifier |
| `company_name` | Full legal company name |
| `announcement_type` | One of 11 categories (merger, liquidation, etc.) |
| `content` | JSONB field with type-specific extracted data |
| `city` | Derived from registry office location |

### 🔌 External Dependencies

| Purpose | Technology |
|---------|------------|
| Database | PostgreSQL 15+ |
| Connection Pooling | psycopg2 |
