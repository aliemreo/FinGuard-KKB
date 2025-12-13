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
    raise ValueError("MIA_API_KEY not found in .env file")

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


def get_api_sentiment(client, text, company_name):
    system_prompt = (
        f"Analyze this news article about {company_name}. "
        f"Classify sentiment as 'positive', 'negative', or 'neutral'. Provide confidence (0.0-1.0). "
        f"Write a 2-3 sentence summary in the SAME LANGUAGE as the article. "
        'Return ONLY valid JSON: {{"label": "positive", "confidence": 0.95, "summary": "..."}}'
    )
    try:
        response = client.chat.completions.create(
            model=API_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:4000]},
            ],
            temperature=0.1,
            timeout=45.0,  # Timeout for slow responses
        )
        content = (
            response.choices[0]
            .message.content.replace("```json", "")
            .replace("```", "")
            .strip()
        )
        result = json.loads(content)

        if "label" not in result or result["label"] not in [
            "positive",
            "negative",
            "neutral",
        ]:
            result["label"] = "neutral"
        if "confidence" not in result or not (0 <= result["confidence"] <= 1):
            result["confidence"] = 0.5
        if "summary" not in result or not result["summary"]:
            result["summary"] = "No summary available."
        return result
    except Exception:
        return {
            "label": "neutral",
            "confidence": 0.5,
            "summary": "API analysis failed.",
        }


def process_with_api(txt_files, client, company_name):
    print(
        f"\n🔄 Processing {len(txt_files)} files via API with {API_MAX_WORKERS} parallel workers..."
    )
    start_time = time.time()

    def process_file(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
            lang = "Turkish" if file_path.name.startswith("0") else "English"
            api_result = get_api_sentiment(client, text, company_name)
            return {
                "filename": file_path.name,
                "language": lang,
                "label": api_result["label"],
                "confidence": round(api_result["confidence"], 4),
                "summary": api_result["summary"],
                "source": "api",
            }
        except Exception as e:
            lang = "Turkish" if file_path.name.startswith("0") else "English"
            return {
                "filename": file_path.name,
                "language": lang,
                "label": "neutral",
                "confidence": 0.0,
                "summary": f"Error: {str(e)}",
                "source": "error",
            }

    results = []
    completed = 0
    last_update = 0

    with ThreadPoolExecutor(max_workers=API_MAX_WORKERS) as executor:
        # Submit all at once for maximum parallelization
        future_to_file = {executor.submit(process_file, fp): fp for fp in txt_files}

        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)
            completed += 1

            # Update progress every 3 files or at milestones
            current_time = time.time()
            if (
                completed == 1
                or completed == len(txt_files)
                or completed % 3 == 0
                or (current_time - last_update) > 2
            ):
                elapsed = current_time - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (len(txt_files) - completed) / rate if rate > 0 else 0
                print(
                    f"  Progress: {completed}/{len(txt_files)} ({completed*100//len(txt_files)}%) | Rate: {rate:.1f}/s | ETA: {eta:.0f}s"
                )
                last_update = current_time

    total_time = time.time() - start_time
    print(
        f"✓ API processing complete in {total_time:.1f}s ({len(txt_files)/total_time:.1f} files/sec)"
    )
    return results


def main():
    print(f"\n{'='*60}")
    print(f"🧠 SENTIMENT ANALYSIS - {COMPANY_NAME}")
    print(f"Mode: {'Local Model' if USE_LOCAL_MODEL else 'API'}")
    print(f"{'='*60}\n")

    txt_files = list(INPUT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"❌ No files found in {INPUT_DIR}")
        return

    if not USE_LOCAL_MODEL:  # API mode (default)
        client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
        results = process_with_api(txt_files, client, COMPANY_NAME)
    else:  # Local model mode (when --uselocalmodel flag is used)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(
            f"Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}"
        )
        print(f"Loading model from {MODEL_PATH}...")

        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH).to(
            device
        )
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

        print(f"\n📊 Processing {len(txt_files)} files in batches of {BATCH_SIZE}...")
        start_time = time.time()
        results = []
        low_conf = []
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
                        "summary": None,
                        "source": "local_model",
                    }

                    if confidence < CONFIDENCE_THRESHOLD:
                        low_conf.append(result)

                    results.append(result)
                    file_idx += 1

                # Progress update every few batches
                if (batch_idx + 1) % 5 == 0 or (batch_idx + 1) == len(dataloader):
                    print(
                        f"  Progress: {file_idx}/{len(txt_files)} ({file_idx*100//len(txt_files)}%)"
                    )

        total_time = time.time() - start_time
        print(
            f"✓ Local model complete in {total_time:.1f}s: {len(results)} processed, {len(low_conf)} low confidence (< {CONFIDENCE_THRESHOLD})"
        )

    results.sort(key=lambda x: x["filename"])
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ COMPLETE - {len(results)} files analyzed")
    print(f"💾 Saved to {OUTPUT_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
