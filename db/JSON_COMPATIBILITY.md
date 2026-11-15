# JSON ↔ Database Compatibility

This document explains the compatibility issues between the JSON output from `trade_registry/batch_process_gazettes.py` and what the `db/` loader expects.

## Schema: `ilanlar` Table

| Column | Type | Source in JSON |
|--------|------|----------------|
| `ilan_no` | VARCHAR(50) UNIQUE | `metadata.announcement_number` |
| `ilan_turu` | SMALLINT (1-11) | `announcement_type` → mapped |
| `mersis_no` | VARCHAR(16) | `metadata.mersis_no` |
| `unvan` | VARCHAR(500) | `metadata.company_name` |
| `il` | SMALLINT (1-81) | `content.city` → plaka code |
| `ilce` | VARCHAR(100) | `content.district` |
| `adres` | TEXT | `content.new_address` |
| `tescil_tarihi` | DATE | `content.registration_date` |
| `gazete_tarihi` | DATE | `gazette_metadata.date` |
| `gazete_sayisi` | VARCHAR(20) | `gazette_metadata.number` |
| `detaylar` | JSONB | remaining `content` fields |

---

## ⚠️ Compatibility Issues

### 1. `announcement_number` is NULL (CRITICAL)

**trade_registry outputs:**
```json
"announcement_number": null
```

**Problem:** `ilan_no` is UNIQUE and required. Records with null are **SKIPPED**.

**Fix needed in trade_registry:** Extract "İlan Sıra No:" from the OCR text.

---

### 2. Date Format Mismatch

**trade_registry outputs:**
```json
"date": "30 EKIM 2024"
```

**Database expects:** `DATE` type (`YYYY-MM-DD`)

**Current workaround:** `import_to_postgres.py` converts Turkish months to numbers.

**Better fix:** Have trade_registry output ISO format: `"2024-10-30"`

---

### 3. City (`il`) Field Missing

**trade_registry outputs:**
```json
"content": {
    // no "city" field
}
```

**Database expects:** `il` as SMALLINT plaka code (1-81)

**Current workaround:** Extracted from `registry_office` string (e.g., "T.C. **İSTANBUL** TİCARET...")

**Better fix:** Add `"city": "İSTANBUL"` to content in trade_registry.

---

### 4. `registry_number` is "Unknown"

**trade_registry outputs:**
```json
"registry_number": "Unknown"
```

**Problem:** Should be actual ticaret sicil no or null.

**Fix needed in trade_registry:** Extract from "Ticaret Sicil No:" in OCR text.

---

## İlan Türü Mapping

The `announcement_type` string maps to `ilan_turu` SMALLINT:

| Code | Category | trade_registry Types |
|------|----------|------------------|
| 1 | Kuruluş | `kuruluş`, `yeni_kayit` |
| 2 | Yönetim/Temsil | `yönetim`, `müdür_atama` |
| 3 | Sermaye/Pay | `sermaye_azaltımı`, `pay_senedi_değişimi` |
| 4 | Sözleşme/Merkez | `adres_değişikliği`, `bileşik_değişiklik` |
| 5 | Yapısal Değişiklik | `birleşme`, `bölünme` |
| 6 | Şube | `şube_kuruluşu` |
| 7 | Tasfiye | `tasfiye` |
| 8 | İflas/Konkordato | `iflas`, `konkordato` |
| 9 | Devir | `mal_varlığı_devri`, `işletme_devri` |
| 10 | Çağrı/Bildirim | `toplantı_çağrısı`, `genel_kurul` |
| 11 | Düzeltme | Unknown types default here |

---

## Current Status

| Issue | Severity | Handled By |
|-------|----------|------------|
| NULL `announcement_number` | 🔴 Critical | **Skipped** - needs trade_registry fix |
| Turkish date format | 🟡 Medium | `import_to_postgres.py` converts |
| Missing `city` field | 🟡 Medium | Extracted from `registry_office` |
| "Unknown" values | 🟢 Low | Converted to NULL |
