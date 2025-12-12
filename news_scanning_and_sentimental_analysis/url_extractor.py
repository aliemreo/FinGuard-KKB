from ddgs import DDGS
import requests
from urllib.parse import urlparse
import time
from datetime import datetime, timedelta
import json
import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional


class NewsFilterConfig:
    # Configuration class for filtering rules

    # Domains to completely block
    BLOCKED_DOMAINS = {
        "twitter.com",
        "x.com",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "tiktok.com",
        "pinterest.com",
        "reddit.com",
        "kariyer.net",
        "indeed.com",
        "glassdoor.com",
        "monster.com",
        "secretcv.com",
        "yenibiris.com",
        "youtube.com",
        "youtu.be",
        "vimeo.com",
        "dailymotion.com",
        "eksisozluk.com",
        "ekşisözlük.com",
        "quora.com",
        "wikipedia.org",
        "wikiwand.com",
        "britannica.com",
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
        "/category/",
        "/search?",
        "/ara?",
        "/haber-arsivi/",
        "/arsiv/",
        "/archive/",
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

    # Priority news domains (Turkish and international) with importance scores
    PRIORITY_DOMAINS = {
        # Turkish - High traffic
        "hurriyet.com.tr": 95,
        "milliyet.com.tr": 90,
        "sabah.com.tr": 92,
        "haberturk.com": 88,
        "ntv.com.tr": 87,
        "cnnturk.com": 89,
        "aa.com.tr": 93,
        "sozcu.com.tr": 86,
        "cumhuriyet.com.tr": 85,
        "yenisafak.com": 84,
        "dha.com.tr": 82,
        "bloomberght.com": 91,
        # International - Very high traffic
        "reuters.com": 98,
        "bloomberg.com": 97,
        "bbc.com": 99,
        "cnn.com": 96,
        "ft.com": 94,
        "wsj.com": 95,
        "theguardian.com": 93,
        "nytimes.com": 97,
        "apnews.com": 92,
        "forbes.com": 90,
        "businessinsider.com": 88,
    }

    # Similarity threshold for duplicate detection (0.0 - 1.0)
    TITLE_SIMILARITY_THRESHOLD = 0.75

    # CurrentNews API Configuration
    CURRENTNEWS_API_KEY = "j0IuEj0aSYQDTmFpbYrboY6DfxKSzvb8Rd6_j-VcfZBaVKI-"
    CURRENTNEWS_BASE_URL = "https://api.currentsapi.services/v1/search"

    # Search queries for DuckDuckGo fallback
    SEARCH_QUERY_TEMPLATES = [
        '"{company}" haber {year}',
        '"{company}" açıklama',
        '"{company}" anlaşma imzaladı',
        '"{company}" duyuru',
    ]


class ImportanceCalculator:
    # Calculates importance scores for URLs based on domain traffic

    def __init__(self, config: NewsFilterConfig):
        self.config = config
        self.domain_cache = {}

    def get_domain_importance(self, url: str) -> int:
        # Get importance score for a domain (0-100)
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")

            # Check cache first
            if domain in self.domain_cache:
                return self.domain_cache[domain]

            # Check if it's a priority domain with pre-defined score
            for priority_domain, score in self.config.PRIORITY_DOMAINS.items():
                if priority_domain in domain:
                    self.domain_cache[domain] = score
                    return score

            score = self._estimate_domain_score(domain)
            self.domain_cache[domain] = score
            return score

        except Exception as e:
            print(f"  ⚠️ Error calculating importance for {url}: {e}")
            return 50  # Default middle score

    def _estimate_domain_score(self, domain: str) -> int:
        # Estimate domain score based on heuristics
        # Turkish news domains (not in priority list)
        turkish_patterns = [
            "haber",
            "gazetesi",
            "ajans",
            "medya",
            "basin",
            ".com.tr",
            "gundem",
            "ekonomi",
        ]
        if any(pattern in domain for pattern in turkish_patterns):
            return 70

        # International news patterns
        intl_patterns = ["news", "times", "post", "press", "daily", "tribune"]
        if any(pattern in domain for pattern in intl_patterns):
            return 65

        # General websites
        return 50

    def calculate_article_importance(
        self,
        url: str,
        is_priority: bool,
        source: str,
        published_at: Optional[str] = None,
    ) -> Dict[str, any]:
        # Calculate comprehensive importance metrics for an article
        # Base domain importance
        domain_score = self.get_domain_importance(url)

        # Source type bonus
        source_bonus = 0
        if source == "currentnews":
            source_bonus = 5  # API results tend to be more relevant

        # Recency boost (if date available)
        recency_boost = 0
        if published_at:
            try:
                pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                days_old = (datetime.now() - pub_date).days

                # More recent = higher boost
                if days_old < 7:
                    recency_boost = 10
                elif days_old < 30:
                    recency_boost = 7
                elif days_old < 90:
                    recency_boost = 5
                elif days_old < 365:
                    recency_boost = 3
            except:
                pass

        # Calculate final importance score
        importance_score = min(100, domain_score + source_bonus + recency_boost)

        return {
            "importance_score": importance_score,
            "domain_score": domain_score,
            "recency_boost": recency_boost,
            "source_bonus": source_bonus,
        }


class DuplicateDetector:
    # Handles detection of duplicate news from different sources

    def __init__(self, similarity_threshold: float = 0.75):
        self.similarity_threshold = similarity_threshold
        self.seen_titles: List[str] = []

    def normalize_title(self, title: str) -> str:
        # Normalize title for comparison
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
        # Calculate similarity between two titles
        norm1 = self.normalize_title(title1)
        norm2 = self.normalize_title(title2)

        if not norm1 or not norm2:
            return 0.0

        return SequenceMatcher(None, norm1, norm2).ratio()

    def is_duplicate(self, title: str) -> bool:
        # Check if this title is a duplicate of previously seen titles
        if not title:
            return False

        for seen_title in self.seen_titles:
            similarity = self.calculate_similarity(title, seen_title)
            if similarity >= self.similarity_threshold:
                return True

        return False

    def add_title(self, title: str):
        # Add title to seen list
        if title:
            self.seen_titles.append(title)

    def reset(self):
        # Clear seen titles
        self.seen_titles.clear()


class ArticleValidator:
    # Validates whether a URL is likely a news article

    def __init__(self, config: NewsFilterConfig):
        self.config = config

    def is_blocked_domain(self, url: str) -> bool:
        # Check if URL is from a blocked domain
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            return any(blocked in domain for blocked in self.config.BLOCKED_DOMAINS)
        except:
            return True

    def has_blocked_pattern(self, url: str) -> bool:
        # Check if URL contains blocked patterns
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in self.config.BLOCKED_PATTERNS)

    def is_homepage(self, url: str) -> bool:
        # Check if URL is likely a homepage or very shallow page
        try:
            path = urlparse(url).path.lower()
            return path in ["", "/", "/tr", "/en", "/tr/", "/en/"]
        except:
            return True

    def looks_like_article(self, url: str) -> bool:
        # Check if URL structure indicates it's an article
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
        # Main validation method
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
        # Check if URL is from a major news source
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            return any(priority in domain for priority in self.config.PRIORITY_DOMAINS)
        except:
            return False


class CurrentNewsSearchEngine:
    # Handles CurrentNews API search operations

    def __init__(self, config: NewsFilterConfig):
        self.config = config
        self.api_key = config.CURRENTNEWS_API_KEY
        self.base_url = config.CURRENTNEWS_BASE_URL

    def search_currentnews(
        self,
        company_name: str,
        max_results: int = 100,
        language: str = "tr",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        print(f"🔍 Searching CurrentNews API for: {company_name}")

        params = {
            "keywords": company_name,
            "apiKey": self.api_key,
            "language": language,
        }

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        results = []

        try:
            # Make API request
            response = requests.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()

            # Check for errors
            if data.get("status") != "ok":
                print(f"  ✗ API Error: {data.get('message', 'Unknown error')}")
                return []

            # Extract articles
            articles = data.get("news", [])
            print(f"  ✓ Found {len(articles)} articles from API")

            for article in articles[:max_results]:
                results.append(
                    {
                        "url": article.get("url", ""),
                        "title": article.get("title", ""),
                        "snippet": article.get("description", ""),
                        "source": article.get("author", "currentnews"),
                        "published_at": article.get("published", ""),
                        "image": article.get("image", ""),
                    }
                )

            return results

        except requests.exceptions.RequestException as e:
            print(f"  ✗ CurrentNews API request failed: {e}")
            return []
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            return []


class DuckDuckGoSearchEngine:
    def __init__(self, config: NewsFilterConfig):
        self.config = config

    def build_queries(
        self,
        company_name: str,
        year: Optional[int] = None,
        start_date: Optional[str] = None,
    ) -> List[str]:
        if year is None:
            if start_date:
                year = int(start_date.split("-")[0])
            else:
                year = datetime.now().year

        queries = []
        for template in self.config.SEARCH_QUERY_TEMPLATES:
            query = template.replace("{company}", company_name).replace(
                "{year}", str(year)
            )
            queries.append(query)

        return queries

    def search_duckduckgo(
        self, company_name: str, max_results: int = 30, start_date: Optional[str] = None
    ) -> List[Dict]:
        print(f"🔍 Searching DuckDuckGo for: {company_name}")
        results = []

        queries = self.build_queries(company_name, start_date=start_date)
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

            print(f"  ✓ Found {len(results)} raw results from DuckDuckGo")
            return results

        except Exception as e:
            print(f"  ✗ DuckDuckGo search failed: {e}")
            return []


class URLExtractor:
    """Main URL extraction and filtering class with hybrid search"""

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
        self.importance_calculator = ImportanceCalculator(self.config)
        self.currentnews_engine = CurrentNewsSearchEngine(self.config)
        self.ddg_engine = DuckDuckGoSearchEngine(self.config)

        self.id_counter = 0

    def filter_and_process_results(
        self,
        raw_results: List[Dict],
        target_count: int,
        source_name: str,
        company_name: str,
    ) -> tuple[List[Dict], Dict]:
        """
        Filter and deduplicate results

        Args:
            raw_results: Raw search results
            target_count: Target number of articles to collect
            source_name: Name of the source for logging

        Returns:
            Tuple of (filtered_urls, stats)
        """
        filtered_urls = []
        stats = {
            "total_found": len(raw_results),
            "blocked_domains": 0,
            "blocked_patterns": 0,
            "not_articles": 0,
            "duplicates": 0,
            "not_in_title": 0,
            "kept": 0,
        }

        print(f"  🔧 Filtering {source_name} results...")

        for result in raw_results:
            url = result["url"]
            title = result.get("title", "")

            if not self.validator.is_valid_article(url):
                if self.validator.is_blocked_domain(url):
                    stats["blocked_domains"] += 1
                elif self.validator.has_blocked_pattern(url):
                    stats["blocked_patterns"] += 1
                else:
                    stats["not_articles"] += 1
                continue

            if company_name.lower() not in title.lower():
                stats["not_in_title"] += 1
                continue

            if self.duplicate_detector.is_duplicate(title):
                stats["duplicates"] += 1
                continue

            is_priority = self.validator.is_priority_source(url)
            importance_data = self.importance_calculator.calculate_article_importance(
                url=url,
                is_priority=is_priority,
                source=result.get("source", "unknown"),
                published_at=result.get("published_at"),
            )

            self.id_counter += 1
            self.duplicate_detector.add_title(title)
            filtered_urls.append(
                {
                    "id": self.id_counter,
                    "url": url,
                    "title": title,
                    "snippet": result.get("snippet", ""),
                    "priority": is_priority,
                    "source": result.get("source", "unknown"),
                    "published_at": result.get("published_at", ""),
                    "importance_score": importance_data["importance_score"],
                    "domain_score": importance_data["domain_score"],
                    "recency_boost": importance_data["recency_boost"],
                }
            )
            stats["kept"] += 1

            if len(filtered_urls) >= target_count:
                break

        return filtered_urls, stats

    def extract_urls(
        self,
        company_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        target_count: int = 30,
        language: str = "tr",
        api_threshold: int = 50,
    ) -> List[Dict]:
        """
        Extract and filter URLs for company news using hybrid approach

        Args:
            company_name: Company name to search for
            start_date: Start date (YYYY-MM-DD) - defaults to 3 years ago
            end_date: End date (YYYY-MM-DD) - defaults to today
            target_count: Target number of unique URLs to return
            language: Language code (tr, en, etc.)
            api_threshold: Minimum API results before using DuckDuckGo fallback

        Returns:
            List of dictionaries with url, title, snippet, priority, source, importance metrics
        """

        self.id_counter = 0

        # Set default dates
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")

        print(f"\n{'='*60}")
        print(f"📰 HYBRID URL EXTRACTION STARTED")
        print(f"{'='*60}")
        print(f"Company: {company_name}")
        print(f"Date Range: {start_date} to {end_date}")
        print(f"Language: {language}")
        print(f"Target: {target_count} unique articles")
        print(f"API Threshold: {api_threshold} articles\n")

        self.duplicate_detector.reset()

        api_results = self.currentnews_engine.search_currentnews(
            company_name,
            max_results=100,
            language=language,
            start_date=start_date,
            end_date=end_date,
        )

        filtered_urls, api_stats = self.filter_and_process_results(
            api_results, target_count, "CurrentNews API", company_name
        )

        print(f"  ✓ API provided {len(filtered_urls)} valid articles")

        if len(filtered_urls) < api_threshold:
            print(
                f"\n⚠️  API results ({len(filtered_urls)}) below threshold ({api_threshold})"
            )
            print(f"🔄 Activating DuckDuckGo fallback...\n")

            remaining_needed = target_count - len(filtered_urls)
            ddg_results = self.ddg_engine.search_duckduckgo(
                company_name, max_results=remaining_needed * 3, start_date=start_date
            )

            ddg_filtered, ddg_stats = self.filter_and_process_results(
                ddg_results, remaining_needed, "DuckDuckGo", company_name
            )

            print(f"  ✓ DuckDuckGo provided {len(ddg_filtered)} additional articles")

            filtered_urls.extend(ddg_filtered)
            combined_stats = {
                "api_total": api_stats["total_found"],
                "api_kept": api_stats["kept"],
                "ddg_total": ddg_stats["total_found"],
                "ddg_kept": ddg_stats["kept"],
                "total_found": api_stats["total_found"] + ddg_stats["total_found"],
                "blocked_domains": api_stats["blocked_domains"]
                + ddg_stats["blocked_domains"],
                "blocked_patterns": api_stats["blocked_patterns"]
                + ddg_stats["blocked_patterns"],
                "not_articles": api_stats["not_articles"] + ddg_stats["not_articles"],
                "not_in_title": api_stats["not_in_title"] + ddg_stats["not_in_title"],
                "duplicates": api_stats["duplicates"] + ddg_stats["duplicates"],
                "kept": api_stats["kept"] + ddg_stats["kept"],
            }
        else:
            print(
                f"\n✅ API provided sufficient results ({len(filtered_urls)} >= {api_threshold})"
            )
            print("📌 DuckDuckGo fallback not needed\n")
            combined_stats = api_stats

        # Sort by importance score (highest first)
        filtered_urls.sort(key=lambda x: x["importance_score"], reverse=True)

        # Limit to target count
        filtered_urls = filtered_urls[:target_count]

        print(f"\n{'='*60}")
        print(f"📊 EXTRACTION STATISTICS")
        print(f"{'='*60}")
        if "api_total" in combined_stats:
            print(
                f"API Results:          {combined_stats['api_total']} found, {combined_stats['api_kept']} kept"
            )
            print(
                f"DuckDuckGo Results:   {combined_stats['ddg_total']} found, {combined_stats['ddg_kept']} kept"
            )
            print(f"---")
        print(f"Total found:          {combined_stats['total_found']}")
        print(f"Blocked domains:      {combined_stats.get('blocked_domains', 0)}")
        print(f"Blocked patterns:     {combined_stats.get('blocked_patterns', 0)}")
        print(f"Not articles:         {combined_stats['not_articles']}")
        print(f"Not in title:         {combined_stats.get('not_in_title', 0)}")
        print(f"Duplicates removed:   {combined_stats['duplicates']}")
        print(f"Final count:          {len(filtered_urls)}")
        print(f"Priority sources:     {sum(1 for u in filtered_urls if u['priority'])}")

        if filtered_urls:
            avg_importance = sum(u["importance_score"] for u in filtered_urls) / len(
                filtered_urls
            )
            max_importance = max(u["importance_score"] for u in filtered_urls)
            min_importance = min(u["importance_score"] for u in filtered_urls)
            print(
                f"Importance scores:    avg={avg_importance:.1f}, max={max_importance}, min={min_importance}"
            )

        print(f"{'='*60}\n")

        return filtered_urls

    def save_to_json(self, urls: List[Dict], filename: str = "extracted_urls.json"):
        """Save URLs to JSON file"""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(urls, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved to {filename}")


# Example usage
if __name__ == "__main__":
    # Create extractor with custom similarity threshold
    extractor = URLExtractor(similarity_threshold=0.75)

    # Extract URLs with hybrid approach
    company_name = "turkcell"
    urls = extractor.extract_urls(
        company_name=company_name,
        start_date="2023-01-01",
        end_date="2025-12-31",
        target_count=50,
        language="tr",
        api_threshold=50,  # Use duckduckgo if API returns < 50 articles
    )

    # Display results
    print("📋 EXTRACTED URLS (sorted by importance):")
    print("=" * 60)
    for i, item in enumerate(urls, 1):
        priority_flag = "⭐" if item["priority"] else "  "
        source_indicator = "🌐" if item["source"] == "duckduckgo" else "📡"
        importance_bar = "█" * (item["importance_score"] // 10)
        print(
            f"{i:2d}. {priority_flag} {source_indicator} [{importance_bar:10s}] {item['importance_score']:3d}/100"
        )
        print(f"     {item['title'][:55]}")
        print(f"     {item['url']}")
        print(
            f"     Source: {item['source']} | Published: {item.get('published_at', 'N/A')}"
        )
        print(f"     Domain Score: {item['domain_score']}\n")

    # Save results
    extractor.save_to_json(urls)
