import pymupdf  # or: import fitz
import os

# Path to your PDFs
PDF_FOLDER = r"C:\Users\fuatk\Desktop\Hackaton\exampleTTSG"

def extract_text_multicolumn(pdf_path):
    """Extract text from multi-column PDF preserving reading order."""
    doc = pymupdf.open(pdf_path)
    all_text = []
    
    for page_num, page in enumerate(doc):
        print(f"  Page {page_num + 1}...")
        
        # Method 1: Layout-preserving extraction (good for columns)
        text = page.get_text("text", sort=True)
        all_text.append(f"=== PAGE {page_num + 1} ===\n{text}")
    
    doc.close()
    return "\n\n".join(all_text)


def extract_text_blocks(pdf_path):
    """Extract text as blocks with position info."""
    doc = pymupdf.open(pdf_path)
    all_blocks = []
    
    for page_num, page in enumerate(doc):
        blocks = page.get_text("blocks", sort=True)
        
        print(f"  Page {page_num + 1}: {len(blocks)} text blocks found")
        
        for block in blocks:
            if block[6] == 0:  # text block (not image)
                x0, y0, x1, y1, text, block_no, block_type = block
                all_blocks.append({
                    "page": page_num + 1,
                    "bbox": (x0, y0, x1, y1),
                    "text": text.strip()
                })
    
    doc.close()
    return all_blocks


# Process each PDF
for filename in os.listdir(PDF_FOLDER):
    if filename.lower().endswith('.pdf'):
        pdf_path = os.path.join(PDF_FOLDER, filename)
        print(f"\n{'='*60}")
        print(f"Processing: {filename}")
        print('='*60)
        
        # Extract full text
        full_text = extract_text_multicolumn(pdf_path)
        
        # Save to file
        output_path = os.path.join(PDF_FOLDER, f"{filename}_extracted.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"  Saved: {output_path}")
        
        # Also extract blocks for structured analysis
        blocks = extract_text_blocks(pdf_path)
        print(f"\n  First 3 blocks preview:")
        for b in blocks[:3]:
            preview = b['text'][:100].replace('\n', ' ')
            print(f"    - {preview}...")