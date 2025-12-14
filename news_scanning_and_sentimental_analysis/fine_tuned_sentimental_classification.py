import torch
import json
import os
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from torch.utils.data import Dataset, DataLoader
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import time

load_dotenv()

parser = argparse.ArgumentParser()
parser.add_argument("--company", type=str, required=True)
parser.add_argument(
    "--uselocalmodel",
    action="store_true",
    help="Use local fine-tuned model instead of OpenAI API (default: API)",
)
args = parser.parse_args()

COMPANY_NAME = args.company
USE_LOCAL_MODEL = (
    args.uselocalmodel
)  # True = use local model, False (default) = use API
BATCH_SIZE = 64  # Increased for faster local processing
API_MAX_WORKERS = 20  # Increased for faster API processing
CONFIDENCE_THRESHOLD = 0.90
SCRIPT_DIR = Path(__file__).parent
MODEL_PATH = SCRIPT_DIR / "finetuned_sentiment_model" / "final_model"
INPUT_DIR = SCRIPT_DIR / "scraped_data" / "cleaned_text"
OUTPUT_FILE = SCRIPT_DIR / "sentiment_results.json"
API_KEY = os.getenv("MIA_API_KEY")
API_BASE_URL = "https://mia.csp.kloudeks.com/v1"
API_MODEL = "gpt-oss-120b"

if not USE_LOCAL_MODEL and not API_KEY:
    print("[!] MIA_API_KEY not found - will use local model only")
    USE_LOCAL_MODEL = True

ID_TO_LABEL = {0: "positive", 1: "negative", 2: "neutral"}


class FileDataset(Dataset):
    def __init__(self, file_paths):
        self.file_paths = file_paths

    def __len__(self):
        return len(self.file_paths)

    def __getitem__(self, idx):
        try:
            with open(self.file_paths[idx], "r", encoding="utf-8") as f:
                return f.read().strip() or "ignore_empty"
        except:
            return "ignore_error"


def get_api_sentiment(client, text, company_name, max_retries=3):
    """Call API with retries for reliability"""
    system_prompt = (
        f"Analyze this news article about {company_name}. "
        f"Classify sentiment as 'positive', 'negative', or 'neutral'. Provide confidence (0.0-1.0). "
        f"Write a 2-3 sentence summary in the SAME LANGUAGE as the article. "
        'Return ONLY valid JSON: {{"label": "positive", "confidence": 0.95, "summary": "..."}}'
    )
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=API_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text[:4000]},
                ],
                temperature=0.1,
                timeout=60.0,  # Increased timeout
            )
            content = (
                response.choices[0]
                .message.content.replace("```json", "")
                .replace("```", "")
                .strip()
            )
            result = json.loads(content)

            if "label" not in result or result["label"] not in ["positive", "negative", "neutral"]:
                result["label"] = "neutral"
            if "confidence" not in result or not (0 <= result["confidence"] <= 1):
                result["confidence"] = 0.5
            if "summary" not in result or not result["summary"]:
                result["summary"] = "No summary available."
            return result, True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))  # Backoff
                continue
            return {"label": "neutral", "confidence": 0.0, "summary": None}, False


def process_with_api(txt_files, client, company_name):
    print(f"Processing {len(txt_files)} files via API...")
    start_time = time.time()
    failed_files = []

    def process_file(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
            lang = "Turkish" if file_path.name.startswith("0") else "English"
            api_result, success = get_api_sentiment(client, text, company_name)
            return {
                "filename": file_path.name,
                "language": lang,
                "label": api_result["label"],
                "confidence": round(api_result["confidence"], 4),
                "summary": api_result["summary"],
                "source": "api" if success else "api_failed",
                "file_path": file_path,  # Keep for fallback
                "success": success,
            }
        except Exception as e:
            lang = "Turkish" if file_path.name.startswith("0") else "English"
            return {
                "filename": file_path.name,
                "language": lang,
                "label": "neutral",
                "confidence": 0.0,
                "summary": f"Error: {str(e)[:50]}",
                "source": "error",
                "file_path": file_path,
                "success": False,
            }

    results = []
    completed = 0
    last_update = 0

    with ThreadPoolExecutor(max_workers=API_MAX_WORKERS) as executor:
        future_to_file = {executor.submit(process_file, fp): fp for fp in txt_files}

        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)
            if not result.get("success"):
                failed_files.append(result["file_path"])
            completed += 1

            current_time = time.time()
            if completed == len(txt_files) or completed % 10 == 0:
                print(f"  {completed}/{len(txt_files)} done")

    total_time = time.time() - start_time
    print(f"API complete: {len(txt_files)} files in {total_time:.1f}s")
    
    return results, failed_files


def process_with_local_model(txt_files, device=None):
    """Process files with local model - used as primary or fallback"""
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    import warnings
    warnings.filterwarnings("ignore", message=".*regex.*")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, use_fast=False)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH).to(device)
    model.eval()

    dataset = FileDataset(txt_files)
    dataloader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        collate_fn=lambda batch: tokenizer(
            batch,
            truncation=True,
            padding=True,
            max_length=512,
            return_tensors="pt",
        ),
    )

    print(f"Processing {len(txt_files)} files with local model...")
    start_time = time.time()
    results = []
    file_idx = 0

    with torch.no_grad():
        for batch_idx, batch in enumerate(dataloader):
            input_ids = batch["input_ids"].to(device, non_blocking=True)
            attention_mask = batch["attention_mask"].to(device, non_blocking=True)
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=-1)
            confidences = torch.softmax(logits, dim=-1)

            for i in range(len(predictions)):
                if file_idx >= len(txt_files):
                    break
                file_path = txt_files[file_idx]
                pred_label_id = predictions[i].item()
                confidence = confidences[i][pred_label_id].item()
                sentiment = ID_TO_LABEL[pred_label_id]
                lang = "Turkish" if file_path.name.startswith("0") else "English"

                result = {
                    "filename": file_path.name,
                    "language": lang,
                    "label": sentiment,
                    "confidence": round(confidence, 4),
                    "summary": None,  # Leave empty so report uses article snippet
                    "source": "local_model",
                }
                results.append(result)
                file_idx += 1

    total_time = time.time() - start_time
    print(f"Local model complete: {len(results)} files in {total_time:.1f}s")
    return results


def main():
    print(f"\n{'='*60}")
    print(f"SENTIMENT ANALYSIS - {COMPANY_NAME}")
    print(f"Mode: {'Local Model' if USE_LOCAL_MODEL else 'API (with local fallback)'}")
    print(f"{'='*60}\n")

    txt_files = list(INPUT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"[ERROR] No files found in {INPUT_DIR}")
        return

    results = []
    
    if USE_LOCAL_MODEL:
        # Use local model only
        results = process_with_local_model(txt_files)
    else:
        # API mode with local model fallback
        client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
        api_results, failed_files = process_with_api(txt_files, client, COMPANY_NAME)
        
        # Filter out failed results and keep successful ones
        results = [r for r in api_results if r.get("success", False)]
        
        # Clean up file_path from results (not needed in output)
        for r in results:
            r.pop("file_path", None)
            r.pop("success", None)
        
        # If there are failed files, retry with local model
        if failed_files:
            print(f"\n[!] {len(failed_files)} files failed API - retrying with local model...")
            fallback_results = process_with_local_model(failed_files)
            results.extend(fallback_results)
            print(f"[OK] Fallback complete - recovered {len(fallback_results)} files")

    results.sort(key=lambda x: x["filename"])
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"[OK] COMPLETE - {len(results)} files analyzed")
    print(f"[SAVE] Saved to {OUTPUT_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
