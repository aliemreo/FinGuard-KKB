"""
HTML Cleaner with Language Detection
Features:
- Extracts clean text from HTML files using trafilatura
- Detects language (Turkish vs English)
- Returns LLM-ready text
- Handles various edge cases and errors
"""

import trafilatura
from langdetect import detect, LangDetectException
from typing import Tuple
import re


class HTMLCleaner:
    """Clean HTML and extract text suitable for LLM processing"""

    def __init__(self):
        """Initialize HTML cleaner"""
        self.min_text_length = 300  # Minimum text length to consider valid
        self.max_text_length = 50000  # Maximum text length for LLM context

    def clean_text(self, text: str) -> str:
        """
        Clean and normalize extracted text

        Args:
            text: Raw extracted text

        Returns:
            Cleaned text suitable for LLM
        """
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove multiple newlines (keep max 2)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove common HTML artifacts that trafilatura might miss
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)

        # Remove common navigation/UI text patterns (Turkish and English)
        noise_patterns = [
            r"Çerez Politikası.*?Kabul Et",
            r"Cookie Policy.*?Accept",
            r"Reklam\s*\d*",
            r"Advertisement\s*\d*",
            r"Paylaş.*?Facebook.*?Twitter.*?WhatsApp",
            r"Share.*?Facebook.*?Twitter.*?WhatsApp",
            r"Yorumlar\s*\(\d+\)",
            r"Comments\s*\(\d+\)",
        ]

        for pattern in noise_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)

        # Strip and normalize
        text = text.strip()

        # Truncate if too long (keep first part as it usually contains main content)
        if len(text) > self.max_text_length:
            text = text[: self.max_text_length]
            # Try to end at a sentence
            last_period = text.rfind(".")
            if last_period > self.max_text_length * 0.8:
                text = text[: last_period + 1]

        return text

    def detect_language(self, text: str) -> int:
        """
        Detect language of text

        Args:
            text: Text to analyze

        Returns:
            0 for Turkish, 1 for English
        """
        if not text or len(text) < 50:
            # Default to Turkish if text too short
            return 0

        try:
            # Detect language
            lang = detect(text)

            # Map to binary output
            if lang == "tr":
                return 0
            elif lang == "en":
                return 1
            else:
                # For other languages, check which is more likely
                # Count Turkish and English specific characters/words
                turkish_indicators = (
                    len(re.findall(r"[ğĞıİöÖüÜşŞçÇ]", text))
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
            # If detection fails, default to Turkish
            return 0

    def is_valid_content(self, text: str) -> bool:
        """
        Check if extracted text is valid article content (not code/scripts)

        Args:
            text: Extracted text to validate

        Returns:
            True if valid content, False if it's code/scripts
        """
        if not text or len(text) < 50:
            return False

        # Check for code/script indicators
        code_indicators = [
            "var ",
            "function(",
            "return ",
            "const ",
            "let ",
            ".push(",
            ".createElement(",
            "setAttribute(",
            "getElementById(",
            "querySelector(",
            "addEventListener(",
            "{",
            "}",
            "=>",
            "//",
            "/*",
            "*/",
            ";",
            "===",
            "!==",
            "typeof",
            "undefined",
        ]

        # Count how many code indicators are present
        code_count = sum(1 for indicator in code_indicators if indicator in text)

        # If more than 5 different code indicators, it's probably code
        if code_count > 5:
            return False

        # Check ratio of special characters (code has lots of them)
        special_chars = len([c for c in text if c in "{}[];()=<>"])
        if len(text) > 0 and (special_chars / len(text)) > 0.05:
            return False

        return True

    def extract_from_html_file(self, html_file_path: str) -> Tuple[str, int]:
        """
        Extract clean text from HTML file

        Args:
            html_file_path: Path to HTML file

        Returns:
            Tuple of (cleaned_text, language_code)
            language_code: 0 for Turkish, 1 for English
        """
        try:
            # Read HTML file
            with open(html_file_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Try multiple extraction strategies
            extracted_text = None

            # Strategy 1: Precision mode (strict)
            extracted_text = trafilatura.extract(
                html_content,
                favor_precision=True,
                include_comments=False,
                include_tables=True,
                no_fallback=True,  # Don't use fallback initially
            )

            # Strategy 2: If first attempt failed or returned code, try recall mode
            if not extracted_text or not self.is_valid_content(extracted_text):
                extracted_text = trafilatura.extract(
                    html_content,
                    favor_recall=True,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=True,
                )

            # Strategy 3: Try with different settings
            if not extracted_text or not self.is_valid_content(extracted_text):
                extracted_text = trafilatura.extract(
                    html_content,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False,
                    favor_precision=False,
                    favor_recall=False,
                )

            # Final validation
            if not extracted_text:
                raise ValueError("No text could be extracted from HTML")

            if not self.is_valid_content(extracted_text):
                raise ValueError(
                    "Extracted text appears to be code/scripts, not article content"
                )

            # Check minimum length
            if len(extracted_text) < self.min_text_length:
                raise ValueError(
                    f"Extracted text too short ({len(extracted_text)} chars, minimum {self.min_text_length})"
                )

            # Clean the extracted text
            cleaned_text = self.clean_text(extracted_text)

            if not cleaned_text:
                raise ValueError("Cleaned text is empty")

            # Detect language
            language_code = self.detect_language(cleaned_text)

            return cleaned_text, language_code

        except FileNotFoundError:
            raise FileNotFoundError(f"HTML file not found: {html_file_path}")
        except Exception as e:
            raise Exception(f"Error processing HTML file: {e}")

    def process_html_file(
        self, html_file_path: str, verbose: bool = True
    ) -> Tuple[str, int]:
        """
        Main method to process HTML file with optional verbose output

        Args:
            html_file_path: Path to HTML file
            verbose: Print processing information

        Returns:
            Tuple of (cleaned_text, language_code)
        """
        if verbose:
            print(f"\n{'='*60}")
            print(f"🧹 HTML CLEANING STARTED")
            print(f"{'='*60}")
            print(f"File: {html_file_path}")

        try:
            text, lang_code = self.extract_from_html_file(html_file_path)

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


# Convenience function for easy usage
def clean_html_file(html_file_path: str, verbose: bool = True) -> Tuple[str, int]:
    """
    Clean HTML file and return text with language code

    Args:
        html_file_path: Path to HTML file
        verbose: Print processing information

    Returns:
        Tuple of (cleaned_text, language_code)
        language_code: 0 for Turkish, 1 for English
    """
    cleaner = HTMLCleaner()
    return cleaner.process_html_file(html_file_path, verbose=verbose)


# Example usage
if __name__ == "__main__":
    import os

    # Configuration
    html_dir = "./scraped_data/html_content/"
    output_dir = "./scraped_data/cleaned_text/"

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"🚀 BATCH HTML CLEANING")
    print(f"{'='*60}")
    print(f"Input directory: {os.path.abspath(html_dir)}")
    print(f"Output directory: {os.path.abspath(output_dir)}")
    print(f"{'='*60}\n")

    # Check if input directory exists
    if not os.path.exists(html_dir):
        print(f"❌ Error: Input directory not found: {html_dir}")
        print(f"Current working directory: {os.getcwd()}")
        exit(1)

    # Get all .html files
    html_files = [f for f in os.listdir(html_dir) if f.endswith(".html")]

    if not html_files:
        print(f"❌ No HTML files found in {html_dir}")
        exit(1)

    print(f"Found {len(html_files)} HTML files to process\n")

    # Process each file
    cleaner = HTMLCleaner()
    successful = 0
    failed = 0

    for i, html_file in enumerate(html_files, 1):
        input_path = os.path.join(html_dir, html_file)

        print(f"[{i}/{len(html_files)}] Processing: {html_file}")

        try:
            # Extract and clean text
            text, lang_code = cleaner.process_html_file(input_path, verbose=False)
            language = "Turkish" if lang_code == 0 else "English"

            # Create output filename with language code prefix
            # Format: {lang_code}_{original_name}.txt
            output_filename = f"{lang_code}_{html_file.replace('.html', '.txt')}"
            output_path = os.path.join(output_dir, output_filename)

            # Save to text file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)

            print(f"    ✓ Saved: {output_filename}")
            print(f"      Length: {len(text)} chars | Language: {language}\n")
            successful += 1

        except Exception as e:
            print(f"    ✗ Failed: {e}\n")
            failed += 1

    # Summary
    print(f"{'='*60}")
    print(f"📊 PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"✓ Successful: {successful}")
    print(f"✗ Failed: {failed}")
    print(f"📁 Output saved to: {os.path.abspath(output_dir)}")
    print(f"{'='*60}\n")
