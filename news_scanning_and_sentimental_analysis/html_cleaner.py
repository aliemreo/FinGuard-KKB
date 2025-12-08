"""
HTML Cleaner with Language Detection - Optimized Version
Features:
- Extracts clean text from HTML files using trafilatura
- Detects language (Turkish vs English)
- Returns LLM-ready text
- Parallelized batch processing
- Performance timing
"""

import trafilatura
from langdetect import detect, LangDetectException
from typing import Tuple, List, Dict
import re
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
import time


class HTMLCleaner:
    """Clean HTML and extract text suitable for LLM processing"""

    def __init__(self):
        """Initialize HTML cleaner"""
        self.min_text_length = 300
        self.max_text_length = 50000
        # Compile regex patterns once for better performance
        self._compile_patterns()

    def _compile_patterns(self):
        """Precompile regex patterns for better performance"""
        self.whitespace_pattern = re.compile(r"\s+")
        self.newline_pattern = re.compile(r"\n{3,}")
        self.html_entity_patterns = [
            (re.compile(r"&nbsp;"), " "),
            (re.compile(r"&amp;"), "&"),
            (re.compile(r"&lt;"), "<"),
            (re.compile(r"&gt;"), ">"),
            (re.compile(r"&quot;"), '"'),
        ]
        self.noise_patterns = [
            re.compile(pattern, re.IGNORECASE | re.DOTALL)
            for pattern in [
                r"Çerez Politikası.*?Kabul Et",
                r"Cookie Policy.*?Accept",
                r"Reklam\s*\d*",
                r"Advertisement\s*\d*",
                r"Paylaş.*?Facebook.*?Twitter.*?WhatsApp",
                r"Share.*?Facebook.*?Twitter.*?WhatsApp",
                r"Yorumlar\s*\(\d+\)",
                r"Comments\s*\(\d+\)",
            ]
        ]
        self.turkish_char_pattern = re.compile(r"[ğĞıİöÖüÜşŞçÇ]")

    def clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""

        # Use precompiled patterns
        text = self.whitespace_pattern.sub(" ", text)
        text = self.newline_pattern.sub("\n\n", text)

        # Apply HTML entity replacements
        for pattern, replacement in self.html_entity_patterns:
            text = pattern.sub(replacement, text)

        # Remove noise patterns
        for pattern in self.noise_patterns:
            text = pattern.sub("", text)

        text = text.strip()

        # Truncate if too long
        if len(text) > self.max_text_length:
            text = text[: self.max_text_length]
            last_period = text.rfind(".")
            if last_period > self.max_text_length * 0.8:
                text = text[: last_period + 1]

        return text

    def detect_language(self, text: str) -> int:
        """Detect language of text (0=Turkish, 1=English)"""
        if not text or len(text) < 50:
            return 0

        try:
            lang = detect(text)
            if lang == "tr":
                return 0
            elif lang == "en":
                return 1
            else:
                # Fallback to character analysis
                turkish_indicators = (
                    len(self.turkish_char_pattern.findall(text))
                    + text.lower().count(" ve ")
                    + text.lower().count(" bir ")
                )
                english_indicators = (
                    text.lower().count(" the ")
                    + text.lower().count(" and ")
                    + text.lower().count(" a ")
                )
                return 0 if turkish_indicators > english_indicators else 1
        except LangDetectException:
            return 0

    def is_valid_content(self, text: str) -> bool:
        """Check if extracted text is valid article content"""
        if not text or len(text) < 50:
            return False

        # Quick checks using counting
        code_indicators = ["var ", "function(", "const ", "let ", "=>", "typeof"]
        code_count = sum(1 for indicator in code_indicators if indicator in text)

        if code_count > 5:
            return False

        # Check special character ratio
        special_count = sum(1 for c in text if c in "{}[];()=<>")
        if len(text) > 0 and (special_count / len(text)) > 0.05:
            return False

        return True

    def extract_from_html_file(self, html_file_path: str) -> Tuple[str, int]:
        """Extract clean text from HTML file"""
        try:
            with open(html_file_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Try extraction strategies
            for kwargs in [
                {
                    "favor_precision": True,
                    "include_comments": False,
                    "include_tables": True,
                    "no_fallback": True,
                },
                {
                    "favor_recall": True,
                    "include_comments": False,
                    "include_tables": True,
                    "no_fallback": True,
                },
                {
                    "include_comments": False,
                    "include_tables": True,
                    "no_fallback": False,
                },
            ]:
                extracted_text = trafilatura.extract(html_content, **kwargs)
                if extracted_text and self.is_valid_content(extracted_text):
                    break

            if not extracted_text:
                raise ValueError("No text could be extracted from HTML")

            if not self.is_valid_content(extracted_text):
                raise ValueError("Extracted text appears to be code/scripts")

            if len(extracted_text) < self.min_text_length:
                raise ValueError(
                    f"Extracted text too short ({len(extracted_text)} chars)"
                )

            cleaned_text = self.clean_text(extracted_text)
            if not cleaned_text:
                raise ValueError("Cleaned text is empty")

            language_code = self.detect_language(cleaned_text)
            return cleaned_text, language_code

        except FileNotFoundError:
            raise FileNotFoundError(f"HTML file not found: {html_file_path}")
        except Exception as e:
            raise Exception(f"Error processing HTML file: {e}")


def process_single_file(args: Tuple[str, str, str]) -> Dict:
    """
    Process a single HTML file (for parallel execution)

    Args:
        args: Tuple of (html_file, html_dir, output_dir)

    Returns:
        Dict with processing results
    """
    html_file, html_dir, output_dir = args
    input_path = os.path.join(html_dir, html_file)

    result = {
        "filename": html_file,
        "success": False,
        "error": None,
        "output_file": None,
        "text_length": 0,
        "language": None,
    }

    try:
        cleaner = HTMLCleaner()
        text, lang_code = cleaner.extract_from_html_file(input_path)
        language = "Turkish" if lang_code == 0 else "English"

        output_filename = f"{lang_code}_{html_file.replace('.html', '.txt')}"
        output_path = os.path.join(output_dir, output_filename)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)

        result.update(
            {
                "success": True,
                "output_file": output_filename,
                "text_length": len(text),
                "language": language,
            }
        )
    except Exception as e:
        result["error"] = str(e)

    return result


def clean_html_file(html_file_path: str, verbose: bool = True) -> Tuple[str, int]:
    """
    Clean HTML file and return text with language code

    Args:
        html_file_path: Path to HTML file
        verbose: Print processing information

    Returns:
        Tuple of (cleaned_text, language_code)
    """
    cleaner = HTMLCleaner()

    if verbose:
        print(f"\n{'='*60}")
        print(f"🧹 HTML CLEANING STARTED")
        print(f"{'='*60}")
        print(f"File: {html_file_path}")

    try:
        text, lang_code = cleaner.extract_from_html_file(html_file_path)

        if verbose:
            language = "Turkish" if lang_code == 0 else "English"
            print(f"✓ Extraction successful")
            print(f"  - Text length: {len(text)} characters")
            print(f"  - Language: {language} (code: {lang_code})")
            print(f"  - Preview: {text[:200]}...")
            print(f"{'='*60}\n")

        return text, lang_code
    except Exception as e:
        if verbose:
            print(f"✗ Extraction failed: {e}")
            print(f"{'='*60}\n")
        raise


if __name__ == "__main__":
    # Configuration
    html_dir = "./scraped_data/html_content/"
    output_dir = "./scraped_data/cleaned_text/"
    max_workers = os.cpu_count()  # Use all available CPU cores

    # Start total timer
    total_start = time.time()

    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"🚀 BATCH HTML CLEANING (PARALLEL)")
    print(f"{'='*60}")
    print(f"Input directory: {os.path.abspath(html_dir)}")
    print(f"Output directory: {os.path.abspath(output_dir)}")
    print(f"CPU cores: {max_workers}")
    print(f"{'='*60}\n")

    if not os.path.exists(html_dir):
        print(f"❌ Error: Input directory not found: {html_dir}")
        print(f"Current working directory: {os.getcwd()}")
        exit(1)

    html_files = [f for f in os.listdir(html_dir) if f.endswith(".html")]

    if not html_files:
        print(f"❌ No HTML files found in {html_dir}")
        exit(1)

    print(f"Found {len(html_files)} HTML files to process\n")
    print(f"⏱️  Processing started at {time.strftime('%H:%M:%S')}\n")

    # Prepare arguments for parallel processing
    process_args = [(f, html_dir, output_dir) for f in html_files]

    # Process files in parallel
    successful = 0
    failed = 0
    results = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(process_single_file, args): args[0] for args in process_args
        }

        # Process completed tasks
        for i, future in enumerate(as_completed(future_to_file), 1):
            result = future.result()
            results.append(result)

            if result["success"]:
                print(f"[{i}/{len(html_files)}] ✓ {result['filename']}")
                print(f"    → {result['output_file']}")
                print(
                    f"    Length: {result['text_length']} chars | Language: {result['language']}\n"
                )
                successful += 1
            else:
                print(f"[{i}/{len(html_files)}] ✗ {result['filename']}")
                print(f"    Error: {result['error']}\n")
                failed += 1

    # Calculate elapsed time
    total_time = time.time() - total_start
    avg_time = total_time / len(html_files) if html_files else 0

    # Summary
    print(f"{'='*60}")
    print(f"📊 PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"✓ Successful: {successful}")
    print(f"✗ Failed: {failed}")
    print(f"⏱️  Total time: {total_time:.2f} seconds")
    print(f"⚡ Average per file: {avg_time:.2f} seconds")
    print(f"🚀 Speedup: ~{max_workers}x (using {max_workers} cores)")
    print(f"📁 Output saved to: {os.path.abspath(output_dir)}")
    print(f"{'='*60}\n")
