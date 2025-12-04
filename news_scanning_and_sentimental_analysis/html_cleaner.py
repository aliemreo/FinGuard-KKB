"""
HTML Cleaner with Language Detection
Features:
- Extracts clean text from HTML using trafilatura
- Detects language (Turkish vs English)
- Returns LLM-ready text
- Handles various edge cases and errors
"""

import trafilatura
from langdetect import detect, LangDetectException
from typing import Tuple, Optional
import re


class HTMLCleaner:
    """Clean HTML and extract text suitable for LLM processing"""

    def __init__(self):
        """Initialize HTML cleaner"""
        self.min_text_length = 100  # Minimum text length to consider valid
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

            return self.extract_from_html_string(html_content)

        except FileNotFoundError:
            raise FileNotFoundError(f"HTML file not found: {html_file_path}")
        except Exception as e:
            raise Exception(f"Error reading HTML file: {e}")

    def extract_from_html_string(self, html_content: str) -> Tuple[str, int]:
        """
        Extract clean text from HTML string

        Args:
            html_content: HTML content as string

        Returns:
            Tuple of (cleaned_text, language_code)
            language_code: 0 for Turkish, 1 for English
        """
        try:
            # Extract main content using trafilatura
            # favor_precision prioritizes quality over quantity
            # include_comments=False to skip comment sections
            # include_tables=True to capture tabular data
            extracted_text = trafilatura.extract(
                html_content,
                favor_precision=True,
                include_comments=False,
                include_tables=True,
                no_fallback=False,  # Use fallback extraction if needed
            )

            if not extracted_text:
                raise ValueError("No text could be extracted from HTML")

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

        except Exception as e:
            raise Exception(f"Error extracting text from HTML: {e}")

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


# Convenience functions for easy usage
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


def clean_html_string(html_content: str, verbose: bool = False) -> Tuple[str, int]:
    """
    Clean HTML string and return text with language code

    Args:
        html_content: HTML content as string
        verbose: Print processing information

    Returns:
        Tuple of (cleaned_text, language_code)
        language_code: 0 for Turkish, 1 for English
    """
    cleaner = HTMLCleaner()

    if verbose:
        print(f"\n{'='*60}")
        print(f"🧹 HTML CLEANING STARTED")
        print(f"{'='*60}")

    try:
        text, lang_code = cleaner.extract_from_html_string(html_content)

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


# Example usage
if __name__ == "__main__":
    # Example 1: Clean from file
    try:
        text, language = clean_html_file(
            "news_scanning_and_sentimental_analysis\scraped_data\html_content\article_001_milliyet_55cb6ab1.html",
            verbose=True,
        )
        print(f"Language code: {language}")
        print(f"Text length: {len(text)}")
        print(f"\nFirst 500 characters:")
        print(text[:500])
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 60 + "\n")

    # Example 2: Clean from HTML string
    sample_html = """
    <html>
    <head><title>Test Article</title></head>
    <body>
        <nav>Navigation menu</nav>
        <article>
            <h1>Baykar'ın Yeni İHA Projesi</h1>
            <p>Baykar Teknoloji, savunma sanayiinde yeni bir döneme imza atıyor. 
            Şirket, geliştirdiği yeni insansız hava aracı ile dünya pazarında 
            önemli bir oyuncu olmayı hedefliyor.</p>
            <p>Proje kapsamında geliştirilen teknolojiler, yerli ve milli 
            üretim anlayışıyla hayata geçiriliyor. Uzmanlar, bu gelişmenin 
            Türkiye'nin savunma sanayiindeki konumunu güçlendireceğini 
            belirtiyor.</p>
        </article>
        <footer>© 2024 News Site</footer>
    </body>
    </html>
    """

    try:
        text, language = clean_html_string(sample_html, verbose=True)
        lang_name = "Turkish" if language == 0 else "English"
        print(f"Detected language: {lang_name}")
        print(f"\nCleaned text:\n{text}")
    except Exception as e:
        print(f"Error: {e}")

    # Example 3: Using the class directly
    print("\n" + "=" * 60 + "\n")
    print("Example 3: Using HTMLCleaner class directly")

    cleaner = HTMLCleaner()

    # Process multiple files
    html_files = ["article1.html", "article2.html", "article3.html"]

    results = []
    for html_file in html_files:
        try:
            text, lang = cleaner.process_html_file(html_file, verbose=False)
            results.append(
                {
                    "file": html_file,
                    "text": text,
                    "language": "Turkish" if lang == 0 else "English",
                    "length": len(text),
                }
            )
            print(f"✓ {html_file}: {len(text)} chars, {results[-1]['language']}")
        except Exception as e:
            print(f"✗ {html_file}: {e}")

    print(f"\nSuccessfully processed {len(results)} files")
