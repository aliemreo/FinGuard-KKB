from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import json
from pathlib import Path

# Load Turkish model
print("Loading Turkish sentiment model...")
tr_model_name = "codealchemist01/turkish-sentiment-analysis"
tr_tokenizer = AutoTokenizer.from_pretrained(tr_model_name)
tr_model = AutoModelForSequenceClassification.from_pretrained(tr_model_name)
tr_id2label = {0: "negative", 1: "neutral", 2: "positive"}

# Load English model
print("Loading English sentiment model...")
en_model_name = "ProsusAI/finbert"
en_tokenizer = AutoTokenizer.from_pretrained(en_model_name)
en_model = AutoModelForSequenceClassification.from_pretrained(en_model_name)
en_id2label = {0: "positive", 1: "negative", 2: "neutral"}

# Directory setup - use script's directory as base
script_dir = Path(__file__).parent
input_dir = script_dir / "scraped_data" / "cleaned_text"
output_file = script_dir / "sentiment_results.json"

results = []

# Process each text file
txt_files = list(input_dir.glob("*.txt"))
print(f"\nFound {len(txt_files)} text files to process...\n")

for idx, file_path in enumerate(txt_files, 1):
    print(f"Processing {idx}/{len(txt_files)}: {file_path.name}")

    try:
        # Determine language from first character
        first_char = file_path.name[0]
        is_turkish = first_char == "0"

        # Select appropriate model
        if is_turkish:
            tokenizer = tr_tokenizer
            model = tr_model
            id2label = tr_id2label
            lang = "Turkish"
        else:
            tokenizer = en_tokenizer
            model = en_model
            id2label = en_id2label
            lang = "English"

        # Read the text file
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read().strip()

        # Skip empty files
        if not text:
            print(f"  Skipping empty file")
            continue

        # Tokenize
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)

        # Predict
        with torch.no_grad():
            outputs = model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            predicted_label_id = predictions.argmax().item()

        # Get label and confidence
        predicted_label = id2label[predicted_label_id]
        confidence = predictions[0][predicted_label_id].item()

        # Store result
        result = {
            "filename": file_path.name,
            "language": lang,
            "label": predicted_label,
            "confidence": round(confidence, 4),
        }
        results.append(result)

        print(f"  {lang} - Label: {predicted_label}, Confidence: {confidence:.4f}")

    except Exception as e:
        print(f"  Error: {str(e)}")
        results.append({"filename": file_path.name, "error": str(e)})

# Save results to JSON
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nProcessing complete! Results saved to {output_file}")
print(
    f"Successfully processed: {len([r for r in results if 'error' not in r])}/{len(results)} files"
)
