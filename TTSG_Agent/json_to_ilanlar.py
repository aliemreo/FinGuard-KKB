#!/usr/bin/env python3
"""
JSON to ilanlar.json Converter

Converts multiple OCR output JSON files to a single ilanlar.json format
for database import.

Key handling:
- Normal announcements: 1 JSON announcement → 1 ilanlar entry
- bileşik_değişiklik with content.announcements[]: 1 JSON → N ilanlar entries
- bileşik_değişiklik with direct content: 1 JSON → 1 ilanlar entry
- Empty announcements: Only gazette metadata is preserved, rest is null

Field mappings:
- ilan_no ← metadata.announcement_number
- il ← filter_settings.city_filter (city name as string)
- adres ← metadata.address
- metin ← raw_text
- detaylar ← content (entire object or sub-announcement)
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional


# ============================================================================
# ANNOUNCEMENT TYPE MAPPING (string → integer for database)
# ============================================================================

# REVERSE MAPPING: Database String Types -> Generator Integer Codes
ILAN_TURU_MAP = {
    "emtia_satışı": 1,
    "sermaye_azaltımı": 2,
    "mal_varlığı_devri": 3,
    "tasfiye": 4,
    "pay_senedi_değişimi": 5,
    "toplantı_çağrısı": 6,
    "sermaye_taahhüdü": 7,
    "birleşme": 8,
    "şube_kuruluşu": 9,
    "adres_değişikliği": 10,
    "unknown": 11,
    # Map other potential types to 'unknown' (11) or specific codes
    "bileşik_değişiklik": 11, 
    "genel_kurul": 6,
    "kuruluş": 9,
}


def parse_turkish_date(date_str: str) -> Optional[str]:
    """Convert Turkish date formats to ISO format (YYYY-MM-DD)."""
    if not date_str:
        return None
    
    # Already in ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    
    # Turkish month names
    turkish_months = {
        "OCAK": 1, "ŞUBAT": 2, "MART": 3, "NİSAN": 4,
        "MAYIS": 5, "HAZİRAN": 6, "TEMMUZ": 7, "AĞUSTOS": 8,
        "EYLÜL": 9, "EYLUL": 9, "EKİM": 10, "KASIM": 11, "ARALIK": 12
    }
    
    # Try "17 TEMMUZ 2025" format
    match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_str.upper())
    if match:
        day, month_name, year = match.groups()
        month = turkish_months.get(month_name)
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    
    return None


def process_announcement(
    announcement: dict,
    gazette_metadata: dict,
    filter_settings: Optional[dict] = None
) -> List[dict]:
    """
    Process a single announcement and return ilanlar entries.
    
    Returns a list because compound announcements with content.announcements[]
    produce multiple entries.
    """
    entries = []
    
    ann_type = announcement.get('announcement_type', '')
    metadata = announcement.get('metadata', {})
    content = announcement.get('content', {})
    raw_text = announcement.get('raw_text')
    
    # Get gazette info
    gazette_date = parse_turkish_date(gazette_metadata.get('date'))
    gazette_number = gazette_metadata.get('number')
    
    # Get city from filter_settings (as string, not plaka code)
    city_name = None
    if filter_settings and filter_settings.get('city_filter'):
        city_name = filter_settings['city_filter'].strip()
    
    # Prepare detaylar (details) dict which generator expects
    detaylar = {}
    if content:
        detaylar = content.copy()
        # Generator expects 'registered_matters' (can be list or string)
        if 'registered_matters' in content:
            detaylar['registered_matters'] = content['registered_matters']
        # Map specific fields generator looks for in 'detaylar'
        if 'company_address' in content:
            detaylar['new_address'] = content['company_address']
        if 'capital' in content:  # If capital field exists
            if isinstance(content['capital'], dict):
                detaylar['new_capital'] = content['capital'].get('total_capital_TL')
        
        # [NEW] Map changes_summary to 'summary'
        if 'changes_summary' in content:
            detaylar['summary'] = content['changes_summary']
    
    # Check if this is a compound announcement with sub-announcements array
    # (Structure 1: content.announcements[])
    if ann_type == "bileşik_değişiklik" and content and isinstance(content.get('announcements'), list):
        # Each sub-announcement becomes a separate entry
        for sub_ann in content['announcements']:
            # Skip empty sub-announcements (all nulls)
            if not sub_ann or all(v is None for v in sub_ann.values()):
                continue
            
            sub_detaylar = sub_ann.copy()
            # Inherit common fields from main content if not present
            if 'registered_matters' not in sub_detaylar and 'registered_matters' in detaylar:
                 sub_detaylar['registered_matters'] = detaylar['registered_matters']

            entry = {
                "ilan_no": metadata.get('announcement_number'),
                "ilan_turu": ILAN_TURU_MAP.get(ann_type, 11), # Default to 11 (Unknown/Bileşik)
                "ticaret_sicil_no": metadata.get('registry_number') if metadata.get('registry_number') != 'Unknown' else None,
                "mersis_no": metadata.get('mersis_no') if metadata.get('mersis_no') != 'Unknown' else None,
                "unvan": sub_ann.get('company_name') or metadata.get('company_name'),
                "eski_unvan": metadata.get('old_company_name'),
                "sirket_sorgusu": filter_settings.get('company_filter') if filter_settings else None,
                "sicil_mudurluk": metadata.get('registry_office') if metadata.get('registry_office') != 'Unknown' else None,
                "il": city_name,
                "adres": metadata.get('address'),
                "gazete_tarihi": gazette_date,
                "gazete_sayisi": str(gazette_number) if gazette_number else None,
                "metin": raw_text,
                "detaylar": sub_detaylar
            }
            entries.append(entry)
    
    else:
        # Normal announcement
        entry = {
            "ilan_no": metadata.get('announcement_number'),
            "ilan_turu": ILAN_TURU_MAP.get(ann_type, 11), # Default to 11 (Unknown)
            "ticaret_sicil_no": metadata.get('registry_number') if metadata.get('registry_number') != 'Unknown' else None,
            "mersis_no": metadata.get('mersis_no') if metadata.get('mersis_no') != 'Unknown' else None,
            "unvan": metadata.get('company_name') if metadata.get('company_name') != 'Unknown' else None,
            "eski_unvan": metadata.get('old_company_name'),
            "sirket_sorgusu": filter_settings.get('company_filter') if filter_settings else None,
            "sicil_mudurluk": metadata.get('registry_office') if metadata.get('registry_office') != 'Unknown' else None,
            "il": city_name,
            "adres": metadata.get('address'),
            "gazete_tarihi": gazette_date,
            "gazete_sayisi": str(gazette_number) if gazette_number else None,
            "metin": raw_text, 
            "detaylar": detaylar
        }
        entries.append(entry)
    
    return entries


def process_json_file(json_path: Path) -> List[dict]:
    """
    Process a single JSON file and return ilanlar entries.
    
    Handles empty announcements by creating a placeholder entry with just
    gazette metadata.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    gazette_metadata = data.get('gazette_metadata', {})
    announcements = data.get('announcements', [])
    filter_settings = data.get('filter_settings')
    
    entries = []
    
    # Handle empty announcements case
    if not announcements:
        gazette_date = parse_turkish_date(gazette_metadata.get('date'))
        gazette_number = gazette_metadata.get('number')
        
        # Get city from filter_settings (as string)
        city_name = None
        if filter_settings and filter_settings.get('city_filter'):
            city_name = filter_settings['city_filter'].strip()
        
        # Create placeholder entry with null values (only date/number preserved)
        entry = {
            "ilan_no": None,
            "ilan_turu": None,
            "ticaret_sicil_no": None,
            "mersis_no": None,
            "unvan": None,
            "eski_unvan": None,
            "sirket_sorgusu": filter_settings.get('company_filter') if filter_settings else None,
            "sicil_mudurluk": None,
            "il": city_name,
            "adres": None,
            "gazete_tarihi": gazette_date,
            "gazete_sayisi": str(gazette_number) if gazette_number else None,
            "metin": None,
            "detaylar": None
        }
        entries.append(entry)
        print(f"  ⚠ {json_path.name}: Empty announcements - created placeholder with gazette metadata")
        return entries
    
    # Process each announcement
    for announcement in announcements:
        ann_entries = process_announcement(
            announcement, 
            gazette_metadata, 
            filter_settings
        )
        entries.extend(ann_entries)
    
    return entries


def convert_json_to_ilanlar(
    input_dir: Path,
    output_path: Path,
    pattern: str = "*.json"
) -> bool:
    """
    Convert all JSON files in input_dir and APPEND to ilanlar.json.
    
    Args:
        input_dir: Directory containing JSON files from OCR extraction
        output_path: Path for output ilanlar.json
        pattern: Glob pattern for JSON files (default: *.json)
    
    Returns:
        True if successful, False otherwise
    """
    print("=" * 60)
    print("🔄 JSON to ilanlar.json Converter (APPEND MODE)")
    print("=" * 60)
    print(f"📂 Input directory: {input_dir}")
    print(f"📄 Output file: {output_path}")
    print()
    
    # Load existing entries from ilanlar.json if it exists
    existing_entries = []
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content and content != '[]':
                    existing_entries = json.loads(content)
                    print(f"📥 Loaded {len(existing_entries)} existing entries from {output_path.name}")
        except (json.JSONDecodeError, Exception) as e:
            print(f"⚠ Could not load existing entries: {e}")
            print(f"  → Starting fresh")
            existing_entries = []
    else:
        print(f"📝 {output_path.name} does not exist, will create new file")
    
    print()
    
    # Find all JSON files
    json_files = sorted(input_dir.glob(pattern))
    
    if not json_files:
        print(f"❌ No JSON files found matching pattern '{pattern}' in {input_dir}")
        return False
    
    print(f"📋 Found {len(json_files)} JSON file(s)")
    print()
    
    new_entries = []
    
    for json_path in json_files:
        print(f"  Processing: {json_path.name}")
        try:
            entries = process_json_file(json_path)
            print(f"    → Generated {len(entries)} entry/entries")
            new_entries.extend(entries)
        except Exception as e:
            print(f"    ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Combine existing + new entries
    all_entries = existing_entries + new_entries
    
    # Write output
    print()
    print(f"💾 Appending {len(new_entries)} new entries to {output_path.name}...")
    print(f"   Total entries after append: {len(all_entries)}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_entries, f, indent=4, ensure_ascii=False)
    
    print()
    print("=" * 60)
    print(f"✅ Conversion complete!")
    print(f"   Existing entries: {len(existing_entries)}")
    print(f"   New entries:      {len(new_entries)}")
    print(f"   Total entries:    {len(all_entries)}")
    print(f"   Output: {output_path}")
    print("=" * 60)
    
    return True


def main():
    """Main entry point with CLI support."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convert OCR JSON outputs to ilanlar.json format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Default: OCR_outputs/json → db/db_Input/ilanlar.json
  python json_to_ilanlar.py
  
  # Custom paths
  python json_to_ilanlar.py --input ./my_jsons --output ./output/ilanlar.json
        '''
    )
    
    parser.add_argument(
        '--input', '-i',
        type=str,
        default=None,
        help='Input directory with JSON files (default: OCR_outputs/json)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Output ilanlar.json path (default: ../db/db_Input/ilanlar.json)'
    )
    
    args = parser.parse_args()
    
    # Default paths relative to script location
    script_dir = Path(__file__).parent
    
    input_dir = Path(args.input) if args.input else script_dir / "OCR_outputs" / "json"
    output_path = Path(args.output) if args.output else script_dir.parent / "db" / "db_Input" / "ilanlar.json"
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    success = convert_json_to_ilanlar(input_dir, output_path)
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
