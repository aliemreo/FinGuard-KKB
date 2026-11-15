"""HTML Cleaner with Language Detection - Optimized Version"""

import trafilatura
from langdetect import detect, LangDetectException
from typing import Tuple, List, Dict
import re
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import time


class HTMLCleaner:
    def __init__(self):
        self.min_text_length = 300
        self.max_text_length = 50000
        self._compile_patterns()

    def _compile_patterns(self):
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
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in [
                r"Çerez Politikası.*?Kabul Et",
                r"Cookie Policy.*?Accept",
                r"Çerez Politikası",
                r"Gizlilik Politikası",
                r"En iyi hizmet",
                r"Detaylar için",
                r"0850",
                r"Güncelleme Tarihi: ",
                r"SON DAKİKA",
                r"künye",
                r"manşetler",
                r"yazarlar",
                r"hava durumu",
                r"gazeteler",
                r"beğen",
                r"paylaş",
                r"takip et",
                r"magazin",
                r"mobil uygulamamız",
                r"Son Güncellenme: ",
                r"Son Güncelleme: ",
                r"Müşteri İletişim Merkezi",
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
        if not text:
            return ""

        text = self.whitespace_pattern.sub(" ", text)
        text = self.newline_pattern.sub("\n\n", text)

        for pattern, replacement in self.html_entity_patterns:
            text = pattern.sub(replacement, text)

        for pattern in self.noise_patterns:
            text = pattern.sub("", text)

        text = text.strip()

        if len(text) > self.max_text_length:
            text = text[: self.max_text_length]
            last_period = text.rfind(".")
            if last_period > self.max_text_length * 0.8:
                text = text[: last_period + 1]

        return text

    def detect_language(self, text: str) -> int:
        if not text or len(text) < 50:
            return 0

        try:
            lang = detect(text)
            if lang == "tr":
                return 0
            elif lang == "en":
                return 1
            else:
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
        if not text or len(text) < 50:
            return False

        code_indicators = ["var ", "function(", "const ", "let ", "=>", "typeof"]
        code_count = sum(1 for indicator in code_indicators if indicator in text)
        if code_count > 5:
            return False

        special_count = sum(1 for c in text if c in "{}[];()=<>")
        if len(text) > 0 and (special_count / len(text)) > 0.05:
            return False

        return True

    def extract_from_html_file(self, html_file_path: str) -> Tuple[str, int]:
        try:
            with open(html_file_path, "r", encoding="utf-8") as f:
                html_content = f.read()

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


def clean_html_file(html_file_path: str, verbose: bool = False) -> Tuple[str, int]:
    cleaner = HTMLCleaner()
    text, lang_code = cleaner.extract_from_html_file(html_file_path)
    return text, lang_code


if __name__ == "__main__":
    html_dir = "./scraped_data/html_content/"
    output_dir = "./scraped_data/cleaned_text/"
    max_workers = os.cpu_count()

    total_start = time.time()
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(html_dir):
        print(f"[ERROR] Input directory not found: {html_dir}")
        exit(1)

    html_files = [f for f in os.listdir(html_dir) if f.endswith(".html")]
    if not html_files:
        print(f"[ERROR] No HTML files found")
        exit(1)

    print(f"Cleaning {len(html_files)} HTML files...")
    process_args = [(f, html_dir, output_dir) for f in html_files]

    successful = 0
    failed = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(process_single_file, args): args[0] for args in process_args}
        for future in as_completed(future_to_file):
            result = future.result()
            if result["success"]:
                successful += 1
            else:
                failed += 1

    total_time = time.time() - total_start
    print(f"HTML cleaning complete: {successful}/{len(html_files)} in {total_time:.1f}s")
