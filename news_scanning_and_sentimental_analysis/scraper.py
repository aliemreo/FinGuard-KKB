"""
News Scraper using Playwright - OPTIMIZED VERSION
Scrapes articles from URLs with parallel processing and viewport screenshots
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from urllib.parse import urlparse
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class NewsScraper:
    # Scrapes news articles using Playwright with parallel processing

    def __init__(
        self,
        output_dir: str = "scraped_data",
        headless: bool = True,
        timeout: int = 15000,
        max_workers: int = 10,
    ):

        self.output_dir = Path(output_dir)
        self.headless = headless
        self.timeout = timeout
        self.max_workers = max_workers

        # Create directory structure
        self.screenshots_dir = self.output_dir / "screenshots"
        self.html_dir = self.output_dir / "html_content"
        self.logs_dir = self.output_dir / "logs"

        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.html_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Error log list (thread-safe)
        self.errors = []
        self.errors_lock = threading.Lock()

    def _generate_filename(self, url: str, index: int) -> str:
        """
        Generate a safe filename from URL

        Args:
            url: Article URL
            index: Article index number

        Returns:
            Safe filename without extension
        """
        # Using hash of URL to ensure uniqueness and avoid filesystem issues
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]

        # Extract domain for readability
        try:
            domain = urlparse(url).netloc.replace("www.", "")
            # Clean domain name
            domain = domain.split(".")[0]  # Get main domain part
        except:
            domain = "unknown"

        return f"article_{index:03d}_{domain}_{url_hash}"

    def _take_full_page_screenshot(self, page: Page, output_path: Path) -> bool:
        """
        Take a full-page screenshot

        Args:
            page: Playwright page object
            output_path: Path to save screenshot

        Returns:
            True if successful, False otherwise
        """
        try:
            page.screenshot(path=str(output_path), full_page=True)
            return True
        except Exception as e:
            with self.errors_lock:
                self.errors.append(
                    f"Screenshot failed for {output_path.name}: {str(e)}"
                )
            return False

    def _save_html(self, page: Page, output_path: Path) -> bool:
        """
        Save page HTML content

        Args:
            page: Playwright page object
            output_path: Path to save HTML

        Returns:
            True if successful, False otherwise
        """
        try:
            html_content = page.content()
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            return True
        except Exception as e:
            with self.errors_lock:
                self.errors.append(f"HTML save failed for {output_path.name}: {str(e)}")
            return False

    def scrape_url(
        self, url: str, index: int, page: Page, metadata: Dict
    ) -> Optional[Dict]:
        """
        Scrape a single URL

        Args:
            url: URL to scrape
            index: Article index
            page: Playwright page object
            metadata: Original metadata from URL extraction

        Returns:
            Dictionary with scraping results or None if failed
        """
        try:
            # Navigate to URL - use domcontentloaded for faster loading
            page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")

            # Generate filename
            filename = self._generate_filename(url, index)

            # Paths for outputs
            screenshot_path = self.screenshots_dir / f"{filename}.png"
            html_path = self.html_dir / f"{filename}.html"

            # Take viewport screenshot (FASTER - first page only)
            screenshot_success = self._take_full_page_screenshot(page, screenshot_path)
            if not screenshot_success:
                with self.errors_lock:
                    self.errors.append(f"Failed to capture screenshot: {url}")
                return None

            # Save HTML
            html_success = self._save_html(page, html_path)
            if not html_success:
                with self.errors_lock:
                    self.errors.append(f"Failed to save HTML: {url}")
                return None

            # Get page title
            try:
                page_title = page.title()
            except:
                page_title = metadata.get("title", "")

            return {
                "url": url,
                "index": index,
                "title": page_title,
                "original_title": metadata.get("title", ""),
                "snippet": metadata.get("snippet", ""),
                "priority": metadata.get("priority", False),
                "source": metadata.get("source", "unknown"),
                "screenshot_path": str(screenshot_path.relative_to(self.output_dir)),
                "html_path": str(html_path.relative_to(self.output_dir)),
                "status": "success",
            }

        except Exception as e:
            # Log error
            with self.errors_lock:
                self.errors.append(f"Scraping failed for {url}: {str(e)}")
            return None

    def _scrape_worker_standalone(self, url_data: Dict, total: int) -> Optional[Dict]:
        """
        Worker function for parallel scraping (each worker gets own browser)

        Args:
            url_data: Dictionary containing URL and metadata
            total: Total number of URLs

        Returns:
            Scraping result or None
        """
        url = url_data.get("url")
        idx = url_data.get("index", 0)

        if not url:
            return None

        # Each worker creates its own playwright instance and browser
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            try:
                print(f"[{idx}/{total}] 🔄 Scraping: {url[:70]}...")
                result = self.scrape_url(url, idx, page, url_data)

                if result:
                    print(f"           ✅ Success")
                else:
                    print(f"           ⏭️  Skipped")

                return result
            finally:
                browser.close()

    def scrape_from_json(self, json_file: str = "extracted_urls.json") -> List[Dict]:
        # Load URLs from JSON
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                urls_data = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load {json_file}: {e}")
            return []

        if not urls_data:
            print("⚠️ No URLs found in JSON file")
            return []

        print(f"\n{'='*60}")
        print(f"🌐 NEWS SCRAPER STARTED (OPTIMIZED)")
        print(f"{'='*60}")
        print(f"Total URLs to scrape: {len(urls_data)}")
        print(f"Parallel workers: {self.max_workers}")
        print(f"Headless mode: {self.headless}")
        print(f"Output directory: {self.output_dir}")
        print(f"{'='*60}\n")

        results = []

        # Add index to each URL data
        for idx, url_data in enumerate(urls_data, 1):
            url_data["index"] = idx

        # Use ThreadPoolExecutor for parallel scraping
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_url = {
                executor.submit(
                    self._scrape_worker_standalone, url_data, len(urls_data)
                ): url_data
                for url_data in urls_data
            }

            # Collect results as they complete
            for future in as_completed(future_to_url):
                result = future.result()
                if result:
                    results.append(result)

        # Sort results by index to maintain order
        results.sort(key=lambda x: x["index"])

        # Save results
        results_file = self.output_dir / "scraped_results.json"
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # Save error log
        if self.errors:
            error_log_file = self.logs_dir / "scraping_errors.log"
            with open(error_log_file, "w", encoding="utf-8") as f:
                f.write(f"Scraping Error Log - {len(self.errors)} errors\n")
                f.write("=" * 60 + "\n\n")
                for i, error in enumerate(self.errors, 1):
                    f.write(f"{i}. {error}\n")
            print(f"\n⚠️  Error log saved to: {error_log_file}")

        # Print summary
        print(f"\n{'='*60}")
        print(f"📊 SCRAPING COMPLETE")
        print(f"{'='*60}")
        print(f"Total attempted: {len(urls_data)}")
        print(f"Successfully scraped: {len(results)}")
        print(f"Failed/Skipped: {len(urls_data) - len(results)}")
        print(f"\n💾 Results saved to: {results_file}")
        print(f"📸 Screenshots saved to: {self.screenshots_dir}")
        print(f"📄 HTML files saved to: {self.html_dir}")
        print(f"{'='*60}\n")

        return results

    def scrape_from_list(self, urls: List[Dict]) -> List[Dict]:
        """
        Scrape from a list of URL dictionaries

        Args:
            urls: List of dictionaries with 'url' key and optional metadata

        Returns:
            List of successfully scraped articles with metadata
        """
        # Save to temp JSON and scrape
        temp_json = "temp_urls.json"
        with open(temp_json, "w", encoding="utf-8") as f:
            json.dump(urls, f, ensure_ascii=False, indent=2)

        results = self.scrape_from_json(temp_json)

        # Clean up temp file
        try:
            os.remove(temp_json)
        except:
            pass

        return results


def main():
    """Run the scraper with extracted URLs"""
    # Check if extracted_urls.json exists
    if not os.path.exists("extracted_urls.json"):
        print("❌ Error: extracted_urls.json not found!")
        print("   Please run url_extractor.py first to generate URLs.")
        return

    # Create scraper with parallel processing
    scraper = NewsScraper(
        output_dir="scraped_data",
        headless=True,
        timeout=15000,  # 15 seconds timeout
        max_workers=10,  # 5 parallel workers for speed
    )

    # Scrape from JSON file
    results = scraper.scrape_from_json("extracted_urls.json")


if __name__ == "__main__":
    main()
