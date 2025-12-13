import json
import os
from datetime import datetime
from jinja2 import Template

# ==========================================
# 1. CONFIGURATION & DATA LOADING
# ==========================================
data_buckets = {"ihale": [], "sicil": [], "news": []}

FILES = {
    "ihale": "ihale.json",
    "sicil": "sicil.json",
    "news": "news.json",
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

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def format_date(date_str):
    """Converts various date formats to dd.mm.yyyy"""
    if not date_str:
        return "-"
    try:
        # Handle various formats
        date_str = str(date_str).strip()
        
        # Try ISO format with timezone: "2025-12-02 04:00:36 +0000" or "2025-02-12T10:47:00+00:00"
        if "T" in date_str or " " in date_str:
            # Remove timezone info for simpler parsing
            date_str = date_str.split("+")[0].split("-")[0:3]  # This approach is flawed, let me fix
            date_str_clean = date_str.replace("+", " ").replace("T", " ").split()[0]
            dt = datetime.strptime(date_str_clean, "%Y-%m-%d")
        else:
            # Handle simple YYYY-MM-DD
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d.%m.%Y")
    except Exception as e:
        # If all parsing fails, try to extract just the date part
        try:
            if len(date_str) >= 10:
                date_part = date_str[:10]  # Get YYYY-MM-DD
                dt = datetime.strptime(date_part, "%Y-%m-%d")
                return dt.strftime("%d.%m.%Y")
        except:
            pass
        return date_str

# ==========================================
# 3. PROCESSORS
# ==========================================
processed_report = {"sicil_items": [], "news_items": [], "ihale_items": []}

# --- PROCESS NEWS ---
for item in data_buckets["news"]:
    summary_text = item.get("summary")
    if not summary_text:
        raw_text = item.get("article_text", "")
        summary_text = raw_text[:300] + "..." if len(raw_text) > 300 else raw_text

    processed_report["news_items"].append({
        "title": item.get("title"),
        "source": item.get("url", "").split("/")[2] if item.get("url") else "Bilinmiyor",
        "date": format_date(item.get("published_at", "")),
        "sentiment": item.get("label", "neutral"),
        "confidence": f"{item.get('confidence', 0) * 100:.1f}%",
        "summary": summary_text,
        "url": item.get("url", "#"),
    })

# --- PROCESS SICIL ---
for item in data_buckets["sicil"]:
    office = item.get("sicil_mudurluk") or item.get("metadata", {}).get("registry_office", "Ticaret Sicil Müdürlüğü")
    date_val = item.get("gazete_tarihi") or item.get("metadata", {}).get("gazette_date", "")
    company = item.get("unvan") or item.get("company_name", "-")
    address = item.get("adres") or item.get("new_address", "-")
    ilan_no = item.get("ilan_no", "-")
    
    # Extract registered matters / events
    registered_matters = []
    if item.get("registered_matters"):
        registered_matters = item["registered_matters"]
    
    # Build details from detaylar field
    details_parts = []
    det = item.get("detaylar", {})
    if det:
        for k, v in det.items():
            if v: 
                label = k.replace('_', ' ').title()
                # Translate common keys to Turkish
                translations = {
                    "Old Address": "Eski Adres",
                    "New Address": "Yeni Adres",
                    "Old Capital": "Eski Sermaye",
                    "New Capital": "Yeni Sermaye"
                }
                label = translations.get(label, label)
                details_parts.append(f"{label}: {v}")
    
    metin = item.get("metin")
    if metin:
        details_parts.append(metin[:150] + "..." if len(metin) > 150 else metin)

    processed_report["sicil_items"].append({
        "office": office,
        "date": format_date(date_val),
        "company_name": company,
        "address": address,
        "ilan_no": ilan_no,
        "registered_matters": registered_matters,
        "details": " • ".join(details_parts) if details_parts else "-"
    })

# --- PROCESS IHALE ---
for item in data_buckets["ihale"]:
    processed_report["ihale_items"].append({
        "registration_number": item.get("ihale_kayit_numarasi", "-"),
        "ministry": item.get("yasaklama_karari_veren_bakanlik/kurum", "-"),
        "administration": item.get("ihaleyi_yapan_idarenin_adi", "-"),
        "banned_entity": item.get("yasakli_adi", "-"),
        "ban_duration": item.get("yasaklama_suresi", "-"),
        "ban_scope": item.get("yasaklama_kanun_kapsami", "-"),
    })

# ==========================================
# 4. HTML TEMPLATE
# ==========================================
html_template = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <style>
        @page { size: A4; margin: 2cm; }
        @media print {
            .page-break { page-break-after: always; }
        }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #0f172a; 
            line-height: 1.5;
            max-width: 900px;
            margin: 0 auto;
            padding: 1rem;
        }

        .main-header { 
            border-bottom: 2px solid #0f172a; 
            padding-bottom: 1rem; 
            margin-bottom: 2rem; 
        }
        .main-header h1 { 
            font-size: 1.8rem; 
            font-weight: 700; 
            margin: 0; 
        }
        
        .section-title { 
            font-size: 1.4rem; 
            font-weight: 600; 
            margin: 2.5rem 0 1.5rem 0; 
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #cbd5e1;
            color: #334155;
            display: flex;
            align-items: center;
        }

        .card {
            border: 1px solid #e2e8f0;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
            margin-bottom: 1.5rem;
            background: white;
            break-inside: avoid;
        }
        .card-content { padding: 1.5rem; }

        .badge {
            display: inline-block; 
            padding: 2px 10px; 
            border-radius: 9999px;
            font-size: 0.75rem; 
            font-weight: 700; 
            text-transform: uppercase;
        }
        .badge-positive { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
        .badge-negative { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
        .badge-neutral { background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }
        
        .matter-badge {
            display: inline-block;
            background: #f8fafc;
            color: #475569;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 4px;
            margin-bottom: 4px;
            border: 1px solid #e2e8f0;
        }
        
        .meta-tag { 
            background: #f1f5f9; 
            color: #475569; 
            padding: 2px 6px; 
            border-radius: 4px; 
            font-size: 0.75rem; 
            font-weight: 600; 
        }
        .date { font-size: 0.85rem; color: #64748b; }
        
        a.button {
            display: inline-block; 
            margin-top: 10px; 
            font-size: 0.85rem; 
            color: #2563eb;
            text-decoration: none; 
            font-weight: 500;
        }
        a.button:hover { text-decoration: underline; }

        table { 
            width: 100%; 
            border-collapse: collapse; 
            font-size: 0.85rem; 
            margin-top: 0.5rem; 
        }
        th { 
            text-align: left; 
            padding: 0.75rem; 
            background-color: #f8fafc; 
            color: #64748b; 
            font-weight: 600; 
            border-bottom: 1px solid #e2e8f0; 
        }
        td { 
            padding: 0.75rem; 
            border-bottom: 1px solid #f1f5f9; 
            vertical-align: top; 
        }
    </style>
</head>
<body>

    <div class="main-header">
        <h1>FinGuard İstihbarat Raporu</h1>
        <p style="color:#64748b; margin-top:5px;">Gizli Analiz • {{ current_date }}</p>
    </div>

    <!-- IHALE (TENDER BANS) SECTION - FIRST -->
    <div class="section-title">
        <span>🚫 Kamu İhale Yasaklıları</span>
    </div>

    {% if ihale_items %}
        <div class="card">
            <div class="card-content">
                <table>
                    <thead>
                        <tr>
                            <th>Kayıt No</th>
                            <th>Yasaklı Firma</th>
                            <th>İdare</th>
                            <th>Süre & Kapsam</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for item in ihale_items %}
                        <tr>
                            <td>{{ item.registration_number }}</td>
                            <td>
                                <div style="font-weight:600; color:#b91c1c;">{{ item.banned_entity }}</div>
                                <div style="font-size:0.75rem; color:#64748b; margin-top:2px;">{{ item.ministry }}</div>
                            </td>
                            <td style="font-size:0.85rem;">{{ item.administration }}</td>
                            <td>
                                <div style="font-weight:600;">{{ item.ban_duration }}</div>
                                <div style="font-size:0.75rem; color:#64748b;">{{ item.ban_scope }}</div>
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
        <span>🏛️ Ticaret Sicil İlanları</span>
    </div>

    {% if sicil_items %}
        {% for item in sicil_items %}
        <div class="card">
            <div class="card-content">
                <div style="display:flex; justify-content:space-between; align-items:start; margin-bottom: 12px;">
                    <div>
                        <span class="meta-tag">{{ item.office }}</span>
                        <span class="date" style="margin-left:8px;">{{ item.date }}</span>
                        <h3 style="margin: 8px 0; font-size:1.1rem; color:#0f172a;">{{ item.company_name }}</h3>
                    </div>
                    <div style="text-align: right; font-size: 0.7rem; color: #94a3b8;">
                        {{ item.ilan_no }}
                    </div>
                </div>
                
                {% if item.registered_matters %}
                <div style="margin-bottom: 10px;">
                    {% for matter in item.registered_matters %}
                        <span class="matter-badge">{{ matter }}</span>
                    {% endfor %}
                </div>
                {% endif %}
                
                <p style="color:#334155; font-size:0.9rem; line-height:1.6; margin-top:8px; margin-bottom: 6px;">
                    <strong>Adres:</strong> {{ item.address }}
                </p>
                
                {% if item.details != "-" %}
                <p style="color:#64748b; font-size:0.85rem; line-height:1.5; font-style:italic;">
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
        <span>📰 Piyasa Haberleri & Duyarlılık Analizi</span>
    </div>

    {% if news_items %}
        {% for item in news_items %}
        <div class="card">
            <div class="card-content">
                <div style="display:flex; justify-content:space-between; align-items:start;">
                    <div>
                        <span class="meta-tag">{{ item.source }}</span>
                        <span class="date" style="margin-left:8px;">{{ item.date }}</span>
                        <h3 style="margin: 8px 0; font-size:1.1rem;">{{ item.title }}</h3>
                    </div>
                    <span class="badge badge-{{ item.sentiment }}">
                        {{ item.sentiment }} ({{ item.confidence }})
                    </span>
                </div>
                <p style="color:#334155; font-size:0.95rem; line-height:1.6; margin-top:10px;">
                    {{ item.summary }}
                </p>
                <a href="{{ item.url }}" class="button" target="_blank">Orijinal Makaleyi Oku →</a>
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
html_output = template.render(
    news_items=processed_report["news_items"],
    sicil_items=processed_report["sicil_items"],
    ihale_items=processed_report["ihale_items"],
    current_date=datetime.now().strftime("%d.%m.%Y"),
)

output_filename = "Final_Report.html"
try:
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"✅ {output_filename} başarıyla oluşturuldu!")
    print(f"   📊 İstatistikler: {len(processed_report['ihale_items'])} İhale, {len(processed_report['sicil_items'])} Sicil, {len(processed_report['news_items'])} Haber")
except Exception as e:
    print(f"❌ Dosya yazma hatası: {e}")
