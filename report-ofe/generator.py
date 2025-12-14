import json
import os
import argparse
from datetime import datetime
from jinja2 import Template

# ARGUMENT PARSING

parser = argparse.ArgumentParser(description="Generate FinGuard Intelligence Report")
parser.add_argument(
    "--start-date", type=str, default="", help="Start date (dd.mm.yyyy)"
)
parser.add_argument("--end-date", type=str, default="", help="End date (dd.mm.yyyy)")
parser.add_argument("--company-name", type=str, default="", help="Company name")
args = parser.parse_args()

# CONFIGURATION & DATA LOADING
data_buckets = {"ihale": [], "sicil": [], "news": []}

FILES = {
    "ihale": "ihale.json",
    "sicil": "../db/db_Input/ilanlar.json",  # Uses TTSG_Agent output
    "news": "../news_scanning_and_sentimental_analysis/merged_results.json",
}


def load_json(filepath):
    """Loads JSON data from a file."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Error reading {filepath}: {e}")
            return []
    print(f"⚠️ Warning: {filepath} not found.")
    return []


# Load Data
for key, filepath in FILES.items():
    data = load_json(filepath)
    if isinstance(data, list):
        data_buckets[key].extend(data)
    elif data:
        data_buckets[key].append(data)


def format_date(date_str):
    """Converts various date formats to dd.mm.yyyy"""
    if not date_str:
        return "-"
    try:
        date_str = str(date_str).strip()

        # Extract just the date part (first 10 chars should be YYYY-MM-DD)
        # This handles formats like "2025-12-02 04:00:36 +0000" or "2025-02-12T10:47:00+00:00"
        if len(date_str) >= 10:
            date_part = date_str[:10]  # Get YYYY-MM-DD
            dt = datetime.strptime(date_part, "%Y-%m-%d")
            return dt.strftime("%d.%m.%Y")
        else:
            # Try to parse as-is
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%d.%m.%Y")
    except Exception:
        return date_str


def get_ilan_type(ilan_turu):
    """Maps ilan_turu code to Turkish description"""
    mapping = {
        1: "Emtia Satışı",
        2: "Sermaye Azaltımı",
        3: "Mal Varlığı Devri",
        4: "Tasfiye",
        5: "Pay Değişimi",
        6: "Toplantı Çağrısı",
        7: "Sermaye Taahhüdü",
        8: "Birleşme",
        9: "Şube Kuruluşu",
        10: "Adres Değişikliği",
        11: "Bilinmiyor",
    }
    return mapping.get(ilan_turu, "Bilinmiyor")


def stringify_value(val):
    """Converts nested dicts/lists to readable string format"""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, dict):
        # Extract meaningful fields from common dict types
        if "name" in val:
            return val["name"]
        if "total_capital_TL" in val:
            parts = []
            if val.get("total_shares"):
                parts.append(f"{val['total_shares']} pay")
            if val.get("total_capital_TL"):
                parts.append(f"{val['total_capital_TL']:,.0f} TL")
            return ", ".join(parts) if parts else str(val)
        # Generic dict: show key=value pairs for simple values only
        simple_parts = []
        for k, v in val.items():
            if isinstance(v, (str, int, float)) and v:
                simple_parts.append(f"{k}: {v}")
        return ", ".join(simple_parts) if simple_parts else ""
    if isinstance(val, list):
        items = [stringify_value(item) for item in val if stringify_value(item)]
        return ", ".join(items)
    return str(val)


# PROCESSORS

processed_report = {"sicil_items": [], "news_items": [], "ihale_items": []}

# Track date ranges for report header
all_dates = []

# --- PROCESS NEWS ---
for item in data_buckets["news"]:
    summary_text = item.get("summary")
    if not summary_text:
        raw_text = item.get("article_text", "")
        summary_text = raw_text[:300] + "..." if len(raw_text) > 300 else raw_text

    pub_date = item.get("published_at", "")
    if pub_date:
        all_dates.append(pub_date)

    processed_report["news_items"].append(
        {
            "title": item.get("title"),
            "source": (
                item.get("url", "").split("/")[2] if item.get("url") else "Bilinmiyor"
            ),
            "date": format_date(pub_date),
            "sentiment": item.get("label", "neutral"),
            "confidence": f"{item.get('confidence', 0) * 100:.1f}%",
            "summary": summary_text,
            "url": item.get("url", "#"),
            "needs_attention": item.get("needs_attention", False),
        }
    )

# --- PROCESS SICIL ---
for item in data_buckets["sicil"]:
    office = item.get("sicil_mudurluk") or item.get("metadata", {}).get(
        "registry_office", "Ticaret Sicil Müdürlüğü"
    )
    date_val = item.get("gazete_tarihi") or item.get("metadata", {}).get(
        "gazette_date", ""
    )
    if date_val:
        all_dates.append(date_val)

    company = item.get("unvan") or item.get("company_name", "-")
    address = item.get("adres") or item.get("new_address", "-")
    ilan_no = item.get("ilan_no", "-")
    ticaret_sicil_no = item.get("ticaret_sicil_no", "-")
    mersis_no = item.get("mersis_no", "-")
    ilan_type = get_ilan_type(item.get("ilan_turu"))

    # Extract registered matters from detaylar if present
    registered_matters = []
    det = item.get("detaylar") or {}
    if det and det.get("registered_matters"):
        rm = det["registered_matters"]
        # Ensure it's always a list (not a string that gets iterated char-by-char)
        if isinstance(rm, str):
            registered_matters = [rm]
        elif isinstance(rm, list):
            registered_matters = rm
        else:
            registered_matters = [str(rm)]
    elif item.get("registered_matters"):
        rm = item["registered_matters"]
        if isinstance(rm, str):
            registered_matters = [rm]
        elif isinstance(rm, list):
            registered_matters = rm
        else:
            registered_matters = [str(rm)]

    # Build details from detaylar field
    details_parts = []
    if det:
        if det.get("new_address"):
            details_parts.append(f"Yeni Adres: {det['new_address']}")
        if det.get("old_address"):
            details_parts.append(f"Eski Adres: {det['old_address']}")
        if det.get("new_capital"):
            details_parts.append(f"Yeni Sermaye: {det['new_capital']}")
        if det.get("old_capital"):
            details_parts.append(f"Eski Sermaye: {det['old_capital']}")
        if det.get("capital_breakdown"):
            details_parts.append(
                f"Sermaye: {stringify_value(det['capital_breakdown'])}"
            )
        if det.get("shareholders"):
            details_parts.append(
                f"Pay Sahipleri: {stringify_value(det['shareholders'])}"
            )

        # Handle notary_info - can be string, dict, or list
        notary_info = det.get("notary_info")
        if notary_info:
            if isinstance(notary_info, str):
                # Direct string format: "Ankara | Nt Nin 18.7.2025 Tarih 5188 Sayı İle Tasdikli"
                details_parts.append(f"Noter: {notary_info}")
            elif isinstance(notary_info, dict):
                # Single dict format: {"date": "...", "number": "...", "notary_office": "..."}
                parts = []
                if notary_info.get("notary_office"):
                    parts.append(notary_info["notary_office"])
                if notary_info.get("notary"):
                    parts.append(notary_info["notary"])
                if notary_info.get("date"):
                    parts.append(notary_info["date"])
                if notary_info.get("number"):
                    parts.append(f"No: {notary_info['number']}")
                if notary_info.get("document_number"):
                    parts.append(f"No: {notary_info['document_number']}")
                if notary_info.get("description"):
                    parts.append(notary_info["description"])
                if parts:
                    details_parts.append("Noter: " + " - ".join(parts))
            elif isinstance(notary_info, list):
                # List of dicts format
                notary_texts = []
                for n in notary_info:
                    if isinstance(n, dict):
                        parts = []
                        if n.get("notary_office"):
                            parts.append(n["notary_office"])
                        if n.get("notary"):
                            parts.append(n["notary"])
                        if n.get("date"):
                            parts.append(n["date"])
                        if n.get("document_number"):
                            parts.append(f"No: {n['document_number']}")
                        if n.get("number"):
                            parts.append(f"No: {n['number']}")
                        if n.get("description"):
                            parts.append(n["description"])
                        if parts:
                            notary_texts.append(" - ".join(parts))
                if notary_texts:
                    details_parts.append("Noter: " + " | ".join(notary_texts))

    processed_report["sicil_items"].append(
        {
            "office": office,
            "date": format_date(date_val),
            "company_name": company,
            "address": address,
            "ilan_no": ilan_no,
            "ilan_no": ilan_no,
            "ticaret_sicil_no": ticaret_sicil_no,
            "mersis_no": mersis_no,
            "ilan_type": ilan_type,
            "registered_matters": registered_matters,
            "details": " • ".join(details_parts) if details_parts else "",
            "summary": det.get("summary"),  # Extract summary
            "raw_json_content": (
                json.dumps(det, indent=2, ensure_ascii=False) if det else "{}"
            ),
        }
    )

# --- PROCESS IHALE ---
for item in data_buckets["ihale"]:
    # Process partners if they exist
    partners_list = []
    for partner in item.get("ortaklar", []):
        partner_info = partner.get("ortak_adi_unvani", "")
        tc_no = partner.get("ortak_tc_kimlik_no", "")
        vergi_no = partner.get("ortak_vergi_kimlik_no", "")
        if tc_no:
            partner_info += f" (TC: {tc_no})"
        elif vergi_no:
            partner_info += f" (VKN: {vergi_no})"
        if partner_info:
            partners_list.append(partner_info)

    processed_report["ihale_items"].append(
        {
            "registration_number": item.get("ihale_kayit_numarasi", "-"),
            "ministry": item.get("yasaklama_karari_veren_bakanlik_kurum", "-"),
            "administration": item.get("ihaleyi_yapan_idarenin_adi", "-"),
            "banned_entity": item.get("yasakli_adi", "-"),
            "banned_tc": item.get("yasakli_tc_kimlik_no", "-"),
            "banned_tax_id": item.get("yasakli_vergi_kimlik_no", "-"),
            "partners": partners_list,
            "law_basis": item.get("yasaklama_kanun_dayanagi", "-"),
            "ban_scope": item.get("yasaklama_kanun_kapsami", "-"),
            "ban_duration": item.get("yasaklama_suresi", "-"),
        }
    )

# Calculate date range for header
if all_dates:
    try:
        parsed_dates = []
        for d in all_dates:
            d_str = str(d).strip()[:10]  # Get YYYY-MM-DD part
            try:
                parsed_dates.append(datetime.strptime(d_str, "%Y-%m-%d"))
            except:
                pass
        if parsed_dates:
            min_date = min(parsed_dates).strftime("%d.%m.%Y")
            max_date = max(parsed_dates).strftime("%d.%m.%Y")
        else:
            min_date = max_date = "-"
    except:
        min_date = max_date = "-"
else:
    min_date = max_date = "-"


# HTML TEMPLATE

html_template = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <style>
        @page { 
            size: A4; 
            margin: 2.5cm; 
        }
        @media print {
            .page-break { page-break-after: always; }
        }
        
        * {
            box-sizing: border-box;
        }
        
        body { 
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
            color: #1e293b; 
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 0;
            background: #ffffff;
        }

        .main-header { 
            border-bottom: 3px solid #0f172a;
            padding: 2.5rem 2rem 2rem 2rem;
            margin: -2rem -2rem 3rem -2rem;
            background: #ffffff;
        }
        .main-header h1 { 
            font-size: 0.85rem; 
            font-weight: 600; 
            margin: 0;
            color: #94a3b8;
            letter-spacing: 2px;
            text-transform: uppercase;
        }
        .main-header .company-name {
            font-size: 2.5rem;
            font-weight: 800;
            color: #0f172a;
            margin: 0.75rem 0 1.25rem 0;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .main-header .report-info {
            display: flex;
            align-items: center;
            gap: 1.5rem;
            flex-wrap: wrap;
        }
        .main-header .report-period {
            display: inline-block;
            width: fit-content;
            background: #1e40af !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            color: #ffffff !important;
            padding: 0.6rem 1.5rem;
            border-radius: 50px;
            font-size: 0.9rem;
            font-weight: 600;
        }
        .main-header .report-date {
            color: #334155 !important;
            font-size: 0.85rem;
            font-weight: 500;
            display: block;
            margin-top: 0.75rem;
        }
        
        .section-title { 
            font-size: 1.3rem; 
            font-weight: 700; 
            margin: 3rem 0 1.5rem 0; 
            padding: 0.75rem 1rem;
            background: #1e3a5f !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            color: #ffffff !important;
            border-radius: 8px;
            display: flex;
            align-items: center;
        }
        .section-title span {
            letter-spacing: 0.3px;
            color: #ffffff !important;
        }

        .card {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.08);
            margin-bottom: 1.2rem;
            background: #ffffff;
            break-inside: avoid;
            overflow: hidden;
        }
        .card-content { 
            padding: 1.25rem; 
        }

        .badge {
            display: inline-block; 
            padding: 4px 12px; 
            border-radius: 9999px;
            font-size: 0.75rem; 
            font-weight: 700; 
            text-transform: uppercase;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            flex-shrink: 0;
            white-space: nowrap;
        }
        .badge-positive { background: #dcfce7 !important; color: #166534 !important; border: 1px solid #86efac; }
        .badge-negative { background: #fee2e2 !important; color: #991b1b !important; border: 1px solid #fca5a5; }
        .badge-neutral { background: #f3f4f6 !important; color: #374151 !important; border: 1px solid #d1d5db; }
        
        .matter-badge {
            display: inline-block;
            background: #1e3a8a;
            color: #ffffff;
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 700;
            margin-right: 6px;
            margin-bottom: 6px;
            border: none;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        
        .ilan-type-badge {
            display: inline-block;
            background: #6366f1;
            color: #ffffff;
            padding: 3px 10px;
            border-radius: 5px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: capitalize;
            letter-spacing: 0.2px;
        }
        
        .meta-tag { 
            background: #e0e7ff;
            color: #3730a3; 
            padding: 4px 10px; 
            border-radius: 6px; 
            font-size: 0.7rem; 
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .date { 
            font-size: 0.8rem; 
            color: #64748b;
            font-weight: 500;
        }
        
        a.button {
            display: inline-block; 
            margin-top: 12px; 
            font-size: 0.85rem; 
            color: #2563eb;
            text-decoration: none; 
            font-weight: 600;
            transition: color 0.2s ease;
        }
        a.button:hover { 
            color: #1d4ed8;
            text-decoration: underline;
        }

        table { 
            width: 100%; 
            border-collapse: collapse; 
            font-size: 0.85rem; 
            margin-top: 0.5rem; 
        }
        th { 
            text-align: left; 
            padding: 0.85rem; 
            background: linear-gradient(to bottom, #f8fafc, #f1f5f9);
            color: #475569; 
            font-weight: 600; 
            border-bottom: 2px solid #cbd5e1; 
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        td { 
            padding: 0.85rem; 
            border-bottom: 1px solid #f1f5f9; 
            vertical-align: top; 
        }
        tbody tr {
            transition: background-color 0.2s ease;
        }
        tbody tr:nth-child(even) {
            background-color: #fafbfc;
        }
        tbody tr:hover {
            background-color: #f8fafc;
        }
    </style>
</head>
<body>

    <div class="main-header">
        <h1>FinGuard İstihbarat Raporu</h1>
        <div class="company-name">{{ company_name }}</div>
        <div class="report-info">
            <div class="report-period">
                <span>{{ start_date }} — {{ end_date }}</span>
            </div>
            <div class="report-date">Oluşturulma: {{ current_date }}</div>
        </div>
    </div>

    <!-- IHALE (TENDER BANS) SECTION - FIRST -->
    <div class="section-title">
        <span>KAMU IHALE YASAKLILARI</span>
    </div>

    {% if ihale_items %}
        <div class="card">
            <div class="card-content">
                <table>
                    <thead>
                        <tr>
                            <th style="width:12%">İhale Kayıt No</th>
                            <th style="width:22%">İhale Yasaklısı Kurum</th>
                            <th style="width:20%">Yasaklama Kararı Veren Bakanlık / İhaleyi Yapan İdare</th>
                            <th style="width:18%">Ortaklar</th>
                            <th style="width:14%">Kanun Kapsamı</th>
                            <th style="width:14%">Yasak Kapsam Süresi</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for item in ihale_items %}
                        <tr>
                            <td style="font-size:0.75rem; color:#64748b; font-family: 'Courier New', monospace;">{{ item.registration_number }}</td>
                            <td>
                                <div style="font-weight:600; color:#0f172a; font-size:0.85rem;">{{ item.banned_entity }}</div>
                                <div style="font-size:0.7rem; color:#64748b; margin-top:3px;">
                                    {% if item.banned_tc and item.banned_tc != "-" %}
                                        <span style="background:#f1f5f9; padding:2px 6px; border-radius:3px; margin-right:4px;">TC: {{ item.banned_tc }}</span>
                                    {% endif %}
                                    {% if item.banned_tax_id and item.banned_tax_id != "-" %}
                                        <span style="background:#f1f5f9; padding:2px 6px; border-radius:3px;">VKN: {{ item.banned_tax_id }}</span>
                                    {% endif %}
                                </div>
                            </td>
                            <td style="font-size:0.8rem;">
                                <div style="font-weight:600; color:#334155; font-size:0.82rem;">{{ item.ministry }}</div>
                                <div style="font-size:0.75rem; color:#64748b; margin-top:3px;">{{ item.administration }}</div>
                            </td>
                            <td style="font-size:0.75rem; color:#475569;">
                                {% if item.partners %}
                                    {% for partner in item.partners %}
                                        <div style="margin-bottom:4px; padding-left:6px; border-left:2px solid #e2e8f0;">{{ partner }}</div>
                                    {% endfor %}
                                {% else %}
                                    <span style="color:#cbd5e1;">—</span>
                                {% endif %}
                            </td>
                            <td>
                                <div style="font-size:0.75rem; font-weight:600; color:#1e40af; background:#dbeafe; padding:3px 8px; border-radius:4px; display:inline-block;">{{ item.law_basis }}</div>
                                {% if item.ban_scope and item.ban_scope != "-" %}
                                    <div style="font-size:0.7rem; color:#64748b; margin-top:4px;">{{ item.ban_scope }}</div>
                                {% endif %}
                            </td>
                            <td>
                                <div style="font-weight:600; font-size:0.82rem; color:#0f172a;">{{ item.ban_duration }}</div>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    {% else %}
        <p style="color:#64748b; font-style:italic;">İhale yasaklı verisi bulunamadı.</p>
    {% endif %}

    <!-- SICIL (TRADE REGISTRY) SECTION - SECOND -->
    <div class="section-title" style="page-break-before: always;">
        <span>TICARET SICIL ILANLARI</span>
    </div>

    {% if sicil_items %}
        {% for item in sicil_items %}
        <div class="card">
            <div class="card-content">
                <div style="display:flex; justify-content:space-between; align-items:start; margin-bottom: 6px;">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                            <span class="ilan-type-badge">{{ item.ilan_type }}</span>
                            <span class="meta-tag">{{ item.office }}</span>
                            <span class="date">{{ item.date }}</span>
                        </div>
                        <h3 style="margin: 6px 0 8px 0; font-size:1.05rem; color:#0f172a;">{{ item.company_name }}</h3>
                        {% if item.ticaret_sicil_no and item.ticaret_sicil_no != "-" %}
                        <div style="font-size: 0.75rem; color: #64748b; margin-bottom: 2px;">
                            <strong>Ticaret Sicil No:</strong> {{ item.ticaret_sicil_no }}
                        </div>
                        {% endif %}
                        {% if item.mersis_no and item.mersis_no != "-" %}
                        <div style="font-size: 0.75rem; color: #64748b; margin-bottom: 6px;">
                            <strong>Mersis No:</strong> {{ item.mersis_no }}
                        </div>
                        {% endif %}
                        {% if item.registered_matters %}
                        <div style="margin-top: 6px;">
                            {% for matter in item.registered_matters %}
                                <span class="matter-badge">{{ matter }}</span>
                            {% endfor %}
                        </div>
                        {% endif %}
                    </div>
                    <div style="text-align: right; font-size: 0.7rem; color: #94a3b8; margin-left: 10px;">
                        {{ item.ilan_no }}
                    </div>
                </div>
                
                {% if item.summary %}
                <div style="background-color: #f8fafc; border-left: 3px solid #6366f1; padding: 8px 12px; margin: 8px 0; border-radius: 0 4px 4px 0;">
                    <p style="color:#334155; font-size:0.9rem; margin:0; font-style: italic;">
                        {{ item.summary }}
                    </p>
                </div>
                {% endif %}

                {% if item.raw_json_content and item.raw_json_content != "{}" %}
                <details style="margin-top: 10px; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px;">
                    <summary style="cursor: pointer; padding: 6px; font-size: 0.8rem; font-weight: 600; color: #475569; background-color: #f8fafc; outline: none;">
                        🔍 Raw JSON Content
                    </summary>
                    <div style="background-color: #1e293b; color: #cbd5e1; padding: 10px; border-radius: 4px; overflow-x: auto; margin-top: 4px;">
                        <pre style="margin: 0; font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 0.75rem; white-space: pre-wrap;">{{ item.raw_json_content }}</pre>
                    </div>
                </details>
                {% endif %}

                <p style="color:#334155; font-size:0.85rem; line-height:1.5; margin-top:8px; margin-bottom: 4px;">
                    <strong>Adres:</strong> {{ item.address }}
                </p>
                
                {% if item.details != "-" %}
                <p style="color:#64748b; font-size:0.8rem; line-height:1.4; font-style:italic; margin-top:4px;">
                    {{ item.details }}
                </p>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    {% else %}
        <p style="color:#64748b; font-style:italic;">Ticaret sicil verisi bulunamadı.</p>
    {% endif %}

    <!-- NEWS SECTION - THIRD -->
    <div class="section-title" style="page-break-before: always;">
        <span>PIYASA HABERLERI & DUYARLILIK ANALIZI</span>
    </div>

    {% if news_items %}
        {% for item in news_items %}
        <div class="card">
            <div class="card-content">
                <table style="width:100%; border-collapse:collapse; border:none;">
                    <tr>
                        <td style="vertical-align:top; border:none; padding:0;">
                            <span class="meta-tag">{{ item.source }}</span>
                            <span class="date" style="margin-left:8px;">{{ item.date }}</span>
                            <h3 style="margin: 8px 0; font-size:1.1rem;">{{ item.title }}</h3>
                        </td>
                        <td style="vertical-align:top; text-align:right; width:150px; border:none; padding:0;">
                            {% if item.needs_attention %}<span style="color:#dc2626; font-weight:bold; margin-right:4px;" title="Low confidence - needs review">!</span>{% endif %}
                            <span class="badge badge-{{ item.sentiment }}">
                                {{ item.sentiment }} ({{ item.confidence }})
                            </span>
                        </td>
                    </tr>
                </table>
                <p style="color:#334155; font-size:0.95rem; line-height:1.6; margin-top:10px;">
                    {{ item.summary }}
                </p>
                <a href="{{ item.url }}" class="button" target="_blank">Orijinal Makaleyi Oku</a>
            </div>
        </div>
        {% endfor %}
    {% else %}
        <p style="color:#64748b; font-style:italic;">Haber verisi bulunamadı.</p>
    {% endif %}

</body>
</html>
"""

# ==========================================
# 5. RENDER & SAVE
# ==========================================
template = Template(html_template)

# Use CLI args if provided, otherwise fall back to calculated dates
report_company = (
    args.company_name if args.company_name else "Şirket Bilgisi Belirtilmedi"
)
report_start = args.start_date if args.start_date else min_date
report_end = args.end_date if args.end_date else max_date

html_output = template.render(
    news_items=processed_report["news_items"],
    sicil_items=processed_report["sicil_items"],
    ihale_items=processed_report["ihale_items"],
    current_date=datetime.now().strftime("%d.%m.%Y"),
    start_date=report_start,
    end_date=report_end,
    company_name=report_company,
)

output_filename = "Final_Report.html"
pdf_filename = "Final_Report.pdf"

try:
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"✅ {output_filename} başarıyla oluşturuldu!")
    print(
        f"   📊 İstatistikler: {len(processed_report['ihale_items'])} İhale, {len(processed_report['sicil_items'])} Sicil, {len(processed_report['news_items'])} Haber"
    )

    # Generate PDF using pdfkit (requires wkhtmltopdf installed)
    # In Docker: apt-get install -y wkhtmltopdf
    try:
        import pdfkit
        import shutil

        # Find wkhtmltopdf - works on Linux (Docker) and Windows
        wkhtmltopdf_path = shutil.which("wkhtmltopdf")
        if not wkhtmltopdf_path:
            # Try common Windows paths
            for path in [
                r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
                r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
            ]:
                if os.path.exists(path):
                    wkhtmltopdf_path = path
                    break

        if wkhtmltopdf_path:
            config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
            pdfkit.from_file(output_filename, pdf_filename, configuration=config)
        else:
            pdfkit.from_file(output_filename, pdf_filename)
        print(f"✅ {pdf_filename} başarıyla oluşturuldu!")
    except ImportError:
        print("⚠️ pdfkit yüklü değil. PDF için: pip install pdfkit")
    except Exception as pdf_error:
        print(f"⚠️ PDF oluşturma hatası: {pdf_error}")

except Exception as e:
    print(f"❌ Dosya yazma hatası: {e}")
