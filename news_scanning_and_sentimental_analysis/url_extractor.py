"""
Improved URL Extractor and Filter for News Analysis
Features:
- Duplicate news detection using title similarity
- Modular, configurable design
- Better article detection
- Cleaner code structure
"""

try:
    from ddgs import DDGS
except ImportError:
    from ddgs import DDGS

from urllib.parse import urlparse
import time
from datetime import datetime, timedelta
import json
import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Set


class NewsFilterConfig:
    """Configuration class for filtering rules"""

    # Domains to completely block
    BLOCKED_DOMAINS = {
        # Social media
        "twitter.com",
        "x.com",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "tiktok.com",
        "pinterest.com",
        "reddit.com",
        # Job listings
        "kariyer.net",
        "indeed.com",
        "glassdoor.com",
        "monster.com",
        "secretcv.com",
        "yenibiris.com",
        # Video sites
        "youtube.com",
        "youtu.be",
        "vimeo.com",
        "dailymotion.com",
        # Forums & wikis
        "eksisozluk.com",
        "ekşisözlük.com",
        "quora.com",
        "wikipedia.org",
        "wikiwand.com",
        "britannica.com",
        # Non-news finance sites
        "investing.com",
        "finance.yahoo.com",
        "tradingview.com",
        "bigpara.com",
    }

    # URL path patterns to block
    BLOCKED_PATTERNS = [
        "/kariyer",
        "/career",
        "/hakkimizda",
        "/about",
        "/iletisim",
        "/contact",
        "/kunye",
        "/privacy",
        "/gizlilik",
        "/kullanim-kosullari",
        "/terms",
        "/sss",
        "/faq",
        "/haberleri/",
        "/haberler/",
        "/etiket/",
        "/tag/",
        "/kategori/",
        "/search?",
        "/ara?",
        "/haber-arsivi/",
        "/arsiv/",
        "/hisse/",
        "/hisse-haberleri/",
        "/borsa/",
    ]

    # Patterns indicating actual articles
    ARTICLE_INDICATORS = [
        r"/\d{4}/",
        r"/\d{4}-\d{2}/",
        r"/\d{8}/",  # Date patterns
        r"-\d{6,}",
        r"_ID\d+",
        r"/id/",
        r"/\d{6,}",  # ID patterns
        "/gundem/",
        "/ekonomi/",
        "/bilim-teknoloji/",
        "/spor/",
        "/dunya/",
        "/teknoloji/",
        "/finans/",
        "/politika/",
        "/saglik/",
    ]

    # Priority news domains (Turkish and international)
    PRIORITY_DOMAINS = {
        # Turkish
        "hurriyet.com.tr",
        "milliyet.com.tr",
        "sabah.com.tr",
        "haberturk.com",
        "ntv.com.tr",
        "cnnturk.com",
        "aa.com.tr",
        "sozcu.com.tr",
        "cumhuriyet.com.tr",
        "yenisafak.com",
        "dha.com.tr",
        "bloomberght.com",
        # International
        "reuters.com",
        "bloomberg.com",
        "bbc.com",
        "cnn.com",
        "ft.com",
        "wsj.com",
        "theguardian.com",
        "nytimes.com",
        "apnews.com",
        "forbes.com",
        "businessinsider.com",
    }

    # Similarity threshold for duplicate detection (0.0 - 1.0)
    TITLE_SIMILARITY_THRESHOLD = 0.75

    # Search queries for different aspects of company news
    SEARCH_QUERY_TEMPLATES = [
        '"{company}" haber {year}',
        '"{company}" açıklama',
        '"{company}" anlaşma imzaladı',
        '"{company}" duyuru',
    ]


class DuplicateDetector:
    """Handles detection of duplicate news from different sources"""

    def __init__(self, similarity_threshold: float = 0.75):
        self.similarity_threshold = similarity_threshold
        self.seen_titles: List[str] = []

    def normalize_title(self, title: str) -> str:
        """Normalize title for comparison"""
        if not title:
            return ""

        # Convert to lowercase
        title = title.lower()

        # Remove common noise words (Turkish and English)
        noise_words = {
            "haber",
            "son",
            "dakika",
            "breaking",
            "news",
            "live",
            "video",
            "foto",
            "galeri",
            "özel",
            "exclusive",
        }
        words = title.split()
        words = [w for w in words if w not in noise_words]

        # Remove punctuation and extra spaces
        title = " ".join(words)
        title = re.sub(r"[^\w\s]", "", title)
        title = re.sub(r"\s+", " ", title).strip()

        return title

    def calculate_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles"""
        norm1 = self.normalize_title(title1)
        norm2 = self.normalize_title(title2)

        if not norm1 or not norm2:
            return 0.0

        return SequenceMatcher(None, norm1, norm2).ratio()

    def is_duplicate(self, title: str) -> bool:
        """Check if this title is a duplicate of previously seen titles"""
        if not title:
            return False

        for seen_title in self.seen_titles:
            similarity = self.calculate_similarity(title, seen_title)
            if similarity >= self.similarity_threshold:
                return True

        return False

    def add_title(self, title: str):
        """Add title to seen list"""
        if title:
            self.seen_titles.append(title)

    def reset(self):
        """Clear seen titles"""
        self.seen_titles.clear()


class ArticleValidator:
    """Validates whether a URL is likely a news article"""

    def __init__(self, config: NewsFilterConfig):
        self.config = config

    def is_blocked_domain(self, url: str) -> bool:
        """Check if URL is from a blocked domain"""
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            return any(blocked in domain for blocked in self.config.BLOCKED_DOMAINS)
        except:
            return True

    def has_blocked_pattern(self, url: str) -> bool:
        """Check if URL contains blocked patterns"""
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in self.config.BLOCKED_PATTERNS)

    def is_homepage(self, url: str) -> bool:
        """Check if URL is likely a homepage or very shallow page"""
        try:
            path = urlparse(url).path.lower()
            return path in ["", "/", "/tr", "/en", "/tr/", "/en/"]
        except:
            return True

    def looks_like_article(self, url: str) -> bool:
        """Check if URL structure indicates it's an article"""
        try:
            # Check for article indicators
            for pattern in self.config.ARTICLE_INDICATORS:
                if re.search(pattern, url):
                    return True

            # Check URL structure
            parsed = urlparse(url)
            path = parsed.path
            segments = [s for s in path.split("/") if s]

            # Articles usually have multiple path segments and descriptive URLs
            return len(segments) >= 2 and len(path) > 30
        except:
            return False

    def is_valid_article(self, url: str) -> bool:
        """Main validation method"""
        if self.is_blocked_domain(url):
            return False
        if self.has_blocked_pattern(url):
            return False
        if self.is_homepage(url):
            return False
        if not self.looks_like_article(url):
            return False
        return True

    def is_priority_source(self, url: str) -> bool:
        """Check if URL is from a major news source"""
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            return any(priority in domain for priority in self.config.PRIORITY_DOMAINS)
        except:
            return False


class SearchEngine:
    """Handles search operations"""

    def __init__(self, config: NewsFilterConfig):
        self.config = config

    def build_queries(self, company_name: str, year: Optional[int] = None) -> List[str]:
        """Build search queries from templates"""
        if year is None:
            year = datetime.now().year

        queries = []
        for template in self.config.SEARCH_QUERY_TEMPLATES:
            query = template.replace("{company}", company_name).replace(
                "{year}", str(year)
            )
            queries.append(query)

        return queries

    def search_duckduckgo(self, company_name: str, max_results: int = 30) -> List[Dict]:
        """Search DuckDuckGo with multiple query strategies"""
        print(f"🔍 Searching DuckDuckGo for: {company_name}")
        results = []

        queries = self.build_queries(company_name)
        results_per_query = max(5, max_results // len(queries))

        try:
            with DDGS() as ddgs:
                for query in queries:
                    try:
                        search_results = ddgs.text(
                            query, max_results=results_per_query, region="tr-tr"
                        )

                        for result in search_results:
                            url = result.get("href") or result.get("link")
                            if url:
                                results.append(
                                    {
                                        "url": url,
                                        "title": result.get("title", ""),
                                        "snippet": result.get("body", ""),
                                        "source": "duckduckgo",
                                    }
                                )

                        time.sleep(0.5)

                    except Exception as e:
                        print(f"  ⚠️ Query failed: {query[:50]}... - {e}")
                        continue

            print(f"  ✓ Found {len(results)} raw results")
            return results

        except Exception as e:
            print(f"  ✗ DuckDuckGo search failed: {e}")
            return []


class URLExtractor:
    """Main URL extraction and filtering class"""

    def __init__(
        self,
        config: Optional[NewsFilterConfig] = None,
        similarity_threshold: float = 0.75,
    ):
        """
        Initialize URL extractor

        Args:
            config: Configuration object (uses default if None)
            similarity_threshold: Threshold for duplicate detection (0.0-1.0)
        """
        self.config = config or NewsFilterConfig()
        self.validator = ArticleValidator(self.config)
        self.duplicate_detector = DuplicateDetector(similarity_threshold)
        self.search_engine = SearchEngine(self.config)

    def extract_urls(
        self,
        company_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        target_count: int = 30,
    ) -> List[Dict]:
        """
        Extract and filter URLs for company news

        Args:
            company_name: Company name to search for
            start_date: Start date (YYYY-MM-DD) - defaults to 3 years ago
            end_date: End date (YYYY-MM-DD) - defaults to today
            target_count: Target number of unique URLs to return

        Returns:
            List of dictionaries with url, title, snippet, priority, source
        """
        # Set default dates
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")

        print(f"\n{'='*60}")
        print(f"📰 URL EXTRACTION STARTED")
        print(f"{'='*60}")
        print(f"Company: {company_name}")
        print(f"Date Range: {start_date} to {end_date}")
        print(f"Target: {target_count} unique articles\n")

        # Reset duplicate detector
        self.duplicate_detector.reset()

        # Search
        raw_results = self.search_engine.search_duckduckgo(
            company_name,
            max_results=target_count * 3,  # Get more to account for filtering
        )

        # Filter and deduplicate
        filtered_urls = []
        stats = {
            "total_found": len(raw_results),
            "blocked_domains": 0,
            "blocked_patterns": 0,
            "not_articles": 0,
            "duplicates": 0,
            "kept": 0,
        }

        print(f"\n🔧 Filtering and deduplicating results...")

        for result in raw_results:
            url = result["url"]
            title = result.get("title", "")

            # Validate URL
            if not self.validator.is_valid_article(url):
                if self.validator.is_blocked_domain(url):
                    stats["blocked_domains"] += 1
                elif self.validator.has_blocked_pattern(url):
                    stats["blocked_patterns"] += 1
                else:
                    stats["not_articles"] += 1
                continue

            # Check for duplicates
            if self.duplicate_detector.is_duplicate(title):
                stats["duplicates"] += 1
                continue

            # Add to results
            self.duplicate_detector.add_title(title)
            filtered_urls.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": result.get("snippet", ""),
                    "priority": self.validator.is_priority_source(url),
                    "source": result.get("source", "unknown"),
                }
            )
            stats["kept"] += 1

            # Stop if we have enough
            if len(filtered_urls) >= target_count:
                break

        # Sort by priority (major news sources first)
        filtered_urls.sort(key=lambda x: x["priority"], reverse=True)

        # Limit to target count
        filtered_urls = filtered_urls[:target_count]

        # Print statistics
        print(f"\n{'='*60}")
        print(f"📊 EXTRACTION STATISTICS")
        print(f"{'='*60}")
        print(f"Total found:          {stats['total_found']}")
        print(f"Blocked domains:      {stats['blocked_domains']}")
        print(f"Blocked patterns:     {stats['blocked_patterns']}")
        print(f"Not articles:         {stats['not_articles']}")
        print(f"Duplicates removed:   {stats['duplicates']}")
        print(f"Final count:          {len(filtered_urls)}")
        print(f"Priority sources:     {sum(1 for u in filtered_urls if u['priority'])}")
        print(f"{'='*60}\n")

        return filtered_urls

    def save_to_json(self, urls: List[Dict]):
        """Save URLs to JSON file"""
        filename: str = "extracted_urls.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(urls, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved to {filename}")


# Example usage
if __name__ == "__main__":
    # Create extractor with custom similarity threshold
    extractor = URLExtractor(similarity_threshold=0.75)

    # Extract URLs
    company_name = "türkcell"
    urls = extractor.extract_urls(
        company_name=company_name,
        start_date="2023-01-01",
        end_date="2025-12-31",
        target_count=30,
    )

    # Display results
    print("📋 EXTRACTED URLS:")
    print("=" * 60)
    for i, item in enumerate(urls, 1):
        priority_flag = "⭐" if item["priority"] else "  "
        print(f"{i:2d}. {priority_flag} {item['title'][:60]}")
        print(f"     {item['url']}\n")

    # Save results
    extractor.save_to_json(urls)
