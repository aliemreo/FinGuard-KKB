"""
Fast layout detection for Turkish Trade Registry Gazette PDFs.
Decides whether to use simple 2-column split or custom layout detector.
"""
import pymupdf
import numpy as np
from PIL import Image
import io
from pathlib import Path
from typing import Tuple, Callable, Optional
from dataclasses import dataclass


@dataclass
class LayoutDecision:
    """Result of layout analysis"""
    use_simple_split: bool
    num_columns_detected: int
    confidence: float  # 0.0 to 1.0
    valley_positions: list  # normalized positions (0-1) of detected valleys


def analyze_page_layout(page, dpi: int = 72) -> LayoutDecision:
    """
    Analyze a single page's column layout using vertical projection profile.
    
    Args:
        page: PyMuPDF page object
        dpi: Resolution for analysis (72 is fast enough)
    
    Returns:
        LayoutDecision with recommendation
    """
    # Render at low resolution for speed
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert('L')
    
    # Convert to numpy and binarize (text = 1, background = 0)
    arr = np.array(img)
    threshold = 200  # pixels darker than this are "ink"
    binary = (arr < threshold).astype(np.float32)
    
    # Compute vertical projection (sum of ink per column)
    projection = binary.sum(axis=0)
    
    # Analyze only the central region (ignore margins: 10%-90% of width)
    width = len(projection)
    margin = int(width * 0.10)
    central_projection = projection[margin:width - margin]
    central_width = len(central_projection)
    
    if central_width == 0 or central_projection.max() == 0:
        # Empty or nearly empty page
        return LayoutDecision(
            use_simple_split=True,
            num_columns_detected=0,
            confidence=0.5,
            valley_positions=[]
        )
    
    # Smooth the projection to reduce noise
    kernel_size = max(5, central_width // 50)
    kernel = np.ones(kernel_size) / kernel_size
    smoothed = np.convolve(central_projection, kernel, mode='same')
    
    # Normalize
    smoothed_norm = smoothed / smoothed.max()
    
    # Find valleys: local minima below threshold
    valley_threshold = 0.3  # valleys must drop below 30% of max
    
    valleys = []
    for i in range(1, len(smoothed_norm) - 1):
        # Local minimum check
        if smoothed_norm[i] < smoothed_norm[i-1] and smoothed_norm[i] < smoothed_norm[i+1]:
            if smoothed_norm[i] < valley_threshold:
                # Convert to normalized position (0-1 relative to full width)
                norm_pos = (i + margin) / width
                valleys.append((norm_pos, smoothed_norm[i]))
    
    # Merge nearby valleys (within 5% of width)
    merged_valleys = []
    for pos, depth in valleys:
        if not merged_valleys or pos - merged_valleys[-1][0] > 0.05:
            merged_valleys.append((pos, depth))
        elif depth < merged_valleys[-1][1]:
            merged_valleys[-1] = (pos, depth)
    
    # Filter out edge valleys (likely margins/artifacts, not real columns)
    # Only keep valleys in the 15-85% range for column detection
    central_valleys = [(p, d) for p, d in merged_valleys if 0.15 <= p <= 0.85]
    
    valley_positions = [v[0] for v in central_valleys]
    num_valleys = len(valley_positions)
    
    # Decision logic
    if num_valleys == 1:
        valley_pos = valley_positions[0]
        valley_depth = central_valleys[0][1]
        
        # Check if valley is centered (40-60% of page width)
        is_centered = 0.40 <= valley_pos <= 0.60
        is_deep = valley_depth < 0.25  # very low ink density
        
        if is_centered and is_deep:
            confidence = 1.0 - abs(valley_pos - 0.5) * 2  # higher if closer to center
            return LayoutDecision(
                use_simple_split=True,
                num_columns_detected=2,
                confidence=min(0.95, confidence),
                valley_positions=valley_positions
            )
    
    # Any other case: use custom layout detector
    num_columns = num_valleys + 1 if num_valleys > 0 else 1
    return LayoutDecision(
        use_simple_split=False,
        num_columns_detected=num_columns,
        confidence=0.7 if num_valleys > 0 else 0.5,
        valley_positions=valley_positions
    )


def check_pdf_layout(pdf_path: Path, sample_pages: int = 3) -> LayoutDecision:
    """
    Check if a PDF has standard 2-column layout.
    Samples first N pages and uses majority vote.
    
    Args:
        pdf_path: Path to PDF file
        sample_pages: Number of pages to sample (default 3)
    
    Returns:
        LayoutDecision for the document
    """
    doc = pymupdf.open(str(pdf_path))
    
    pages_to_check = min(sample_pages, len(doc))
    decisions = []
    
    for page_num in range(pages_to_check):
        page = doc[page_num]
        decision = analyze_page_layout(page)
        decisions.append(decision)
    
    doc.close()
    
    # Majority vote on use_simple_split
    simple_votes = sum(1 for d in decisions if d.use_simple_split)
    use_simple = simple_votes > pages_to_check / 2
    
    # Average confidence
    avg_confidence = sum(d.confidence for d in decisions) / len(decisions)
    
    # Most common column count
    col_counts = [d.num_columns_detected for d in decisions]
    most_common_cols = max(set(col_counts), key=col_counts.count)
    
    return LayoutDecision(
        use_simple_split=use_simple,
        num_columns_detected=most_common_cols,
        confidence=avg_confidence,
        valley_positions=decisions[0].valley_positions if decisions else []
    )


# =============================================================================
# MAIN OCR DISPATCH FUNCTION - Integrate this into your pipeline
# =============================================================================

def process_pdf_page(
    page,
    simple_ocr_func: Callable,
    complex_ocr_func: Optional[Callable] = None,
    force_simple: bool = False
) -> str:
    """
    Process a single PDF page with appropriate OCR method.
    
    Args:
        page: PyMuPDF page object
        simple_ocr_func: Function for standard 2-column OCR (takes page, returns text)
        complex_ocr_func: Function for complex layout OCR using Surya (takes page, returns text)
        force_simple: Skip layout detection, always use simple method
    
    Returns:
        Extracted text from page
    """
    if force_simple:
        return simple_ocr_func(page)
    
    decision = analyze_page_layout(page)
    
    if decision.use_simple_split:
        return simple_ocr_func(page)
    else:
        if complex_ocr_func is None:
            # Fallback to simple if no complex handler provided
            print(f"    ⚠ Non-standard layout detected but no complex OCR available, using simple split")
            return simple_ocr_func(page)
        return complex_ocr_func(page)


# =============================================================================
# PLACEHOLDER: Your Surya layout detector implementation goes here
# =============================================================================

def surya_layout_ocr(page, dpi: int = 300, debug_dir: Path = None, debug: bool = False) -> str:
    """
    Surya-based OCR for complex layouts.
    Uses layout detection to identify columns first, then OCR each column.
    
    Args:
        page: PyMuPDF page object
        dpi: Resolution for rendering
        debug_dir: If provided, saves debug image with bounding boxes
    
    Returns:
        Extracted text with proper reading order (column by column)
    """
    from surya.foundation import FoundationPredictor
    from surya.recognition import RecognitionPredictor
    from surya.detection import DetectionPredictor
    from surya.layout import LayoutPredictor
    from surya.settings import settings
    from PIL import ImageDraw
    
    # Render page to image
    pix = page.get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pix.tobytes("png"))).convert('RGB')
    
    # Initialize predictors
    foundation_predictor = FoundationPredictor()
    det_predictor = DetectionPredictor()
    rec_predictor = RecognitionPredictor(foundation_predictor)
    layout_predictor = LayoutPredictor(FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT))
    
    # Step 1: Detect layout to find text columns/regions
    layout_results = layout_predictor([image])
    page_layout = layout_results[0]
    
    # Include ALL layout regions (headers, footers, etc.)
    text_labels = {'Text', 'Title', 'Section-header', 'Caption', 'List-item', 
                   'Footnote', 'Table', 'Page-header', 'Page-footer', 'Handwriting'}
    text_regions = []
    for bbox in page_layout.bboxes:
        if bbox.label in text_labels:
            x1, y1, x2, y2 = bbox.bbox
            text_regions.append({
                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                'label': bbox.label,
                'x_center': (x1 + x2) / 2,
                'y_center': (y1 + y2) / 2,
                'width': x2 - x1,
                'height': y2 - y1
            })
    
    # Separate page headers/footers (top 10% and bottom 5% of page)
    page_height = image.height
    header_threshold = page_height * 0.10
    footer_threshold = page_height * 0.95
    
    headers = [r for r in text_regions if r['y_center'] < header_threshold]
    footers = [r for r in text_regions if r['y_center'] > footer_threshold]
    main_regions = [r for r in text_regions if header_threshold <= r['y_center'] <= footer_threshold]
    
    # Sort headers left to right
    headers.sort(key=lambda r: r['x_center'])
    footers.sort(key=lambda r: r['x_center'])
    
    if not main_regions and not headers:
        # Fallback: no layout detected, use full page OCR
        predictions = rec_predictor([image], det_predictor=det_predictor)
        page_result = predictions[0]
        return "\n".join([line.text for line in page_result.text_lines])
    
    # Group main regions into columns based on x overlap
    main_regions.sort(key=lambda r: r['x_center'])
    
    columns = []
    column_threshold = image.width * 0.05  # 5% of page width tolerance
    
    for region in main_regions:
        placed = False
        for col in columns:
            col_x_min = min(r['bbox'][0] for r in col)
            col_x_max = max(r['bbox'][2] for r in col)
            region_x_center = region['x_center']
            
            if col_x_min - column_threshold <= region_x_center <= col_x_max + column_threshold:
                col.append(region)
                placed = True
                break
        
        if not placed:
            columns.append([region])
    
    # Sort columns left to right, then sort regions within each column top to bottom
    columns.sort(key=lambda col: min(r['bbox'][0] for r in col))
    for col in columns:
        col.sort(key=lambda r: r['y_center'])
    
    # Debug visualization
    if debug and debug_dir:
        debug_dir = Path(debug_dir)
        debug_dir.mkdir(parents=True, exist_ok=True)
        
        debug_img = image.copy()
        draw = ImageDraw.Draw(debug_img)
        
        # Draw headers in yellow
        for region in headers:
            bbox = region['bbox']
            draw.rectangle(bbox, outline='yellow', width=3)
            draw.text((bbox[0], bbox[1] - 20), "HDR", fill='yellow')
        
        # Draw footers in gray
        for region in footers:
            bbox = region['bbox']
            draw.rectangle(bbox, outline='gray', width=3)
            draw.text((bbox[0], bbox[1] - 20), "FTR", fill='gray')
        
        # Draw columns in different colors
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'cyan']
        for col_idx, col in enumerate(columns):
            color = colors[col_idx % len(colors)]
            for region in col:
                bbox = region['bbox']
                draw.rectangle(bbox, outline=color, width=3)
                draw.text((bbox[0], bbox[1] - 20), f"Col{col_idx+1}", fill=color)
        
        debug_path = debug_dir / f"debug_layout_page_{page.number}.png"
        debug_img.save(debug_path)
        print(f"    📸 Debug layout image saved: {debug_path}")
    
    # Step 2: OCR each region and combine
    all_texts = []
    
    # OCR headers first (page title, date, etc.)
    if headers:
        header_texts = []
        for region in headers:
            x1, y1, x2, y2 = region['bbox']
            cropped = image.crop((x1, y1, x2, y2))
            predictions = rec_predictor([cropped], det_predictor=det_predictor)
            if predictions and predictions[0].text_lines:
                region_text = " ".join([line.text for line in predictions[0].text_lines])
                header_texts.append(region_text)
        if header_texts:
            all_texts.append("=== PAGE HEADER ===\n\n" + " | ".join(header_texts))
    
    # OCR each column
    for col_idx, col in enumerate(columns):
        column_texts = []
        
        for region in col:
            x1, y1, x2, y2 = region['bbox']
            cropped = image.crop((x1, y1, x2, y2))
            
            predictions = rec_predictor([cropped], det_predictor=det_predictor)
            if predictions and predictions[0].text_lines:
                region_text = "\n".join([line.text for line in predictions[0].text_lines])
                column_texts.append(region_text)
        
        if column_texts:
            all_texts.append(f"=== COLUMN {col_idx + 1} ===\n\n" + "\n\n".join(column_texts))
    
    # OCR footers last
    if footers:
        footer_texts = []
        for region in footers:
            x1, y1, x2, y2 = region['bbox']
            cropped = image.crop((x1, y1, x2, y2))
            predictions = rec_predictor([cropped], det_predictor=det_predictor)
            if predictions and predictions[0].text_lines:
                region_text = " ".join([line.text for line in predictions[0].text_lines])
                footer_texts.append(region_text)
        if footer_texts:
            all_texts.append("=== PAGE FOOTER ===\n\n" + " | ".join(footer_texts))
    
    return "\n\n".join(all_texts)


# =============================================================================
# EXAMPLE: Simple 2-column OCR (your existing implementation)
# =============================================================================

def simple_two_column_ocr(page, dpi: int = 400) -> str:
    """
    Standard 2-column OCR: split page in half, OCR each side.
    This is your existing implementation extracted as a function.
    """
    import pytesseract
    from PIL import ImageEnhance, ImageFilter
    
    # Render page
    pix = page.get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    
    # Preprocessing
    image = image.convert('L')
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    
    # Split columns
    width, height = image.size
    mid_point = width // 2
    
    custom_config = r'--oem 3 --psm 6'
    
    left_col = image.crop((0, 0, mid_point, height))
    left_text = pytesseract.image_to_string(left_col, lang='tur', config=custom_config)
    
    right_col = image.crop((mid_point, 0, width, height))
    right_text = pytesseract.image_to_string(right_col, lang='tur', config=custom_config)
    
    return left_text + "\n\n=== RIGHT COLUMN ===\n\n" + right_text


# =============================================================================
# TEST / DEMO
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python layout_detector.py <pdf_path> [pdf_path2 ...]")
        sys.exit(1)
    
    for pdf_path in sys.argv[1:]:
        path = Path(pdf_path)
        if not path.exists():
            print(f"❌ File not found: {pdf_path}")
            continue
        
        print(f"\n{'='*60}")
        print(f"📄 Analyzing: {path.name}")
        print('='*60)
        
        decision = check_pdf_layout(path)
        
        print(f"  Columns detected: {decision.num_columns_detected}")
        print(f"  Confidence: {decision.confidence:.1%}")
        print(f"  Valley positions: {[f'{v:.1%}' for v in decision.valley_positions]}")
        print(f"  ➡ Recommendation: {'Simple 2-column split' if decision.use_simple_split else 'Use Surya layout detector'}")
