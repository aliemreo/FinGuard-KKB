"""
KKB Hackathon - Configuration Settings
Tüm proje ayarları bu dosyada merkezi olarak yönetilir
"""

import os
from dotenv import load_dotenv

load_dotenv()
# ============================================================================
# MOCK DATA TOGGLE
# ============================================================================
USE_MOCK_DATA = True  # False yaparak gerçek veritabanına geçebilirsiniz


# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "kkb_hackathon"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "your_password_here")
}


# ============================================================================
# OPENAI API CONFIGURATION
# ============================================================================
OPENAI_CONFIG = {
    "base_url": os.getenv("OPENAI_BASE_URL", "https://mia.csp.kloudeks.com/v1"),
    "api_key": os.getenv("OPENAI_API_KEY", "sk-XXXX"),
    "model": os.getenv("OPENAI_MODEL", "gpt-oss-120b"),
    "temperature": 0.7,
    "max_tokens": 2000
}


# ============================================================================
# FILE PATHS
# ============================================================================
TEMPLATE_DIR = "templates"
STATIC_DIR = "static"
OUTPUT_DIR = "output"

TEMPLATE_FILE = f"{TEMPLATE_DIR}/report_template.html"
CSS_FILE = f"{STATIC_DIR}/style.css"


# ============================================================================
# REPORT SETTINGS
# ============================================================================
REPORT_CONFIG = {
    "page_size": "A4",
    "margin": "2cm",
    "default_output_name": "firma_raporu.pdf",
    "logo_url": "https://via.placeholder.com/200x200?text=KKB+Logo",
    "company_name": "Kredi Kayıt Bürosu A.Ş.",
    "year": "2024"
}


# ============================================================================
# LOGGING
# ============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
