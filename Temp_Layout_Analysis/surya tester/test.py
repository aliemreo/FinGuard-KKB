import subprocess
import sys
import os
from surya.model.seg import SuryaSegmenter
from surya.model.detection import SuryaDetector
from surya.model.recognition import SuryaRecognizer
from surya.schema import TextType
from surya.ocr import run_ocr

# --- Step 2: Load models (they will download if not present) ---
print("Loading Surya models...")
detector = SuryaDetector.from_pretrained("microsoft/handwritten-text-detector")
segmenter = SuryaSegmenter.from_pretrained("surya/segmenter")
recognizer = SuryaRecognizer.from_pretrained("surya/recognizer")
print("Surya models loaded.")

# --- Step 3: Run OCR on your PDF file ---
input_pdf_path = "1.pdf"
output_dir = "./results_local/surya/1"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

print(f"Running OCR on {input_pdf_path}...")
results = run_ocr(
    input_pdf_path,
    detector,
    segmenter,
    recognizer,
    output_dir=output_dir,
    text_type=TextType.ALL, # or TextType.PRINTED, TextType.HANDWRITTEN
    images=True # To save intermediate images like --images in CLI
)

print(f"OCR completed. Results saved to {output_dir}")

# You can inspect the results object for detected text, bounding boxes, etc.
# For example, to print text from the first page:
# if results and results.pages:
#     for text_line in results.pages[0].text_lines:
#         print(text_line.text)
