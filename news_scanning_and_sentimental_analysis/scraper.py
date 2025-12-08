"""
News Scraper using Playwright - MAXIMUM SPEED VERSION (STABLE)
Key optimizations:
- Viewport-only screenshots (not full page)
- Faster wait strategy
- No route interception (avoids threading issues)
"""

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

worker_count = 25  # Number of parallel workers
USE_VIEWPORT_ONLY = True


class NewsScraper:
    def __init__(
        self,
        output_dir: str = "scraped_data",
        headless: bool = True,
        timeout: int = 15000,
        max_workers=worker_count,
        viewport_only: bool = USE_VIEWPORT_ONLY,
    ):
        self.output_dir = Path(output_dir)
        self.headless = headless
        self.timeout = timeout
        self.max_workers = max_workers
        self.viewport_only = viewport_only

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
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        try:
            domain = urlparse(url).netloc.replace("www.", "")
            domain = domain.split(".")[0]
        except:
            domain = "unknown"
        return f"article_{index:03d}_{domain}_{url_hash}"

    def _take_screenshot(self, page: Page, output_path: Path) -> bool:
        """Take screenshot (viewport or full page based on settings)"""
        try:
            if self.viewport_only:
                # MUCH FASTER: Only capture visible viewport
                page.screenshot(path=str(output_path), full_page=False)
            else:
                # SLOWER: Capture entire page
                page.screenshot(path=str(output_path), full_page=True)
            return True
        except Exception as e:
            with self.errors_lock:
                self.errors.append(
                    f"Screenshot failed for {output_path.name}: {str(e)}"
                )
            return False

    def _save_html(self, page: Page, output_path: Path) -> bool:
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
        try:
            # Navigate with fastest wait strategy
            page.goto(url, timeout=self.timeout, wait_until="commit")

            # Minimal wait for rendering
            page.wait_for_timeout(800)  # 0.8 seconds

            filename = self._generate_filename(url, index)
            screenshot_path = self.screenshots_dir / f"{filename}.png"
            html_path = self.html_dir / f"{filename}.html"

            # Take screenshot
            screenshot_success = self._take_screenshot(page, screenshot_path)
            if not screenshot_success:
                return None

            # Save HTML
            html_success = self._save_html(page, html_path)
            if not html_success:
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
            with self.errors_lock:
                self.errors.append(f"Scraping failed for {url}: {str(e)}")
            return None

    def _scrape_worker_standalone(self, url_data: Dict, total: int) -> Optional[Dict]:
        url = url_data.get("url")
        idx = url_data.get("index", 0)

        if not url:
            return None

        browser = None
        try:
            with sync_playwright() as p:
                # Launch browser with performance flags
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-extensions",
                        "--disable-plugins",
                        # Performance flags
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--disable-default-apps",
                        "--no-first-run",
                        "--no-zygote",
                    ],
                )

                # Create context
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )

                page = context.new_page()

                print(f"[{idx}/{total}] 🔄 Scraping: {url[:70]}...")
                result = self.scrape_url(url, idx, page, url_data)

                if result:
                    print(f"           ✅ Success")
                else:
                    print(f"           ⏭️  Skipped")

                # Clean close
                page.close()
                context.close()
                browser.close()

                return result

        except Exception as e:
            with self.errors_lock:
                self.errors.append(f"Worker error for {url}: {str(e)}")
            return None
        finally:
            # Ensure browser closes
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
            print(f"❌ Failed to load {json_file}: {e}")
            return []

        if not urls_data:
            print("⚠️ No URLs found in JSON file")
            return []

        print(f"\n{'='*60}")
        print(f"🌐 NEWS SCRAPER STARTED (STABLE + FAST)")
        print(f"{'='*60}")
        print(f"Total URLs to scrape: {len(urls_data)}")
        print(f"Parallel workers: {self.max_workers}")
        print(f"Headless mode: {self.headless}")
        print(
            f"Screenshot mode: {'VIEWPORT ONLY (Fast)' if self.viewport_only else 'FULL PAGE (Slow)'}"
        )
        print(f"Output directory: {self.output_dir}")
        print(f"{'='*60}\n")

        results = []

        for idx, url_data in enumerate(urls_data, 1):
            url_data["index"] = idx

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {
                executor.submit(
                    self._scrape_worker_standalone, url_data, len(urls_data)
                ): url_data
                for url_data in urls_data
            }

            for future in as_completed(future_to_url):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    with self.errors_lock:
                        self.errors.append(f"Future error: {str(e)}")

        results.sort(key=lambda x: x["index"])

        # Save results
        results_file = self.output_dir / "scraped_results.json"
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        if self.errors:
            error_log_file = self.logs_dir / "scraping_errors.log"
            with open(error_log_file, "w", encoding="utf-8") as f:
                f.write(f"Scraping Error Log - {len(self.errors)} errors\n")
                f.write("=" * 60 + "\n\n")
                for i, error in enumerate(self.errors, 1):
                    f.write(f"{i}. {error}\n")
            print(f"\n⚠️  Error log saved to: {error_log_file}")

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

        end_time = time.perf_counter()
        duration = end_time - start_time
        avg_time = duration / len(urls_data) if urls_data else 0
        print(f"\n⏱️  Total time: {duration:.2f} seconds ({duration/60:.2f} minutes)")
        print(f"⚡ Average per URL: {avg_time:.2f} seconds")

        return results


def main():
    if not os.path.exists("extracted_urls.json"):
        print("❌ Error: extracted_urls.json not found!")
        print("   Please run url_extractor.py first to generate URLs.")
        return

    # Create scraper with settings from top of file
    scraper = NewsScraper(
        output_dir="scraped_data",
        headless=True,
        timeout=15000,  # 15 seconds
        max_workers=worker_count,
        viewport_only=USE_VIEWPORT_ONLY,
    )

    results = scraper.scrape_from_json("extracted_urls.json")


if __name__ == "__main__":
    main()
