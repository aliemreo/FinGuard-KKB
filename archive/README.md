# Archive

Earlier versions and backup copies, kept for reference. Nothing in the project imports or runs these files, and they still use the old folder names (`TTSG_Agent/`, `final/`, `report-ofe/`).

| File | What it was | Replaced by |
|---|---|---|
| `trade_registry/batch_process_gazettes_yedek.py` | Backup of the gazette OCR + LLM extractor | `trade_registry/batch_process_gazettes.py` |
| `trade_registry/json_to_ilanlar copy.py` | Backup of the JSON → `ilanlar` converter | `trade_registry/json_to_ilanlar.py` |
| `trade_registry/ticaret_sicil_scraper copy.py` | Backup of the Trade Registry scraper | `trade_registry/ticaret_sicil_scraper.py` |
| `report/generator copy.py` | Earlier report generator | `report/generator.py` |
| `procurement_bans/yasaklama_scraper.py` | Standalone ban-notice scraper and PDF stitcher | Stages `scrape` and `stitch` of `procurement_bans/pipeline.py` |
| `procurement_bans/enesson.py` | Standalone PaddleOCR-VL OCR step | Stage `ocr` of `procurement_bans/pipeline.py` |
| `procurement_bans/html2json.py` | Standalone HTML → JSON → database step | Stage `extract` of `procurement_bans/pipeline.py` |
| `procurement_bans/seperate_search_in_db.py` | Standalone active-ban search | `arama_motoru.py` |
