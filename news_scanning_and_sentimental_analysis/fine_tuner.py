import torch
from pathlib import Path
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
)
from torch.utils.data import Dataset
from sklearn.model_selection import train_test_split
import numpy as np
from sklearn.metrics import accuracy_score, f1_score

# Configuration
MODEL_NAME = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
SCRIPT_DIR = Path(__file__).parent
DATASET_PATH = SCRIPT_DIR / "training_data"
OUTPUT_DIR = SCRIPT_DIR / "finetuned_sentiment_model"

LABEL_MAP = {"positive": 0, "negative": 1, "neutral": 2}
ID_TO_LABEL = {0: "positive", 1: "negative", 2: "neutral"}


class SentimentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length=512):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        text = self.texts[idx]
        label = self.labels[idx]

        encoding = self.tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )

        return {
            "input_ids": encoding["input_ids"].flatten(),
            "attention_mask": encoding["attention_mask"].flatten(),
            "labels": torch.tensor(label, dtype=torch.long),
        }


def load_data_from_folders():
    """Load all text files from positive, negative, neutral folders"""
    texts = []
    labels = []

    for folder_name in ["positive", "negative", "neutral"]:
        folder_path = DATASET_PATH / folder_name
        label = LABEL_MAP[folder_name]

        txt_files = list(folder_path.glob("*.txt"))
        print(f"Loading {len(txt_files)} files from {folder_name}...")

        for file_path in txt_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read().strip()

                if text:  # Only add non-empty texts
                    texts.append(text)
                    labels.append(label)
            except Exception as e:
                print(f"Error reading {file_path.name}: {e}")

    return texts, labels


def compute_metrics(eval_pred):
    """Compute accuracy and F1 score"""
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)

    accuracy = accuracy_score(labels, predictions)
    f1 = f1_score(labels, predictions, average="weighted")

    return {"accuracy": accuracy, "f1": f1}


def main():
    print("Starting fine-tuning process...\n")

    # 1. Load tokenizer and model
    print("Loading tokenizer and model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=3,  # positive, negative, neutral
        ignore_mismatched_sizes=True,  # Since we're changing the classification head
    )

    # 2. Load data
    print("\nLoading data from folders...")
    texts, labels = load_data_from_folders()
    print(f"Total samples loaded: {len(texts)}")
    print(
        f"Label distribution: Positive={labels.count(0)}, Negative={labels.count(1)}, Neutral={labels.count(2)}"
    )

    # 3. Split into train and validation sets (80/20)
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    print(f"\nTrain samples: {len(train_texts)}")
    print(f"Validation samples: {len(val_texts)}")

    # 4. Create datasets
    train_dataset = SentimentDataset(train_texts, train_labels, tokenizer)
    val_dataset = SentimentDataset(val_texts, val_labels, tokenizer)

    # 5. Setup training arguments (optimized for 8GB VRAM)
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=4,  # Sweet spot for fine-tuning - enough to learn, not overfit
        per_device_train_batch_size=16,  # Good balance for 8GB VRAM
        per_device_eval_batch_size=32,  # Can be larger since no gradients
        gradient_accumulation_steps=2,  # Effective batch size = 16 * 2 = 32
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_ratio=0.1,  # Warmup for 10% of training
        logging_dir=str(OUTPUT_DIR / "logs"),
        logging_steps=25,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        fp16=torch.cuda.is_available(),  # Use mixed precision to save VRAM
        save_total_limit=2,  # Only keep 2 best checkpoints
        dataloader_num_workers=2,  # Parallel data loading
        optim="adamw_torch",  # Efficient optimizer
        report_to="none",  # Disable wandb/tensorboard
    )

    # 6. Initialize Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
    )

    # 7. Train
    print("\nStarting training...")
    trainer.train()

    # 8. Save the final model
    print("\nSaving final model...")
    model.save_pretrained(OUTPUT_DIR / "final_model")
    tokenizer.save_pretrained(OUTPUT_DIR / "final_model")

    # 9. Evaluate
    print("\nEvaluating on validation set...")
    eval_results = trainer.evaluate()
    print(f"Validation Results: {eval_results}")

    print(f"\n✅ Fine-tuning complete! Model saved to: {OUTPUT_DIR / 'final_model'}")
    print("\nTo use this model, replace the MODEL_NAME in your inference script with:")
    print(f'MODEL_NAME = "{OUTPUT_DIR / "final_model"}"')


if __name__ == "__main__":
    main()
