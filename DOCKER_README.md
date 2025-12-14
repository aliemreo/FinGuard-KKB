# KKB Docker Setup

## Quick Start

```bash
# 1. Copy and edit environment variables
cp .env.example .env
# Edit .env with your passwords

# 2. Start PostgreSQL + pgAdmin
docker-compose up -d

# 3. Wait for database to be ready
docker-compose logs -f postgres

# 4. Import JSON data
cd db
pip install psycopg2-binary python-dotenv
python import_json.py --json-dir ../TTSG_Agent/OCR_outputs/json
```

## Services

| Service | URL | Credentials |
|---------|-----|-------------|
| PostgreSQL | `localhost:5435` | See `.env` |
| pgAdmin | http://localhost:5050 | `admin@kkb.local` / `admin` |

## Commands

```bash
# Start containers
docker-compose up -d

# Stop containers
docker-compose down

# View logs
docker-compose logs -f

# Reset database (WARNING: deletes all data)
docker-compose down -v
docker-compose up -d
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Your Machine                       │
├─────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────┐    │
│  │           Docker Containers                  │    │
│  │  ┌─────────────┐   ┌─────────────┐          │    │
│  │  │  PostgreSQL │   │   pgAdmin   │          │    │
│  │  │   :5435     │   │    :5050    │          │    │
│  │  └─────────────┘   └─────────────┘          │    │
│  └─────────────────────────────────────────────┘    │
│                         ↑                            │
│                    import_json.py                    │
│                         ↑                            │
│  ┌─────────────────────────────────────────────┐    │
│  │  TTSG_Agent (runs locally)                   │    │
│  │  • batch_process_gazettes.py                 │    │
│  │  • ticaret_sicil_scraper.py                  │    │
│  │  • OCR + Tesseract + Surya                   │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```
