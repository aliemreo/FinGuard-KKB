import subprocess
import os
import sys
import json
import shutil
from pathlib import Path
import re
from datetime import datetime, timedelta
import argparse

os.environ["PYTHONIOENCODING"] = "utf-8"

parser = argparse.ArgumentParser()
parser.add_argument("--start-date", type=str, required=True)
parser.add_argument("--end-date", type=str, required=True)
parser.add_argument("--company-name", type=str, required=True)
parser.add_argument(
    "--uselocalmodel",
    action="store_true",
    help="Use local fine-tuned model instead of OpenAI API (default: API)",
)
args = parser.parse_args()

START_DATE = datetime.strptime(args.start_date, "%d.%m.%Y")
END_DATE = datetime.strptime(args.end_date, "%d.%m.%Y")
COMPANY_NAME = args.company_name
USE_LOCAL_MODEL = args.uselocalmodel


def clear_scraped_data():
    """Clear the scraped_data folder before starting"""
    scraped_dir = Path("scraped_data")
    if scraped_dir.exists():
        shutil.rmtree(scraped_dir)
        print("[OK] Cleared scraped_data folder")
    scraped_dir.mkdir(exist_ok=True)


def merge_results():
    """Merge data from all sources into a single JSON file"""
    CONFIDENCE_THRESHOLD = 0.60

    # Load extracted URLs
    try:
        with open("extracted_urls.json", "r", encoding="utf-8") as f:
            urls_data = json.load(f)

        # Check if empty or no URLs extracted
        if not urls_data or len(urls_data) == 0:
            print("[!]  No URLs were extracted from the search")
            return "No news articles found for these constraints"

        print(f"[OK] Loaded {len(urls_data)} URLs from extracted_urls.json")
    except FileNotFoundError:
        print("[ERROR] extracted_urls.json not found - no URLs were extracted")
        return "No news articles found for these constraints"
    except Exception as e:
        print(f"[ERROR] Failed to load extracted_urls.json: {e}")
        return f"Error loading results: {e}"

    # Load sentiment results
    try:
        with open("sentiment_results.json", "r", encoding="utf-8") as f:
            sentiment_data = json.load(f)
        print(f"[OK] Loaded {len(sentiment_data)} sentiment results")
    except Exception as e:
        print(f"[ERROR] Failed to load sentiment_results.json: {e}")
        return f"Error loading sentiment results: {e}"

    # Create sentiment lookup
    sentiment_lookup = {}
    for item in sentiment_data:
        filename = item.get("filename", "")
        match = re.search(r"id_(\d+)_", filename)
        if match:
            article_id = int(match.group(1))
            sentiment_lookup[article_id] = item

    print(f"[OK] Parsed {len(sentiment_lookup)} sentiment results by ID")

    cleaned_text_dir = Path("scraped_data/cleaned_text")

    merged_results = []
    low_confidence_count = 0
    low_confidence_ids = []
    skipped_count = 0

    for url_item in urls_data:
        article_id = url_item.get("id")

        # Find cleaned text and language
        article_text = ""
        language = None
        if cleaned_text_dir.exists():
            pattern = f"*_id_{article_id}_"
            for text_file in cleaned_text_dir.glob(f"{pattern}*.txt"):
                filename = text_file.name
                language = (
                    "Turkish"
                    if filename.startswith("0_")
                    else "English" if filename.startswith("1_") else None
                )
                try:
                    with open(text_file, "r", encoding="utf-8") as f:
                        article_text = f.read()
                except Exception as e:
                    print(f"[!]  Failed to read {text_file.name}: {e}")
                break

        # Get sentiment
        sentiment = sentiment_lookup.get(article_id, {})
        label = sentiment.get("label", None)
        confidence = sentiment.get("confidence", None)
        summary = sentiment.get("summary", None)

        # Check if all required fields exist
        if not all(
            [
                article_id,
                url_item.get("url"),
                url_item.get("title"),
                article_text,
                language,
                label is not None,
                confidence is not None,
            ]
        ):
            skipped_count += 1
            continue

        # Check confidence
        needs_attention = confidence < CONFIDENCE_THRESHOLD
        if needs_attention:
            low_confidence_count += 1
            low_confidence_ids.append(article_id)

        merged_results.append(
            {
                "id": article_id,
                "url": url_item.get("url"),
                "title": url_item.get("title"),
                "published_at": url_item.get("published_at"),
                "article_text": article_text,
                "language": language,
                "label": label,
                "confidence": confidence,
                "summary": summary,
                "needs_attention": needs_attention,
            }
        )

    # Check if all articles were filtered out
    if len(merged_results) == 0:
        return "All articles filtered out during processing"

    merged_results.sort(key=lambda x: x["id"])

    # Save results
    output_file = "merged_results.json"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(merged_results, f, ensure_ascii=False, indent=2)
        print(f"Merged {len(merged_results)} articles")
        if low_confidence_count > 0:
            print(f"Low confidence (needs review): {low_confidence_count} articles")
    except Exception as e:
        return f"Error saving results: {e}"

    return None


# Clean up previous run data
clear_scraped_data()

# Step 1: Run URL extractor
print("Step 1/4: Extracting URLs...")
print(f"Company: {COMPANY_NAME}")
print(
    f"Date range: {START_DATE.strftime('%d.%m.%Y')} to {END_DATE.strftime('%d.%m.%Y')}\n"
)

extractor_command = (
    f"python url_extractor.py "
    f'--company "{COMPANY_NAME}" '
    f'--start-date {START_DATE.strftime("%d.%m.%Y")} '
    f'--end-date {END_DATE.strftime("%d.%m.%Y")}'
)

extractor_process = subprocess.Popen(
    extractor_command,
    shell=True,
    stdout=sys.stdout,
    stderr=sys.stderr,
    encoding="utf-8",
)
extractor_process.communicate()

if extractor_process.returncode != 0:
    print(f"\n[ERROR] URL extraction failed with return code {extractor_process.returncode}")
    sys.exit(extractor_process.returncode)

# Check if any URLs were found
try:
    with open("extracted_urls.json", "r", encoding="utf-8") as f:
        urls = json.load(f)

    if not urls or len(urls) == 0:
        print("No articles found - stopping pipeline")
        sys.exit(0)
except Exception as e:
    print(f"[ERROR] Could not read URLs: {e}")
    sys.exit(1)

print(f"Found {len(urls)} articles")

# Step 2-3: Run scraper and html cleaner
step_2_3_commands = "python scraper.py && python html_cleaner.py"

process = subprocess.Popen(
    step_2_3_commands,
    shell=True,
    stdout=sys.stdout,
    stderr=sys.stderr,
    encoding="utf-8",
)
process.communicate()

if process.returncode != 0:
    print(f"\n[ERROR] Scraper/cleaner failed with return code {process.returncode}")
    sys.exit(process.returncode)

# Step 4: Run sentiment analysis with arguments
print("\nStep 4/4: Running sentiment analysis...")
sentiment_command = (
    f"python fine_tuned_sentimental_classification.py " f'--company "{COMPANY_NAME}"'
)

if USE_LOCAL_MODEL:
    sentiment_command += " --uselocalmodel"

sentiment_process = subprocess.Popen(
    sentiment_command,
    shell=True,
    stdout=sys.stdout,
    stderr=sys.stderr,
    encoding="utf-8",
)
sentiment_process.communicate()

# Run merge after all scripts complete
if sentiment_process.returncode == 0:
    result = merge_results()
    if result:
        print(f"Pipeline failed: {result}")
        sys.exit(1)
    else:
        print("Pipeline complete")
else:
    print(f"Sentiment analysis failed")
    sys.exit(sentiment_process.returncode)
