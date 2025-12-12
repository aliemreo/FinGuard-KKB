import subprocess
import os
import sys
import json
from pathlib import Path
import re

os.environ["PYTHONIOENCODING"] = "utf-8"


def merge_results():
    """
    Merge data from extracted_urls.json, screenshots, cleaned text, and sentiment results
    into a single JSON file with flagging for low confidence predictions.
    """
    print("\n" + "=" * 60)
    print("📊 MERGING RESULTS")
    print("=" * 60)

    # Confidence threshold - flag anything below 60%
    CONFIDENCE_THRESHOLD = 0.60

    # Load extracted URLs
    try:
        with open("extracted_urls.json", "r", encoding="utf-8") as f:
            urls_data = json.load(f)
        print(f"✅ Loaded {len(urls_data)} URLs from extracted_urls.json")
    except Exception as e:
        print(f"❌ Failed to load extracted_urls.json: {e}")
        return

    # Load sentiment results
    try:
        with open("sentiment_results.json", "r", encoding="utf-8") as f:
            sentiment_data = json.load(f)
        print(f"✅ Loaded {len(sentiment_data)} sentiment results")
    except Exception as e:
        print(f"❌ Failed to load sentiment_results.json: {e}")
        return

    # Create lookup dictionary from sentiment results using ID extracted from filename
    sentiment_lookup = {}
    for item in sentiment_data:
        filename = item.get("filename", "")
        # Extract ID from filename like "0_id_10_hurriyet_00c0c414.txt"
        match = re.search(r"id_(\d+)_", filename)
        if match:
            article_id = int(match.group(1))
            sentiment_lookup[article_id] = item

    print(f"✅ Parsed {len(sentiment_lookup)} sentiment results by ID")

    # Directories
    screenshots_dir = Path("scraped_data/screenshots")
    cleaned_text_dir = Path("scraped_data/cleaned_text")

    merged_results = []
    low_confidence_count = 0
    low_confidence_ids = []
    skipped_count = 0

    for url_item in urls_data:
        article_id = url_item.get("id")

        # Find screenshot path
        screenshot_path = None
        if screenshots_dir.exists():
            # Handle both single and double digit IDs
            pattern = f"id_{article_id}_"
            for screenshot_file in screenshots_dir.glob(f"{pattern}*.png"):
                screenshot_path = str(screenshot_file.relative_to("."))
                break

        # Find cleaned text and determine language
        article_text = ""
        language = None
        if cleaned_text_dir.exists():
            pattern = f"*_id_{article_id}_"
            for text_file in cleaned_text_dir.glob(f"{pattern}*.txt"):
                # Extract language from filename (0 = Turkish, 1 = English)
                filename = text_file.name
                if filename.startswith("0_"):
                    language = "Turkish"
                elif filename.startswith("1_"):
                    language = "English"

                # Read article text
                try:
                    with open(text_file, "r", encoding="utf-8") as f:
                        article_text = f.read()
                except Exception as e:
                    print(f"⚠️  Failed to read {text_file.name}: {e}")
                break

        # Get sentiment data
        sentiment = sentiment_lookup.get(article_id, {})
        label = sentiment.get("label", None)
        confidence = sentiment.get("confidence", None)

        # Check if all required fields have values
        if not all(
            [
                article_id,
                url_item.get("url"),
                url_item.get("title"),
                screenshot_path,
                article_text,
                language,
                label is not None,
                confidence is not None,
            ]
        ):
            skipped_count += 1
            continue

        # Check if confidence is below threshold
        needs_attention = False
        if confidence < CONFIDENCE_THRESHOLD:
            needs_attention = True
            low_confidence_count += 1
            low_confidence_ids.append(article_id)

        # Build merged entry
        merged_entry = {
            "id": article_id,
            "url": url_item.get("url"),
            "title": url_item.get("title"),
            "published_at": url_item.get("published_at"),
            "path_to_screenshot": screenshot_path,
            "article_text": article_text,
            "language": language,
            "label": label,
            "confidence": confidence,
            "needs_attention": needs_attention,
        }

        merged_results.append(merged_entry)

    # Sort by ID (fast operation)
    merged_results.sort(key=lambda x: x["id"])

    # Save merged results
    output_file = "merged_results.json"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(merged_results, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Successfully merged {len(merged_results)} articles")
        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} articles with missing data")
        print(
            f"⚠️  {low_confidence_count} articles flagged with low confidence (< {CONFIDENCE_THRESHOLD*100}%)"
        )

        if low_confidence_ids:
            print(f"\n🔍 Articles needing attention (IDs): {low_confidence_ids}")

        print(f"\n💾 Saved to: {output_file}")
    except Exception as e:
        print(f"❌ Failed to save merged results: {e}")

    print("=" * 60 + "\n")


command = (
    'python url_extractor.py --company "ASELSAN" --start-date 01.01.2025 --end-date 31.01.2025 && '
    "python scraper.py && "
    "python html_cleaner.py && "
    "python fine_tuned_sentimental_classification.py"
)

process = subprocess.Popen(
    command,
    shell=True,
    stdout=sys.stdout,  # stream directly
    stderr=sys.stderr,  # stream directly
    encoding="utf-8",  # force UTF-8 decoding
)

process.communicate()

# Run merge after all scripts complete
if process.returncode == 0:
    merge_results()
else:
    print(f"\n❌ Pipeline failed with return code {process.returncode}")
    print("⏭️  Skipping merge step")
