import torch
import json
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from torch.utils.data import Dataset, DataLoader

# Configuration
BATCH_SIZE = 32
SCRIPT_DIR = Path(__file__).parent
MODEL_PATH = (
    SCRIPT_DIR / "finetuned_sentiment_model" / "final_model"
)  # fine-tuned model
INPUT_DIR = SCRIPT_DIR / "scraped_data" / "cleaned_text"
OUTPUT_FILE = SCRIPT_DIR / "sentiment_results.json"

ID_TO_LABEL = {0: "positive", 1: "negative", 2: "neutral"}


class FileDataset(Dataset):
    def __init__(self, file_paths):
        self.file_paths = file_paths

    def __len__(self):
        return len(self.file_paths)

    def __getitem__(self, idx):
        try:
            with open(self.file_paths[idx], "r", encoding="utf-8") as f:
                text = f.read().strip()
            return text if text else "ignore_empty"
        except:
            return "ignore_error"


def collate_fn(batch, tokenizer):
    """Custom collate function to tokenize batch"""
    return tokenizer(
        batch, truncation=True, padding=True, max_length=512, return_tensors="pt"
    )


def main():
    # 1. Setup GPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if torch.cuda.is_available():
        print(f"CUDA Active: {torch.cuda.get_device_name(0)}")
    else:
        print("WARNING: CUDA not found. Running on CPU.")

    # 2. Load fine-tuned model and tokenizer
    print(f"Loading fine-tuned model from {MODEL_PATH}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, fix_mistral_regex=True)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
    model.to(device)
    model.eval()

    # 3. Prepare Data
    txt_files = list(INPUT_DIR.glob("*.txt"))
    dataset = FileDataset(txt_files)

    dataloader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        collate_fn=lambda batch: collate_fn(batch, tokenizer),
    )

    results = []
    print(f"Processing {len(txt_files)} files with Batch Size {BATCH_SIZE}...")

    # 4. Inference Loop
    file_idx = 0
    with torch.no_grad():
        for batch_idx, batch in enumerate(dataloader):
            # Move batch to device
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)

            # Get predictions
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=-1)
            confidences = torch.softmax(logits, dim=-1)

            # Process each item in batch
            for i in range(len(predictions)):
                if file_idx >= len(txt_files):
                    break

                file_path = txt_files[file_idx]
                pred_label_id = predictions[i].item()
                confidence = confidences[i][pred_label_id].item()

                sentiment = ID_TO_LABEL[pred_label_id]
                lang = "Turkish" if file_path.name.startswith("0") else "English"

                results.append(
                    {
                        "filename": file_path.name,
                        "language": lang,
                        "label": sentiment,
                        "confidence": round(confidence, 4),
                    }
                )

                file_idx += 1

            if batch_idx % 10 == 0:
                print(f"  {file_idx}/{len(txt_files)} processed.")

    # 5. Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
