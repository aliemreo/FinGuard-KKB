"""News Scraper using Playwright"""

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Page
from urllib.parse import urlparse
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

worker_count = 25


class NewsScraper:
    def __init__(
        self,
        output_dir: str = "scraped_data",
        headless: bool = True,
        timeout: int = 15000,
        max_workers=worker_count,
    ):
        self.output_dir = Path(output_dir)
        self.headless = headless
        self.timeout = timeout
        self.max_workers = max_workers

        self.html_dir = self.output_dir / "html_content"
        self.logs_dir = self.output_dir / "logs"

        for d in [self.html_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.errors = []
        self.errors_lock = threading.Lock()

    def _generate_filename(self, url: str, index: int, article_id: int) -> str:
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        try:
            domain = urlparse(url).netloc.replace("www.", "").split(".")[0]
        except:
            domain = "unknown"
        return f"id_{article_id}_{domain}_{url_hash}"

    def _save_html(self, page: Page, output_path: Path) -> bool:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            return True
        except Exception as e:
            with self.errors_lock:
                self.errors.append(f"HTML save failed: {str(e)[:50]}")
            return False

    def scrape_url(self, url: str, index: int, page: Page, metadata: Dict) -> Optional[Dict]:
        try:
            page.goto(url, timeout=self.timeout, wait_until="commit")
            page.wait_for_timeout(500)

            filename = self._generate_filename(url, index, metadata.get("id", 0))
            html_path = self.html_dir / f"{filename}.html"

            if not self._save_html(page, html_path):
                return None

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
                "html_path": str(html_path.relative_to(self.output_dir)),
                "status": "success",
            }
        except Exception as e:
            with self.errors_lock:
                self.errors.append(f"Scrape failed: {str(e)[:50]}")
            return None

    def _scrape_worker_standalone(self, url_data: Dict, total: int) -> Optional[Dict]:
        url = url_data.get("url")
        idx = url_data.get("index", 0)
        if not url:
            return None

        browser = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage", "--no-sandbox"],
                )
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                )
                page = context.new_page()
                result = self.scrape_url(url, idx, page, url_data)
                page.close()
                context.close()
                browser.close()
                return result
        except Exception as e:
            with self.errors_lock:
                self.errors.append(f"Worker error: {str(e)[:50]}")
            return None
        finally:
            if browser:
                try:
                    browser.close()
                except:
                    pass

    def scrape_from_json(self, json_file: str = "extracted_urls.json") -> List[Dict]:
        start_time = time.perf_counter()
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                urls_data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load {json_file}: {e}")
            return []

        if not urls_data:
            print("[!] No URLs found")
            return []

        print(f"\nScraping {len(urls_data)} URLs with {self.max_workers} workers...")

        results = []
        for idx, url_data in enumerate(urls_data, 1):
            url_data["index"] = idx

        completed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {
                executor.submit(self._scrape_worker_standalone, url_data, len(urls_data)): url_data
                for url_data in urls_data
            }
            for future in as_completed(future_to_url):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                    completed += 1
                    if completed % 5 == 0 or completed == len(urls_data):
                        print(f"  Progress: {completed}/{len(urls_data)} ({completed*100//len(urls_data)}%)")
                except Exception as e:
                    with self.errors_lock:
                        self.errors.append(f"Future error: {str(e)[:50]}")

        results.sort(key=lambda x: x["index"])

        results_file = self.output_dir / "logs" / "scraped_results.json"
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        if self.errors:
            error_log_file = self.logs_dir / "scraping_errors.log"
            with open(error_log_file, "w", encoding="utf-8") as f:
                for error in self.errors:
                    f.write(f"{error}\n")

        duration = time.perf_counter() - start_time
        print(f"Scraping complete: {len(results)}/{len(urls_data)} in {duration:.1f}s")
        return results


def main():
    if not os.path.exists("extracted_urls.json"):
        print("[ERROR] extracted_urls.json not found")
        return

    scraper = NewsScraper(
        output_dir="scraped_data",
        headless=True,
        timeout=15000,
        max_workers=worker_count,
    )
    scraper.scrape_from_json("extracted_urls.json")


if __name__ == "__main__":
    main()
