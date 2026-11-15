"""
Batch processing pipeline for Turkish Trade Registry Gazettes
1. Runs OCR on all PDF files in gazette directory
2. Extracts structured data from each gazette using LLM
"""
import sys
import io
import os
from pathlib import Path
import json

# Force UTF-8 encoding for console output (Windows compatibility)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pymupdf
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import re
from pydantic import BaseModel, Field
from typing import Optional, List, Union
from enum import Enum
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import argparse
from rapidfuzz import fuzz, process

# Load environment variables
# Load environment variables from root
root_dir = Path(__file__).parent.parent
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

from layout_detector import analyze_page_layout, surya_layout_ocr

# Set Tesseract path (Windows default install location; Linux/macOS use tesseract from PATH)
if sys.platform == 'win32':
    pytesseract.pytesseract.tesseract_cmd = os.getenv(
        "TESSERACT_CMD", r'C:\Program Files\Tesseract-OCR\tesseract.exe')

# Initialize OpenAI client with timeout
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE"),
    timeout=120.0  # 2 minute timeout for API calls
)
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-oss-120b")

# ============================================================================
# IMPORT MODELS FROM test_ollama.py
# ============================================================================

# Universal Metadata (per-announcement, not gazette-level)
class UniversalMetadata(BaseModel):
    registry_office: str = Field(description="Trade Registry Office")
    registry_number: str = Field(description="Local registry number")
    mersis_no: str = Field(description="MERSİS number (16 digits)")
    company_name: str = Field(description="Official company name")
    announcement_number: Optional[str] = Field(default=None)

class AnnouncementType(str, Enum):
    COMMODITY_SALE = "şirket_emtiası_satışı"
    CAPITAL_DECREASE = "sermaye_azaltımı"
    ASSET_TRANSFER = "mal_varlığı_devri"
    LIQUIDATION = "tasfiye"
    SHARE_EXCHANGE = "pay_senedi_değişimi"
    MEETING_CALL = "toplantı_çağrısı"
    CAPITAL_COMMITMENT = "sermaye_taahhüdü"
    MERGER = "birleşme"
    BRANCH_ESTABLISHMENT = "şube_kuruluşu"
    ADDRESS_CHANGE = "adres_değişikliği"
    COMPOUND = "bileşik_değişiklik"
    UNKNOWN = "unknown"

class Company(BaseModel):
    name: str
    mersis_no: str
    registry_no: str
    address: Optional[str] = ""
    city: Optional[str] = None

class MergerAnnouncement(BaseModel):
    acquired_company: Company
    acquiring_company: Company
    registration_date: str
    deadline_for_creditors: str
    creditor_application_address: str
    announcement_type: str = "Birleşme"
    announcement_number: Optional[str] = None

class BranchEstablishmentAnnouncement(BaseModel):
    parent_company_name: str
    parent_company_mersis: str
    parent_company_address: str
    parent_company_capital: Optional[str] = None
    branch_name: str
    branch_address: str
    branch_manager: Optional[str] = None
    establishment_date: str

class AddressChangeAnnouncement(BaseModel):
    old_address: str
    new_address: str
    change_date: str
    registered_matters: Optional[str] = None

class CompoundAnnouncement(BaseModel):
    registered_matters: str
    registration_date: str
    changes: List[dict] = Field(default_factory=list)
    old_address: Optional[str] = None
    new_address: Optional[str] = None
    old_capital: Optional[str] = None
    new_capital: Optional[str] = None
    capital_breakdown: Optional[str] = None
    shareholders: Optional[List[dict]] = None
    notary_info: Optional[str] = None

class UnknownAnnouncement(BaseModel):
    """Fallback model for announcement types not in the enum"""
    original_detected_type: str = Field(description="The type detected by LLM that didn't match enum")
    extracted_data: dict = Field(default_factory=dict, description="Generic extracted fields")
    validation_error: Optional[str] = Field(default=None, description="Pydantic validation error")

class GazetteAnnouncement(BaseModel):
    metadata: UniversalMetadata
    announcement_type: AnnouncementType
    content: Union[MergerAnnouncement, BranchEstablishmentAnnouncement, AddressChangeAnnouncement, CompoundAnnouncement, UnknownAnnouncement, dict]
    raw_text: Optional[str] = None
    extraction_success: bool = True

class DetectedAnnouncement(BaseModel):
    section_text: str
    announcement_type: str
    mersis_no: Optional[str] = None
    company_name: Optional[str] = None
    registry_office: Optional[str] = None
    ilan_sira_no: Optional[str] = None

class GazetteExtraction(BaseModel):
    gazette_metadata: dict
    announcements: List[GazetteAnnouncement]
    extraction_stats: dict

# ============================================================================
# OCR FUNCTIONS (from pymuOCR.py)
# ============================================================================
def structure_gazette_text(raw_text):
    """Structure the gazette text with proper markdown headers"""
    lines = raw_text.split('\n')
    structured = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect gazette header
        if 'TICARET SICILI GAZETESİ' in line.upper() or 'TURKİYE TİCARET' in line.upper():
            structured.append(f"\n---\n\n# {line}\n")

        # Detect registry office
        elif 'TİCARET SİCİLİ MÜDÜRLÜĞÜ' in line.upper():
            structured.append(f"\n## {line}\n")

        # Detect company name
        elif 'TİCARET UNVAN' in line.upper() or 'TICARET UNVAN' in line.upper():
            if i + 1 < len(lines):
                company_name = lines[i + 1].strip()
                if company_name and len(company_name) > 5:
                    structured.append(f"\n### {company_name}\n")
                    structured.append(f"**Ticaret Unvanı:** {company_name}\n")
                    i += 1
                else:
                    structured.append(f"{line}\n")
            else:
                structured.append(f"{line}\n")

        # Format key fields
        elif line.startswith('İlan Sıra No:') or line.startswith('Ilan Sıra No:'):
            structured.append(f"\n**{line}**  \n")
        elif line.startswith('Mersis No:'):
            structured.append(f"**{line}**  \n")
        elif line.startswith('Ticaret Sicil') or line.startswith('Ticaret Sici/'):
            structured.append(f"**{line}**  \n")
        elif line.startswith('Adres :') or line.startswith('Adres:'):
            structured.append(f"**{line}**  \n")

        # Section headers
        elif 'Tescil Edilen Hususlar:' in line:
            structured.append(f"\n**Tescil Edilen Hususlar:** {line.split(':', 1)[1].strip() if ':' in line else ''}\n")
        elif 'Tescile Delil Olan Belgeler:' in line:
            structured.append(f"\n**Tescile Delil Olan Belgeler:** {line.split(':', 1)[1].strip() if ':' in line else ''}\n")

        # Numbered subheaders
        elif line and len(line) > 2 and line[0].isdigit() and line[1:3] in ['. ', '- ', ') ']:
            structured.append(f"\n#### {line}\n")

        else:
            if line:
                structured.append(f"{line}\n")

        i += 1

    return ''.join(structured)

def run_ocr_on_pdf(pdf_path: Path, output_md_path: Path) -> bool:
    """Run OCR on a single PDF and save as structured markdown"""
    try:
        ocr_start = datetime.now()
        print(f"\n  [STEP 1/2] OCR Processing: {pdf_path.name}", flush=True)
        print(f"    ⏱ Started at: {ocr_start.strftime('%H:%M:%S')}", flush=True)
        doc = pymupdf.open(str(pdf_path))
        print(f"    📄 Document has {len(doc)} page(s)", flush=True)

        all_text = ""
        for page_num, page in enumerate(doc, 1):
            progress_pct = (page_num / len(doc)) * 100
            # Create a simple progress bar
            bar_length = 20
            filled = int(bar_length * page_num / len(doc))
            bar = "█" * filled + "░" * (bar_length - filled)
            print(f"    📄 Page {page_num}/{len(doc)} [{bar}] {progress_pct:.0f}%...", end="", flush=True)

            # Convert PDF page to image
            pix = page.get_pixmap(dpi=400)
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))

            # Image preprocessing
            image = image.convert('L')
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            image = image.filter(ImageFilter.SHARPEN)
            image = image.filter(ImageFilter.MedianFilter(size=3))

            # Check layout and choose OCR method
            layout = analyze_page_layout(page)
            
            if layout.use_simple_split:
                # Standard 2-column: split in half
                width, height = image.size
                mid_point = width // 2
                custom_config = r'--oem 3 --psm 6'
                
                left_col = image.crop((0, 0, mid_point, height))
                left_text = pytesseract.image_to_string(left_col, lang='tur', config=custom_config)
                
                right_col = image.crop((mid_point, 0, width, height))
                right_text = pytesseract.image_to_string(right_col, lang='tur', config=custom_config)
                
                text = left_text + "\n\n=== RIGHT COLUMN ===\n\n" + right_text
            else:
                # Non-standard layout: use Surya
                print(f" [non-standard layout: {layout.num_columns_detected} cols]", end="", flush=True)
                text = surya_layout_ocr(page, debug_dir=output_md_path.parent / "debug")

            if text.strip():
                all_text += f"\n\n---\n**Sayfa {page_num}**\n---\n\n"
                all_text += text
                print(f" {len(text)} chars extracted")
            else:
                print(" WARNING: No text!")

        if all_text:
            print(f"    Structuring text with markdown headers...")
            # Structure the text
            structured_text = structure_gazette_text(all_text)

            # Add header
            final_text = "# Türkiye Ticaret Sicili Gazetesi\n\n"
            final_text += f"OCR Extraction Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            final_text += structured_text

            # Save
            output_md_path.write_text(final_text, encoding='utf-8')
            ocr_elapsed = (datetime.now() - ocr_start).total_seconds()
            print(f"    ✅ OCR Complete: {len(final_text)} chars → {output_md_path.name}")
            print(f"    ⏱ OCR Duration: {ocr_elapsed:.1f}s ({ocr_elapsed/len(doc):.1f}s/page)")
            return True
        else:
            print(f"    ❌ FAILED: No text extracted from PDF")
            return False

    except Exception as e:
        print(f"    ❌ OCR failed: {e}")
        return False

# ============================================================================
# EXTRACTION FUNCTIONS (from test_ollama.py)
# ============================================================================

def normalize_announcement_type(detected_type: str) -> str:
    """Normalize detected announcement types"""
    type_mapping = {
        "kuruluş": "şube_kuruluşu",
        "şube kuruluşu": "şube_kuruluşu",
        "şube": "şube_kuruluşu",
        "merkez değişikliği": "adres_değişikliği",
        "adres değişikliği": "adres_değişikliği",
        "şirketin merkezi": "adres_değişikliği",
        "sistem iletişim adresi": "adres_değişikliği",
        "iletişim adresi": "adres_değişikliği",
        "birleşme": "birleşme",
        "birlesme": "birleşme",
        "sermaye azaltımı": "sermaye_azaltımı",
        "tasfiye": "tasfiye",
        "mal varlığı devri": "mal_varlığı_devri",
        "toplantı çağrısı": "toplantı_çağrısı",
        "pay senedi değişimi": "pay_senedi_değişimi",
        "sermaye taahhüdü": "sermaye_taahhüdü",
        "şirket emtiası satışı": "şirket_emtiası_satışı",
        "bileşik": "bileşik_değişiklik",
        "çoklu": "bileşik_değişiklik",
    }

    detected_lower = detected_type.lower().strip()

    # Check for compound
    compound_indicators = [",", " ve ", "sermaye", "pay"]
    if sum(1 for ind in compound_indicators if ind in detected_lower) >= 2:
        if ("merkez" in detected_lower or "adres" in detected_lower) and \
           ("sermaye" in detected_lower or "pay" in detected_lower):
            return "bileşik_değişiklik"

    if detected_lower in type_mapping:
        return type_mapping[detected_lower]

    for key, value in type_mapping.items():
        if key in detected_lower or detected_lower in key:
            return value

    # Return original if no mapping found (will trigger fallback extraction)
    return detected_type

def split_gazette_into_sections(markdown_content: str) -> List[dict]:
    """Split gazette by announcement sections"""
    sections = []
    # Match headers with or without "T.C." prefix
    # Examples: "## T.C. ANKARA TİCARET SİCİLİ" or "## ANKARA TİCARET SİCİLİ"
    pattern = r'(## (?:T\.C\. )?.*?MÜDÜRLÜĞÜ.*?)(?=## (?:T\.C\. )?.*?MÜDÜRLÜĞÜ|$)'
    matches = re.findall(pattern, markdown_content, re.DOTALL)

    for idx, match in enumerate(matches):
        sections.append({'index': idx, 'text': match.strip()})

    return sections

def find_relevant_sections(gazette_content, company_name, threshold=80):
    """
    Parses the gazette content, identifies sections, and finds ones relevant to the company name.
    Also includes the gazette header for context.

    Args:
        gazette_content (str): The full string content of the markdown file.
        company_name (str): The company name to search for.
        threshold (int): The minimum fuzzy match confidence score (0-100) - used only for fallback.

    Returns:
        list[str]: A list of sections that match the company name.
    """
    # Split by registry office headers
    # The pattern looks for a line starting with '##' and containing 'MÜDÜR' (with or without 'T.C.')
    # Examples: "## T.C. ANKARA TİCARET SİCİLİ MÜDÜRLÜĞÜ" or "## ANKARA TİCARET SİCİLİ MÜDÜRLÜĞÜ"
    registry_sections = re.split(r'(?=^##.*MÜDÜR)', gazette_content, flags=re.MULTILINE)

    # Remove the first section (header part before registry offices)
    if registry_sections and not registry_sections[0].strip().startswith('##'):
        registry_sections = registry_sections[1:]

    relevant_sections = []
    company_name_upper = company_name.upper().strip()

    for registry_section in registry_sections:
        if not registry_section.strip():
            continue

        # Further split each registry section into individual company announcements
        # Announcements typically start with "**İlan Sıra No:**" pattern
        announcement_parts = re.split(r'(?=\*\*İlan Sıra No:)', registry_section)

        # Keep the registry header with the first announcement
        if len(announcement_parts) > 1:
            registry_header = announcement_parts[0]
            announcements = announcement_parts[1:]
        else:
            # No announcement pattern found, treat entire section as one announcement
            registry_header = ""
            announcements = [registry_section]

        for announcement in announcements:
            if not announcement.strip():
                continue

            # Combine with registry header for context
            full_announcement = (registry_header + "\n" + announcement).strip()
            announcement_upper = full_announcement.upper()

            # PRIMARY: Exact word match using word boundaries
            # This prevents "BAYKAR" from matching "BAYKARA" in substring search
            # Use regex to ensure we're matching complete words only
            exact_pattern = r'\b' + re.escape(company_name_upper) + r'\b'
            if re.search(exact_pattern, announcement_upper):
                relevant_sections.append(full_announcement)
                continue

            # SECONDARY: Fuzzy matching for OCR errors (e.g., "TURKCELL" vs "TURCELL")
            # Only if the company name is at least 5 chars to avoid false positives
            if len(company_name_upper) >= 5:
                # Extract potential company names from the announcement (lines with ###)
                # This prevents matching against the entire announcement text
                company_name_lines = re.findall(r'###\s*(.+)', full_announcement)

                for line in company_name_lines:
                    line_upper = line.upper().strip()

                    # Use partial_ratio to find the company name within the line
                    # partial_ratio finds the best matching substring
                    partial_score = fuzz.partial_ratio(company_name_upper, line_upper)

                    # High threshold to avoid false matches
                    # Also check that lengths are similar (within 20% difference)
                    # This prevents "BAYKAR" from matching "BAYKARA MİMARLIK YAPI..."
                    if partial_score >= 80:
                        # Extract just the company name part (before the first space after matching)
                        words_in_line = line_upper.split()
                        for i in range(len(words_in_line)):
                            # Check if this word or combination of words matches closely
                            for j in range(i, min(i + 3, len(words_in_line))):
                                candidate = ' '.join(words_in_line[i:j+1])

                                # Use ratio (Levenshtein distance) for matching
                                ratio_score = fuzz.ratio(company_name_upper, candidate)
                                len_diff = abs(len(candidate) - len(company_name_upper))

                                # Smart threshold based on length difference:
                                # - Same length (OCR errors like "BAYKA8"): use standard threshold (80)
                                # - Different length (like "BAYKARA"): require very high score (95+)
                                # This prevents "BAYKAR" from matching "BAYKARA" (score ~92)
                                # while still catching OCR errors like "BAYKA8" (score ~83)

                                if len_diff == 0:
                                    # Same length: allow OCR character substitutions
                                    if ratio_score >= threshold:
                                        relevant_sections.append(full_announcement)
                                        break
                                elif len_diff <= 2:
                                    # Different length by 1-2 chars: require near-perfect match
                                    # This rejects "BAYKARA" (92.3) but might allow very close OCR errors
                                    if ratio_score >= 95:
                                        relevant_sections.append(full_announcement)
                                        break
                            else:
                                continue
                            break
                        else:
                            continue
                        break

    return relevant_sections

def pre_detect_compound_announcements(markdown_content: str) -> dict:
    """Programmatically detect compound announcements"""
    compound_map = {}
    sections = split_gazette_into_sections(markdown_content)

    for section in sections:
        section_text = section['text']

        mersis_match = re.search(r'MERSİS No[:\s]+(\d{16})', section_text, re.IGNORECASE)
        mersis_no = mersis_match.group(1) if mersis_match else None

        tescil_pattern = r'\*\*Tescil Edilen Hususlar:\*\*\s*(.+?)(?=\n\*\*|\n\n|$)'
        tescil_match = re.search(tescil_pattern, section_text, re.DOTALL | re.IGNORECASE)

        if tescil_match and mersis_no:
            tescil_content = tescil_match.group(1).strip()

            has_comma = ',' in tescil_content
            has_multiple_types = (
                ('merkez' in tescil_content.lower() or 'adres' in tescil_content.lower()) and
                ('sermaye' in tescil_content.lower() or 'pay' in tescil_content.lower())
            )

            if has_comma or has_multiple_types:
                compound_map[mersis_no] = {
                    'is_compound': True,
                    'registered_matters': tescil_content,
                    'reason': 'comma_in_tescil' if has_comma else 'multiple_types_detected'
                }

    return compound_map

def extract_gazette_metadata_llm(markdown_content: str, model=None) -> dict:
    """Extract gazette-level metadata using LLM.
    
    This extracts date, number, and page from the gazette header using LLM
    to handle OCR variations robustly.
    """
    if model is None:
        model = MODEL_NAME
    
    metadata = {'date': None, 'number': None, 'page': None}

    # Only use the first part of the document (header area)
    # Increased to 10000 to ensure we capture both left and right columns of first page
    header_text = markdown_content[:10000]
    
    system_prompt = """You are an expert at extracting metadata from Turkish Trade Registry Gazettes.
Extract the gazette publication metadata from the OCR text.

IMPORTANT: The gazette header is split across LEFT and RIGHT columns. You must search the ENTIRE text carefully.

⚠️ CRITICAL - HANDLING FRAGMENTED TEXT:
OCR column splitting may cause text fragmentation. Be ROBUST to incomplete words:
- "TURKIYE TICARE" → truncated, but still indicates gazette context
- "I SICILI GAZETESI" → starts mid-word ("TİCARET SİCİLİ" split), but contains gazette keywords
- FOCUS ON EXTRACTING THE NUMBERS even if surrounding text is fragmented
- Example: "SAYFA : 704 TURKIYE TICARE" → extract page=704
- Example: "I SICILI GAZETESI 5 ARALIK 2025 SAYI: 11473" → extract date="5 ARALIK 2025", number=11473

METADATA TO EXTRACT:
1. gazette_date: Publication date in Turkish format with day, month name, and year
   - Format: "DD MONTH_NAME YYYY" (e.g., "2 ARALIK 2025", "27 KASIM 2025", "7 EKİM 2025")
   - Turkish months: OCAK, ŞUBAT, MART, NİSAN, MAYIS, HAZİRAN, TEMMUZ, AĞUSTOS, EYLÜL, EKİM, KASIM, ARALIK
   - Usually appears near "SAYI:"
   - May appear in fragmented context like "I SICILI GAZETESI 5 ARALIK 2025"

2. gazette_number: The SAYI (gazette issue number)
   - Look for "SAYI:" or "SAYI :" followed by 4-5 digits (e.g., 11470, 11452, 11431)
   - Usually appears near the date
   - Extract the number even if text around it is incomplete

3. gazette_page: The SAYFA (page number)
   - Look for "SAYFA:" or "SAYFA ;" or "SAYFA :" followed by 1-4 digits (e.g., 273, 894, 1152, 704)
   - Can be separated from date and SAYI
   - Extract the number even if followed by truncated text like "TURKIYE TICARE"

COMMON PATTERNS:
- Left column: "2 ARALIK 2025 SAYI: 11470" | Right column: "SAYFA: 273"
- Left column: "SAYFA ; 894" | Right column: "6 KASIM 2025 SAYI: 11452"
- Single location: "SAYFA :386 TÜRKİYE TİCARET SİCİLİ GAZETESİ 7 EKİM 2025 SAYI: 11431"
- Fragmented: "SAYFA : 704 TURKIYE TICARE" (extract 704) + "I SICILI GAZETESI 5 ARALIK 2025 SAYI: 11473" (extract date and number)

INSTRUCTIONS:
- Search BOTH "LEFT COLUMN" and "RIGHT COLUMN" (marked as "=== RIGHT COLUMN ===")
- Extract only the NUMERIC values for gazette_number and gazette_page (as integers)
- Extract the FULL date string for gazette_date (with Turkish month name)
- Be ROBUST to fragmented/truncated text - focus on the numbers and recognizable date patterns
- If you cannot find a field with certainty, use null for that field

Return JSON with gazette_date (string), gazette_number (integer), and gazette_page (integer)."""

    user_prompt = f"""Extract the gazette metadata from this text.
Search carefully through the entire text - metadata may be split between left and right columns.

Text:
{header_text}

Return JSON format:
{{
  "gazette_date": "DD MONTH_NAME YYYY",
  "gazette_number": number,
  "gazette_page": number
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            temperature=0.1,
            max_tokens=300
        )
        
        result_text = response.choices[0].message.content
        print(f"    📝 LLM metadata response: {result_text[:200] if result_text else 'None'}...", flush=True)
        if result_text:
            # Extract JSON from response (may be wrapped in markdown code block)
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0].strip()
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0].strip()
            
            result = json.loads(result_text)
            metadata['date'] = result.get('gazette_date')
            metadata['number'] = result.get('gazette_number')
            metadata['page'] = result.get('gazette_page')
    except Exception as e:
        print(f"    ⚠ LLM metadata extraction failed: {e}")
    
    return metadata


# Keep the old regex version commented out for reference
# def extract_gazette_metadata_regex(markdown_content: str) -> dict:
#     """Extract gazette-level metadata using regex (legacy)"""
#     metadata = {'date': None, 'number': None, 'page': None}
#     number_match = re.search(r'SAYI[:\s]+(\d+)', markdown_content, re.IGNORECASE)
#     if number_match:
#         metadata['number'] = int(number_match.group(1))
#     page_match = re.search(r'SAYFA\s*[:;]?\s*(\d{2,})', markdown_content, re.IGNORECASE)
#     if page_match:
#         metadata['page'] = int(page_match.group(1))
#     turkish_months = r'(?:OCAK|ŞUBAT|MART|NİSAN|MAYIS|HAZİRAN|TEMMUZ|AĞUSTOS|EYLÜL|EKİM|KASIM|ARALIK)'
#     date_patterns = [rf'(\d{{1,2}}\s+{turkish_months}\s+\d{{4}})', r'(\d{1,2}\.\d{1,2}\.\d{4})']
#     for pattern in date_patterns:
#         date_match = re.search(pattern, markdown_content[:2500], re.IGNORECASE)
#         if date_match:
#             metadata['date'] = date_match.group(1)
#             break
#     return metadata


def detect_announcement_types(gazette_content: str, model=None, company_filter: str = None) -> List[DetectedAnnouncement]:
    """Stage 1: Detect announcements using OpenAI-compatible API

    Args:
        gazette_content: The markdown content of the gazette
        model: LLM model to use
        company_filter: Optional company name to filter by (LLM will only detect this company)
    """
    if model is None:
        model = MODEL_NAME

    # Add filter info to the prompt if company filter is provided
    filter_instruction = ""
    if company_filter:
        filter_instruction = f"""
IMPORTANT FILTERING INSTRUCTION:
Only detect and return announcements for companies whose name contains or matches "{company_filter}".
- Use fuzzy matching - the company name may have slight variations or OCR errors
- Match partial names (e.g., "TURKCELL" should match "TURKCELL İLETİŞİM HİZMETLERİ A.Ş.")
- Include branches/subsidiaries that contain this name
- If no announcements match this company, return an empty array

"""
        print(f"    🔍 LLM filtering for company: '{company_filter}'", flush=True)

    print(f"    🤖 Calling LLM ({model}) for announcement detection...", flush=True)
    system_prompt = """You are a Turkish Trade Registry Gazette analyzer expert. Identify and classify announcements.

Classify into ONE of these PREDEFINED types:
- "birleşme": Merger (look for "devir", "birleşme", "devralan", "devrolan")
- "sermaye_azaltımı": Capital decrease (look for "sermaye azaltımı")
- "tasfiye": Liquidation (look for "tasfiye")
- "mal_varlığı_devri": Asset transfer (look for "mal varlığı devri")
- "şube_kuruluşu": Branch establishment (look for "şube", "kuruluş")
- "adres_değişikliği": Address change (look for "adres", "merkez değişikliği")
- "toplantı_çağrısı": Meeting call (look for "toplantı çağrısı", "genel kurul")
- "pay_senedi_değişimi": Share exchange (look for "pay senedi değişimi")
- "sermaye_taahhüdü": Capital commitment (look for "sermaye taahhüdü")
- "bileşik_değişiklik": COMPOUND - USE ONLY when announcement contains MORE THAN ONE of the above predefined types together (e.g., address change + capital change in same announcement). DO NOT use for single-type changes.
- "unknown": Use when the announcement type is NOT in the predefined list above

CRITICAL: "unknown" type includes (these are NOT compound):
- "Yönetim Kurulu / Yetkililer" (board/management changes)
- "Müdürler / Yetkililer" (manager/authority changes)
- "Denetçiler" (auditor changes)
- "İmza Yetkilisi" (signature authority changes)
- "Temsil Yetkisi" (representation authority changes)
- "Görev Dağılımındaki Değişiklik" (duty distribution changes)
- Any personnel/people changes

IMPORTANT RULES:
1. "bileşik_değişiklik" means MULTIPLE predefined types in ONE announcement - NOT for single types
2. "unknown" is for types NOT in predefined list - even if announcement has "/" or "ve" in the name
3. Board/management/personnel changes are ALWAYS "unknown", NEVER "bileşik_değişiklik"
4. You MUST return at least one announcement for each company section found

Return ONLY valid JSON."""

    user_prompt = f"""{filter_instruction}Analyze this gazette and identify announcements.

Return JSON with "announcements" array:
- section_text: excerpt (100-300 chars)
- announcement_type: one of the types above
- mersis_no: MERSİS number (16 digits)
- company_name: company name (full name from the gazette)
- registry_office: registry office name
- ilan_sira_no: İlan Sıra No (announcement serial number) - REQUIRED field, look for "İlan Sıra No:" or "Ilan Sıra No:"

Document:
{gazette_content[:64000]}

Return format:
{{
  "announcements": [
    {{
      "section_text": "excerpt...",
      "announcement_type": "birleşme",
      "mersis_no": "0608176080400001",
      "company_name": "COMPANY NAME",
      "registry_office": "ANKARA TİCARET SİCİLİ MÜDÜRLÜĞÜ",
      "ilan_sira_no": "123456"
    }}
  ]
}}

IMPORTANT:
1. Analyze the ENTIRE document. Don't miss announcements at the end.
2. ALWAYS extract the İlan Sıra No field - it appears near the top of each announcement section."""

    try:
        import time
        max_retries = 2
        retry_delay = 1  # seconds

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"    🔄 Retry attempt {attempt + 1}/{max_retries}...", flush=True)
                    time.sleep(retry_delay)

                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=8000
                )

                result_text = response.choices[0].message.content

                # Handle None response from LLM
                if result_text is None:
                    print(f"    ⚠ LLM returned None response (possibly content filter or error)")
                    if attempt < max_retries - 1:
                        continue  # Retry
                    return []

                print(f"    ✅ LLM response received ({len(result_text)} chars)")

                if '```json' in result_text:
                    result_text = result_text.split('```json')[1].split('```')[0].strip()
                elif '```' in result_text:
                    result_text = result_text.split('```')[1].split('```')[0].strip()

                parsed = json.loads(result_text)
                announcements = []
                for item in parsed.get('announcements', []):
                    announcements.append(DetectedAnnouncement(**item))

                print(f"    ✅ Successfully parsed {len(announcements)} announcement(s)")
                return announcements

            except Exception as retry_error:
                if attempt < max_retries - 1:
                    print(f"    ⚠ Attempt {attempt + 1} failed: {str(retry_error)[:100]}", flush=True)
                    continue  # Retry
                else:
                    raise  # Re-raise on final attempt

    except Exception as e:
        print(f"    ❌ Type detection failed after {max_retries} attempts: {e}")
        return []

def get_extraction_prompt_for_type(announcement_type: str, section_text: str) -> tuple:
    """Get type-specific prompts"""
    prompts = {
        "birleşme": {
            "system": """You are an expert in Turkish corporate mergers. Extract merger details accurately.""",
            "user": f"""Extract merger information.

Fields:
- acquired_company: {{name, mersis_no, registry_no, address, city}}
- acquiring_company: {{name, mersis_no, registry_no, address, city}}
- registration_date, deadline_for_creditors, creditor_application_address

Look for "devrolan" (acquired) and "Devralan" (acquiring).

Text: {section_text}

Return JSON."""
        },
        "şube_kuruluşu": {
            "system": """Extract branch establishment details.""",
            "user": f"""Extract: parent_company_name, parent_company_mersis, parent_company_address, branch_name, branch_address, establishment_date.

Text: {section_text}

Return JSON."""
        },
        "adres_değişikliği": {
            "system": """Extract address change details.""",
            "user": f"""Extract: old_address (after "adresinden"), new_address (after "adresine"), change_date, registered_matters.

Text: {section_text}

Return JSON."""
        },
        "bileşik_değişiklik": {
            "system": """You are an expert in Turkish Trade Registry Gazettes. Extract ALL information from announcements.
Return dynamic JSON with keys based on what is actually present. Do NOT include empty or null fields.
Be thorough - extract every piece of useful information.""",
            "user": f"""Extract ALL information from this Turkish Trade Registry announcement.

REQUIRED FIELD (MUST BE FIRST):
- changes_summary: Bu ilanın ne hakkında olduğunu özetleyen kısa bir açıklama IN TURKISH (1-2 cümle, TÜRKÇE YAZILMALI)

COMPANY INFO:
- company_name: full company name
- company_address: current address
- mersis_no: MERSİS number
- ticaret_sicil_no: Trade registry number
- ilan_sira_no: Announcement number
- registered_matters: what was registered (Tescil Edilen Hususlar)
- registration_date: when registered
- notary_info: notary details (look for "Noterliği", dates, numbers)

PERSONNEL CHANGES (if any):
- people_added: list of people added with {{name, role, authority_type}}
- people_removed: list of people removed with {{name, previous_role}}

ADDRESS CHANGES (if any):
- old_address, new_address

CAPITAL CHANGES (if any):
- old_capital, new_capital, capital_breakdown

SHAREHOLDERS (if any):
- shareholders: list with {{name, share_quantity, share_amount}}

GAZETTE METADATA (if visible in text):
- gazette_date: gazette publication date (e.g., "7 EKİM 2025")
- gazette_number: SAYI number (e.g., 11431)
- gazette_page: SAYFA number (e.g., 386)

Text:
{section_text}

IMPORTANT: Return JSON with changes_summary as the FIRST field (IN TURKISH), then include ONLY other fields that have actual values. Be comprehensive."""
        },
        "unknown": {
            "system": """You are an expert in Turkish Trade Registry Gazettes. Extract ALL available information from this announcement.
The announcement type is unknown or doesn't match standard categories (e.g., board changes, auditor changes, authority changes).
CRITICAL: The changes_summary field is MANDATORY and must be written IN TURKISH.""",
            "user": f"""Extract ALL information from this Turkish Trade Registry announcement.

⚠️ CRITICAL - REQUIRED FIELD (MUST BE FIRST):
- changes_summary: Bu ilanın ne hakkında olduğunu özetleyen kısa bir açıklama IN TURKISH (1-2 cümle, TÜRKÇE YAZILMALI)
  Example: "Şirketin yönetim kurulu üyelerinde değişiklik yapılmıştır."
  Example: "Şirketin denetçileri değişmiştir."

REQUIRED FIELDS:
- company_name: Full company name
- mersis_no: MERSİS number if present
- ticaret_sicil_no: Trade registry number if present
- registration_date: When this was registered (format: YYYY-MM-DD or DD.MM.YYYY)
- registered_matters: What was registered (Tescil Edilen Hususlar) - exact text from announcement

OPTIONAL FIELDS (include if found):
- company_address: Current address
- ilan_sira_no: Announcement number
- notary_info: Notary details (office, date, document number)
- key_people: List of people mentioned with their roles and actions (added/removed/changed)
- people_added: List of people added with {{name, role, details}}
- people_removed: List of people removed with {{name, previous_role}}
- additional_information: Any other relevant details

Text:
{section_text}

⚠️ IMPORTANT: Return JSON with changes_summary as the VERY FIRST field (WRITTEN IN TURKISH), followed by other fields. The changes_summary field is MANDATORY and cannot be null or empty."""
        }
    }

    default = {
        "system": f"""Extract {announcement_type} details.""",
        "user": f"""Extract information from {announcement_type}.\n\nText: {section_text}\n\nReturn JSON."""
    }

    prompt_set = prompts.get(announcement_type, default)
    return prompt_set["system"], prompt_set["user"]

def extract_announcement_fields(detected: DetectedAnnouncement, full_section: str, model=None) -> dict:
    """Stage 2: Extract fields using OpenAI-compatible API"""
    if model is None:
        model = MODEL_NAME
        
    system_prompt, user_prompt = get_extraction_prompt_for_type(detected.announcement_type, full_section)

    try:
        print(f"        🤖 Extracting fields via LLM...", end="", flush=True)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=3000
        )

        result_text = response.choices[0].message.content
        print(f" ✅")

        # Handle None response from LLM
        if result_text is None:
            print(f"        ⚠ LLM returned None response")
            return {}

        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()

        return json.loads(result_text)

    except Exception as e:
        print(f" ❌")
        print(f"        ✗ Field extraction failed: {e}")
        return {}

def extract_generic_fallback(section_text: str, announcement_type: str, model=None) -> dict:
    """
    Fallback extractor for unknown or failed announcement types using OpenAI-compatible API.
    Uses LLM to extract whatever valuable information is available.
    """
    if model is None:
        model = MODEL_NAME
        
    print(f"        🔄 Running generic fallback extractor...", end="", flush=True)
    system_prompt = """You are an expert in Turkish Trade Registry Gazettes.
Your task is to extract ANY valuable information from this announcement, even if you don't know the exact announcement type.

CRITICAL: You MUST include a changes_summary field IN TURKISH that describes what this announcement is about.

Extract whatever you can find:
- Summary of what changed (REQUIRED, IN TURKISH)
- Company information (name, MERSİS number, address)
- Dates (registration date, effective date, deadlines)
- People (managers, representatives, shareholders)
- Financial information (capital, amounts, payments)
- Legal references (notary info, laws, regulations)
- Changes or actions being announced
- Key terms or phrases that describe what's happening

Be thorough and extract everything that might be useful."""

    user_prompt = f"""This is a "{announcement_type}" announcement type that we don't have a specific extractor for.

Please extract ALL valuable information you can find from this text.

⚠️ REQUIRED FIRST FIELD:
- changes_summary: Bu ilanın ne hakkında olduğunu özetleyen kısa bir açıklama IN TURKISH (1-2 cümle, TÜRKÇE YAZILMALI)

Return JSON with fields like:
- changes_summary: REQUIRED - brief description IN TURKISH
- announcement_type: "{announcement_type}"
- company_info: {{name, mersis_no, address, etc}}
- key_dates: {{registration_date, effective_date, etc}}
- key_people: [list of people mentioned with roles]
- financial_info: {{any amounts, capital, etc}}
- legal_references: {{notary, law references, etc}}
- changes_announced: [list of what changed]
- additional_info: {{any other relevant data}}
- raw_key_phrases: [important Turkish phrases that might help identify type]

Text:
{section_text[:8000]}

⚠️ IMPORTANT: Return comprehensive JSON starting with changes_summary field IN TURKISH, then include ALL other information found."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=4000
        )

        result_text = response.choices[0].message.content

        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()

        extracted = json.loads(result_text)
        extracted['_extraction_method'] = 'generic_fallback'
        extracted['_original_type'] = announcement_type
        print(f" ✅")

        return extracted

    except Exception as e:
        print(f" ❌")
        print(f"        ✗ Generic fallback extraction failed: {e}")
        return {
            '_extraction_method': 'failed',
            '_original_type': announcement_type,
            '_error': str(e),
            'summary': f'Failed to extract {announcement_type}'
        }

def extract_from_markdown(md_path: Path, output_json_path: Path,
                         company_filter: Optional[str] = None,
                         city_filter: Optional[str] = None) -> bool:
    """
    Extract structured data from a markdown gazette

    Args:
        md_path: Path to markdown file
        output_json_path: Path for output JSON
        company_filter: Optional company name to filter by (LLM semantic matching)
        city_filter: Optional city name to filter by (registry office location)

    Returns:
        True if extraction succeeded, False otherwise
    """
    try:
        extraction_start = datetime.now()
        print(f"\n  [STEP 2/2] Data Extraction: {md_path.name}", flush=True)
        print(f"    ⏱ Started at: {extraction_start.strftime('%H:%M:%S')}", flush=True)

        gazette_content = md_path.read_text(encoding='utf-8')
        print(f"    📖 Read {len(gazette_content)} chars from markdown", flush=True)

        # Metadata extraction using LLM (more robust than regex)
        print(f"    [Stage 0/3] Extracting gazette metadata via LLM...", flush=True)
        gazette_metadata = extract_gazette_metadata_llm(gazette_content)
        print(f"    └─ Gazette #{gazette_metadata['number']}, Date: {gazette_metadata['date']}, Page {gazette_metadata['page']}", flush=True)

        # NEW: Pre-filter gazette content if company filter is provided
        # This saves LLM tokens by only passing relevant sections
        if company_filter:
            print(f"    [Stage 1/3] Pre-filtering gazette for: '{company_filter}'", flush=True)
            relevant_sections = find_relevant_sections(gazette_content, company_filter, threshold=80)
            
            if relevant_sections:
                # Combine relevant sections for LLM processing
                filtered_content = "\n\n---\n\n".join(relevant_sections)
                print(f"    ✅ Found {len(relevant_sections)} relevant section(s)", flush=True)
                print(f"    📉 Reduced from {len(gazette_content):,} → {len(filtered_content):,} chars ({100 - (len(filtered_content)/len(gazette_content)*100):.0f}% reduction)", flush=True)
            else:
                print(f"    ⚠ No matching sections found for '{company_filter}'", flush=True)
                # No relevant sections - save empty JSON and return
                output_data = {
                    'gazette_metadata': gazette_metadata,
                    'announcements': [],
                    'extraction_stats': {
                        'total_announcements': 0,
                        'successful_extractions': 0,
                        'failed_extractions': 0,
                        'fallback_extractions': 0
                    },
                    'filter_settings': {
                        'company_filter': company_filter,
                        'city_filter': city_filter,
                        'filter_method': 'pre_filter_find_relevant_sections',
                        'filter_applied': True,
                        'sections_found': 0
                    }
                }
                with open(output_json_path, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)
                print(f"    💾 Empty results file saved: {output_json_path.name}")
                extraction_elapsed = (datetime.now() - extraction_start).total_seconds()
                print(f"    ⏱ Duration: {extraction_elapsed:.1f}s")
                return True
        else:
            filtered_content = gazette_content
            print(f"    [Stage 1/3] No company filter - processing entire gazette", flush=True)

        # Stage 2: Detect announcement types via LLM (LLM decides ALL types including compound)
        print(f"    [Stage 2/3] Detecting announcement types via LLM...", flush=True)
        print(f"    📝 Content preview (first 300 chars): {filtered_content[:300]}...", flush=True)
        detected_announcements = detect_announcement_types(
            filtered_content,  # Use filtered content instead of full gazette
            company_filter=None  # No need for LLM filtering - we pre-filtered!
        )
        print(f"    └─ LLM detected {len(detected_announcements)} announcement(s)", flush=True)

        if not detected_announcements:
            print("    ⏹ No matching announcements to process after filtering. Skipping field extraction.", flush=True)
            # Create an empty JSON file and exit successfully
            output_data = {
                'gazette_metadata': gazette_metadata,
                'announcements': [],
                'extraction_stats': {
                    'total_announcements': 0,
                    'successful_extractions': 0,
                    'failed_extractions': 0,
                    'fallback_extractions': 0
                },
                'filter_settings': {
                    'company_filter': company_filter,
                    'city_filter': city_filter,
                    'filter_method': 'pre_filter_find_relevant_sections',
                    'filter_applied': True
                }
            }
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"    💾 Empty results file saved: {output_json_path.name}")
            extraction_elapsed = (datetime.now() - extraction_start).total_seconds()
            print(f"    ⏱ Duration: {extraction_elapsed:.1f}s")
            return True

        # Stage 3: Extract fields for each announcement
        print(f"    [Stage 3/3] Extracting fields (LLM Stage 2)...", flush=True)
        print(f"    🔄 Processing {len(detected_announcements)} announcement(s)...", flush=True)
        sections = split_gazette_into_sections(gazette_content)
        final_announcements = []

        for i, detected in enumerate(detected_announcements, 1):
            normalized_type = normalize_announcement_type(detected.announcement_type)
            company_short = (detected.company_name[:30] + '...') if detected.company_name and len(detected.company_name) > 30 else detected.company_name
            print(f"\n      📋 [{i}/{len(detected_announcements)}] {normalized_type}", flush=True)
            print(f"      🏢 Company: {company_short or 'N/A'}", flush=True)

            # Find relevant section
            relevant_section = None
            for section in sections:
                if detected.company_name and detected.company_name in section['text']:
                    relevant_section = section['text']
                    break
                elif detected.mersis_no and detected.mersis_no in section['text']:
                    relevant_section = section['text']
                    break

            if not relevant_section:
                relevant_section = gazette_content

            normalized_detected = DetectedAnnouncement(
                section_text=detected.section_text,
                announcement_type=normalized_type,
                mersis_no=detected.mersis_no,
                company_name=detected.company_name,
                registry_office=detected.registry_office
            )

            # Try structured extraction first
            extracted_fields = extract_announcement_fields(normalized_detected, relevant_section[:5000])

            metadata = UniversalMetadata(
                registry_office=detected.registry_office or "Unknown",
                registry_number="Unknown",
                mersis_no=detected.mersis_no or "Unknown",
                company_name=detected.company_name or "Unknown",
                announcement_number=detected.ilan_sira_no
            )

            # SPECIAL HANDLING FOR COMPOUND: Store as raw dict to preserve dynamic keys
            if normalized_type == "bileşik_değişiklik":
                # For compound types, create a raw dict announcement to avoid Pydantic adding null fields
                announcement = {
                    'metadata': metadata.model_dump(),
                    'announcement_type': normalized_type,
                    'content': extracted_fields if extracted_fields else {},
                    'raw_text': None,
                    'extraction_success': bool(extracted_fields)
                }
                final_announcements.append(announcement)
                continue  # Skip the Pydantic validation below

            # Try to create structured announcement for other types
            try:
                announcement = GazetteAnnouncement(
                    metadata=metadata,
                    announcement_type=normalized_type,
                    content=extracted_fields if extracted_fields else {},
                    raw_text=relevant_section[:500] if not extracted_fields else None,
                    extraction_success=bool(extracted_fields)
                )
                final_announcements.append(announcement)

            except Exception as validation_error:
                # Validation failed (e.g., unknown announcement type)
                print(f"        ⚠ Validation failed: {str(validation_error)[:80]}")
                print(f"        → Triggering FALLBACK extractor for: {normalized_type}")

                # Use generic fallback extractor
                fallback_data = extract_generic_fallback(
                    relevant_section[:5000],
                    normalized_type
                )

                # Create announcement with fallback data and UNKNOWN type
                try:
                    # Use the dedicated UNKNOWN enum value
                    unknown_content = UnknownAnnouncement(
                        original_detected_type=normalized_type,
                        extracted_data=fallback_data if isinstance(fallback_data, dict) else {},
                        validation_error=str(validation_error)[:200]
                    )

                    announcement = GazetteAnnouncement(
                        metadata=metadata,
                        announcement_type="unknown",
                        content=unknown_content,
                        raw_text=relevant_section[:1000],  # Include more raw text
                        extraction_success=False  # Mark as fallback
                    )

                    final_announcements.append(announcement)
                    print(f"        ✅ Fallback extraction completed (UNKNOWN type, generic data captured)")

                except Exception as fallback_error:
                    print(f"        ✗ Fallback also failed: {fallback_error}")
                    # Last resort: save raw data
                    announcement = {
                        'metadata': metadata.model_dump(),
                        'announcement_type': 'UNKNOWN',
                        'original_type': normalized_type,
                        'content': fallback_data,
                        'raw_text': relevant_section[:1000],
                        'extraction_success': False,
                        'error': str(validation_error)
                    }
                    final_announcements.append(announcement)
                    print(f"        ✓ Raw data saved for manual review")

        # Save results
        # Count successes (handle both GazetteAnnouncement objects and raw dicts)
        successful = 0
        fallback_count = 0
        for a in final_announcements:
            if isinstance(a, dict):
                if a.get('extraction_success', False):
                    successful += 1
                if a.get('content', {}).get('_is_fallback', False):
                    fallback_count += 1
            else:
                if a.extraction_success:
                    successful += 1
                if isinstance(a.content, dict) and a.content.get('_is_fallback', False):
                    fallback_count += 1

        # Prepare output with mixed types
        announcements_output = []
        for a in final_announcements:
            if isinstance(a, dict):
                announcements_output.append(a)
            else:
                announcements_output.append(a.model_dump())

        # Extract gazette metadata from first announcement's content (LLM extracted)
        if announcements_output:
            first_content = announcements_output[0].get('content', {})
            if isinstance(first_content, dict):
                # Use LLM-extracted values if available
                if first_content.get('gazette_date'):
                    gazette_metadata['date'] = first_content.get('gazette_date')
                if first_content.get('gazette_number'):
                    gazette_metadata['number'] = first_content.get('gazette_number')
                if first_content.get('gazette_page'):
                    gazette_metadata['page'] = first_content.get('gazette_page')

        output_data = {
            'gazette_metadata': gazette_metadata,
            'announcements': announcements_output,
            'extraction_stats': {
                'total_announcements': len(final_announcements),
                'successful_extractions': successful,
                'failed_extractions': len(final_announcements) - successful - fallback_count,
                'fallback_extractions': fallback_count
            }
        }

        # Add filter settings if company filter was applied
        if company_filter or city_filter:
            output_data['filter_settings'] = {
                'company_filter': company_filter,
                'city_filter': city_filter,
                'filter_method': 'llm_semantic',  # LLM does the filtering, not fuzzy match
                'filter_applied': True
            }

        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        # Final statistics
        extraction_elapsed = (datetime.now() - extraction_start).total_seconds()
        print(f"\n    ╔══════════════════════════════════════════╗")
        print(f"    ║  Extraction Summary                      ║")
        print(f"    ╠══════════════════════════════════════════╣")
        print(f"    ║  Total announcements: {len(final_announcements):3d}                 ║")
        print(f"    ║  ✓ Successful:        {successful:3d}                 ║")
        print(f"    ║  ⚠ Fallback:          {fallback_count:3d}                 ║")
        print(f"    ║  ✗ Failed:            {len(final_announcements) - successful - fallback_count:3d}                 ║")
        print(f"    ╠══════════════════════════════════════════╣")
        print(f"    ║  ⏱ Duration:          {extraction_elapsed:.1f}s                  ║")
        print(f"    ╚══════════════════════════════════════════╝")
        print(f"    💾 Output: {output_json_path.name}")
        return True

    except Exception as e:
        print(f"    ❌ EXTRACTION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# MAIN BATCH PROCESSING
# ============================================================================

def main():
    # Parse CLI arguments
    parser = argparse.ArgumentParser(
        description='Batch processing pipeline for Turkish Trade Registry Gazettes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Process all gazettes
  python batch_process_gazettes.py

  # Filter by company name (LLM semantic matching)
  python batch_process_gazettes.py --name "MICROSOFT"

  # Partial name matching works automatically
  python batch_process_gazettes.py --name "TURKCELL"

  # Process specific directory with filtering
  python batch_process_gazettes.py --gazette-dir ./my_pdfs --name "ACME"
        '''
    )

    parser.add_argument(
        '--name',
        type=str,
        default=None,
        help='Filter by company name using local fuzzy matching. '
             'Example: "MICROSOFT" will match "MICROSOFT YAZILIM TİCARET A.Ş." '
             'The script handles variations, OCR errors, and partial matches locally.'
    )

    parser.add_argument(
        '--office',
        type=str,
        default=None
    )

    parser.add_argument(
        '--gazette-dir',
        type=str,
        default=None,
        help='Directory containing gazette PDF files. Default: GAZETTE_DIR from .env or "scrapped_pdf_files"'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output directory for markdown and JSON. Default: OUTPUT_DIR from .env or "OCR_outputs"'
    )

    args = parser.parse_args()

    print("="*80)
    print("🚀 Batch Gazette Processing Pipeline")
    print("="*80)
    print(f"⏱ Pipeline started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Display filter settings if enabled
    if args.name:
        print("🔍 COMPANY NAME FILTER ENABLED (LLM Semantic Matching)")
        print(f"   Search term: '{args.name}'")
        print(f"   Method: AI-powered semantic matching")
        print(f"   Note: Only matching companies will be extracted to save LLM costs\n")

    # Configuration from environment variables or CLI args
    script_dir = Path(__file__).parent
    gazette_dir = script_dir / (args.gazette_dir or os.getenv("GAZETTE_DIR", "scrapped_pdf_files"))
    output_dir = script_dir / (args.output_dir or os.getenv("OUTPUT_DIR", "OCR_outputs"))

    # Create directories
    print("📁 Setting up directories...")
    gazette_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    (output_dir / "markdown").mkdir(exist_ok=True)
    (output_dir / "json").mkdir(exist_ok=True)
    print("✅ Directories ready")

    print(f"\n📂 Input directory: {gazette_dir}")
    print(f"📂 Output directory: {output_dir}")

    # Find all PDF files
    print(f"\n🔍 Scanning for PDF files...")
    pdf_files = list(gazette_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"\n❌ No PDF files found in {gazette_dir}")
        return

    print(f"✅ Found {len(pdf_files)} PDF file(s) to process")
    for i, pdf in enumerate(pdf_files, 1):
        print(f"   {i}. {pdf.name} ({pdf.stat().st_size / 1024:.1f} KB)")

    # Test OpenAI API connection
    print("\n🔌 Testing OpenAI API connection...")
    try:
        test_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {'role': 'user', 'content': 'Test connection'}
            ],
            max_tokens=5
        )
        print(f"✅ OpenAI API connection successful")
        print(f"📦 Using model: {MODEL_NAME}")
    except Exception as e:
        print(f"❌ Cannot connect to OpenAI API: {e}")
        print(f"   Please check your API key and base URL in .env file")
        return

    # Process each PDF
    total_processed = 0
    total_extracted = 0
    total_fallbacks = 0

    print("\n" + "="*80)
    print("🔄 STARTING BATCH PROCESSING")
    print("="*80)

    start_time = datetime.now()

    for idx, pdf_path in enumerate(pdf_files, 1):
        file_start_time = datetime.now()
        print(f"\n{'='*80}", flush=True)
        print(f"📄 [{idx}/{len(pdf_files)}] Processing: {pdf_path.name}", flush=True)
        print(f"⏱ Started at: {file_start_time.strftime('%H:%M:%S')}", flush=True)
        print("="*80, flush=True)

        # Step 1: OCR
        md_filename = pdf_path.stem + ".md"
        md_path = output_dir / "markdown" / md_filename

        if md_path.exists():
            print(f"  ⏭ [SKIP] Markdown already exists: {md_filename}")
        else:
            if not run_ocr_on_pdf(pdf_path, md_path):
                print(f"  ❌ Skipping extraction due to OCR failure")
                continue

        total_processed += 1

        # Step 2: Extract
        json_filename = pdf_path.stem + ".json"
        json_path = output_dir / "json" / json_filename

        if json_path.exists():
            print(f"  ⏭ [SKIP] JSON already exists: {json_filename}")
            total_extracted += 1

            # Count fallbacks from existing file
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    total_fallbacks += existing_data.get('extraction_stats', {}).get('fallback_extractions', 0)
            except:
                pass
        else:
            if extract_from_markdown(
                md_path=md_path,
                output_json_path=json_path,
                company_filter=args.name,
                city_filter=args.office
            ):
                total_extracted += 1

                # Count fallbacks from new extraction
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        new_data = json.load(f)
                        total_fallbacks += new_data.get('extraction_stats', {}).get('fallback_extractions', 0)
                except:
                    pass

        # File completion summary
        file_elapsed = (datetime.now() - file_start_time).total_seconds()
        file_elapsed_min = int(file_elapsed // 60)
        file_elapsed_sec = int(file_elapsed % 60)
        print(f"\n  ✅ File complete: {pdf_path.name}", flush=True)
        print(f"  ⏱ File duration: {file_elapsed_min}m {file_elapsed_sec}s", flush=True)
        print(f"  📊 Progress: {idx}/{len(pdf_files)} files ({(idx/len(pdf_files)*100):.0f}%)", flush=True)

        # Estimate time remaining
        if idx < len(pdf_files):
            avg_time_per_file = (datetime.now() - start_time).total_seconds() / idx
            remaining_files = len(pdf_files) - idx
            est_remaining_sec = avg_time_per_file * remaining_files
            est_remaining_min = int(est_remaining_sec // 60)
            est_remaining_sec_part = int(est_remaining_sec % 60)
            print(f"  ⏳ Est. time remaining: ~{est_remaining_min}m {est_remaining_sec_part}s ({remaining_files} file(s) left)", flush=True)

    # Summary
    elapsed_time = datetime.now() - start_time
    elapsed_seconds = int(elapsed_time.total_seconds())
    elapsed_minutes = elapsed_seconds // 60
    elapsed_secs = elapsed_seconds % 60

    print("\n" + "="*80)
    print("╔═══════════════════════════════════════════════════════════════════════════════╗")
    print("║                        BATCH PROCESSING COMPLETE                              ║")
    print("╠═══════════════════════════════════════════════════════════════════════════════╣")
    print(f"║  PDFs found:           {len(pdf_files):3d}                                                   ║")
    print(f"║  PDFs processed:       {total_processed:3d} / {len(pdf_files):3d}                                             ║")
    print(f"║  Extractions:          {total_extracted:3d} / {len(pdf_files):3d}                                             ║")
    if total_fallbacks > 0:
        print(f"║  ⚠ Fallback extractions: {total_fallbacks:3d} (unknown types - review recommended)        ║")
    print(f"║  Time elapsed:         {elapsed_minutes}m {elapsed_secs}s                                               ║")
    if args.name:
        print("╠═══════════════════════════════════════════════════════════════════════════════╣")
        print(f"║  🔍 Filter applied:    '{args.name[:50]:<50s}' ║")
        print(f"║     Method:            LLM Semantic Matching                                  ║")
    print("╠═══════════════════════════════════════════════════════════════════════════════╣")
    print(f"║  Output Directory: {str(output_dir):<55s} ║")
    print(f"║    → Markdown: {str(output_dir / 'markdown'):<59s} ║")
    print(f"║    → JSON:     {str(output_dir / 'json'):<59s} ║")
    print("╚═══════════════════════════════════════════════════════════════════════════════╝")

    if total_fallbacks > 0:
        print(f"\n⚠ NOTE: {total_fallbacks} announcement(s) used fallback extraction.")
        print("  Review JSON files with '_is_fallback: true' to identify new announcement types.")
        print("  Add them to type_mapping in normalize_announcement_type() for better extraction.")

    print(f"\n{'='*80}")
    print("✅ ALL PROCESSING COMPLETE!")
    print(f"⏱ Total elapsed time: {elapsed_minutes}m {elapsed_secs}s")
    print(f"📊 Success rate: {(total_extracted/len(pdf_files)*100):.1f}% ({total_extracted}/{len(pdf_files)})")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
