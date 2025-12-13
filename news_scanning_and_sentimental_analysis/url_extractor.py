from ddgs import DDGS
import requests
from urllib.parse import urlparse
import time
from datetime import datetime, timedelta
import json
import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--start-date", type=str, required=True)
parser.add_argument("--end-date", type=str, required=True)
parser.add_argument("--company", type=str, required=True)
args = parser.parse_args()

START_DATE = datetime.strptime(args.start_date, "%d.%m.%Y")
END_DATE = datetime.strptime(args.end_date, "%d.%m.%Y")
COMPANY_NAME = args.company


class NewsFilterConfig:
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

    ARTICLE_INDICATORS = [
        r"/\d{4}/",
        r"/\d{4}-\d{2}/",
        r"/\d{8}/",
        r"-\d{6,}",
        r"_ID\d+",
        r"/id/",
        r"/\d{6,}",
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

    PRIORITY_DOMAINS = {
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

    TITLE_SIMILARITY_THRESHOLD = 0.75
    CURRENTNEWS_API_KEY = "j0IuEj0aSYQDTmFpbYrboY6DfxKSzvb8Rd6_j-VcfZBaVKI-"
    CURRENTNEWS_BASE_URL = "https://api.currentsapi.services/v1/search"
    SEARCH_QUERY_TEMPLATES = [
        '"{company}" haber {year}',
        '"{company}" açıklama',
        '"{company}" anlaşma imzaladı',
        '"{company}" duyuru',
    ]


class ImportanceCalculator:
    def __init__(self, config: NewsFilterConfig):
        self.config = config
        self.domain_cache = {}

    def get_domain_importance(self, url: str) -> int:
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            if domain in self.domain_cache:
                return self.domain_cache[domain]

            for priority_domain, score in self.config.PRIORITY_DOMAINS.items():
                if priority_domain in domain:
                    self.domain_cache[domain] = score
                    return score

            score = self._estimate_domain_score(domain)
            self.domain_cache[domain] = score
            return score
        except Exception as e:
            print(f"  ⚠️ Error calculating importance for {url}: {e}")
            return 50

    def _estimate_domain_score(self, domain: str) -> int:
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
        if any(p in domain for p in turkish_patterns):
            return 70
        intl_patterns = ["news", "times", "post", "press", "daily", "tribune"]
        if any(p in domain for p in intl_patterns):
            return 65
        return 50

    def calculate_article_importance(
        self,
        url: str,
        is_priority: bool,
        source: str,
        published_at: Optional[str] = None,
    ) -> Dict[str, any]:
        domain_score = self.get_domain_importance(url)
        source_bonus = 5 if source == "currentnews" else 0
        recency_boost = 0

        if published_at:
            try:
                pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                days_old = (datetime.now() - pub_date).days
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

        importance_score = min(100, domain_score + source_bonus + recency_boost)
        return {
            "importance_score": importance_score,
            "domain_score": domain_score,
            "recency_boost": recency_boost,
            "source_bonus": source_bonus,
        }


class DuplicateDetector:
    def __init__(self, similarity_threshold: float = 0.75):
        self.similarity_threshold = similarity_threshold
        self.seen_titles: List[str] = []

    def normalize_title(self, title: str) -> str:
        if not title:
            return ""
        title = title.lower()
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
        words = [w for w in title.split() if w not in noise_words]
        title = " ".join(words)
        title = re.sub(r"[^\w\s]", "", title)
        return re.sub(r"\s+", " ", title).strip()

    def calculate_similarity(self, title1: str, title2: str) -> float:
        norm1, norm2 = self.normalize_title(title1), self.normalize_title(title2)
        return SequenceMatcher(None, norm1, norm2).ratio() if norm1 and norm2 else 0.0

    def is_duplicate(self, title: str) -> bool:
        if not title:
            return False
        return any(
            self.calculate_similarity(title, seen) >= self.similarity_threshold
            for seen in self.seen_titles
        )

    def add_title(self, title: str):
        if title:
            self.seen_titles.append(title)

    def reset(self):
        self.seen_titles.clear()


class ArticleValidator:
    def __init__(self, config: NewsFilterConfig):
        self.config = config

    def is_blocked_domain(self, url: str) -> bool:
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            return any(blocked in domain for blocked in self.config.BLOCKED_DOMAINS)
        except:
            return True

    def has_blocked_pattern(self, url: str) -> bool:
        return any(p in url.lower() for p in self.config.BLOCKED_PATTERNS)

    def is_homepage(self, url: str) -> bool:
        try:
            path = urlparse(url).path.lower()
            return path in ["", "/", "/tr", "/en", "/tr/", "/en/"]
        except:
            return True

    def looks_like_article(self, url: str) -> bool:
        try:
            if any(re.search(p, url) for p in self.config.ARTICLE_INDICATORS):
                return True
            parsed = urlparse(url)
            segments = [s for s in parsed.path.split("/") if s]
            return len(segments) >= 2 and len(parsed.path) > 30
        except:
            return False

    def is_valid_article(self, url: str) -> bool:
        return (
            not self.is_blocked_domain(url)
            and not self.has_blocked_pattern(url)
            and not self.is_homepage(url)
            and self.looks_like_article(url)
        )

    def is_priority_source(self, url: str) -> bool:
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            return any(p in domain for p in self.config.PRIORITY_DOMAINS)
        except:
            return False


class CurrentNewsSearchEngine:
    def __init__(self, config: NewsFilterConfig):
        self.config = config
        self.api_key = config.CURRENTNEWS_API_KEY
        self.base_url = config.CURRENTNEWS_BASE_URL

    def search_currentnews(
        self,
        company_name: str,
        max_results: int = 100,
        language: str = "tr",
        start_date: Optional[str] = START_DATE,
        end_date: Optional[str] = END_DATE,
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

        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "ok":
                print(f"  ✗ API Error: {data.get('message', 'Unknown error')}")
                return []

            articles = data.get("news", [])
            print(f"  ✓ Found {len(articles)} articles from API")

            return [
                {
                    "url": a.get("url", ""),
                    "title": a.get("title", ""),
                    "snippet": a.get("description", ""),
                    "source": a.get("author", "currentnews"),
                    "published_at": a.get("published", ""),
                    "image": a.get("image", ""),
                }
                for a in articles[:max_results]
            ]
        except requests.exceptions.RequestException as e:
            print(f"  ✗ CurrentNews API request failed: {e}")
            return []
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            return []


class DateExtractor:
    @staticmethod
    def extract_date_from_url(url: str) -> Optional[str]:
        patterns = [
            r"/(\d{4})/(\d{2})/(\d{2})/",
            r"/(\d{4})-(\d{2})-(\d{2})/",
            r"/(\d{8})/",
            r"_(\d{4})(\d{2})(\d{2})_",
            r"-(\d{4})(\d{2})(\d{2})-",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                groups = match.groups()
                try:
                    if len(groups) == 3:
                        year, month, day = groups
                        date_obj = datetime(int(year), int(month), int(day))
                        return date_obj.strftime("%Y-%m-%d")
                    elif len(groups) == 1:
                        date_str = groups[0]
                        year, month, day = date_str[:4], date_str[4:6], date_str[6:8]
                        date_obj = datetime(int(year), int(month), int(day))
                        return date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None


class DuckDuckGoSearchEngine:
    def __init__(self, config):
        self.config = config
        self.date_extractor = DateExtractor()

    def build_queries(
        self,
        company_name: str,
        year: Optional[int] = None,
        start_date: Optional[str] = None,
    ) -> List[str]:
        if isinstance(start_date, datetime):
            start_date = start_date.strftime("%Y-%m-%d")
        if year is None:
            year = int(start_date.split("-")[0]) if start_date else datetime.now().year
        return [
            t.replace("{company}", company_name).replace("{year}", str(year))
            for t in self.config.SEARCH_QUERY_TEMPLATES
        ]

    def search_duckduckgo(
        self, company_name: str, max_results: int = 30, start_date: Optional[str] = None
    ) -> List[Dict]:
        print(f"🔍 Searching DuckDuckGo News for: {company_name}")
        results = []
        queries = self.build_queries(company_name, start_date=start_date)
        results_per_query = max(5, max_results // len(queries))

        try:
            with DDGS() as ddgs:
                for query in queries:
                    try:
                        search_results = ddgs.news(
                            query, max_results=results_per_query, region="tr-tr"
                        )
                        for result in search_results:
                            url = result.get("url", "")
                            published_date = result.get(
                                "date", ""
                            ) or self.date_extractor.extract_date_from_url(url)
                            results.append(
                                {
                                    "url": url,
                                    "title": result.get("title", ""),
                                    "snippet": result.get("body", ""),
                                    "source": "duckduckgo",
                                    "published_at": published_date or "",
                                }
                            )
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"  ⚠️ Query failed: {query[:50]}... - {e}")
                        continue

            dates_found = sum(1 for r in results if r.get("published_at"))
            print(f"  ✓ Found {len(results)} raw results from DuckDuckGo News")
            print(f"  📅 Extracted dates from {dates_found}/{len(results)} URLs")
            return results
        except Exception as e:
            print(f"  ✗ DuckDuckGo search failed: {e}")
            return []


class URLExtractor:
    def __init__(
        self,
        config: Optional[NewsFilterConfig] = None,
        similarity_threshold: float = 0.75,
    ):
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
        filtered_urls = []
        stats = {
            "total_found": len(raw_results),
            "blocked_domains": 0,
            "blocked_patterns": 0,
            "not_articles": 0,
            "duplicates": 0,
            "kept": 0,
        }
        print(f"  🔧 Filtering {source_name} results...")

        for result in raw_results:
            url, title = result["url"], result.get("title", "")

            if not self.validator.is_valid_article(url):
                if self.validator.is_blocked_domain(url):
                    stats["blocked_domains"] += 1
                elif self.validator.has_blocked_pattern(url):
                    stats["blocked_patterns"] += 1
                else:
                    stats["not_articles"] += 1
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
        self.id_counter = 0
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")

        print(f"\n{'='*60}\n📰 HYBRID URL EXTRACTION STARTED\n{'='*60}")
        print(f"Company: {company_name}\nDate Range: {start_date} to {end_date}")
        print(f"Language: {language}\nTarget: {target_count} unique articles")
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
                "duplicates": api_stats["duplicates"] + ddg_stats["duplicates"],
                "kept": api_stats["kept"] + ddg_stats["kept"],
            }
        else:
            print(
                f"\n✅ API provided sufficient results ({len(filtered_urls)} >= {api_threshold})"
            )
            print("📌 DuckDuckGo fallback not needed\n")
            combined_stats = api_stats

        filtered_urls.sort(key=lambda x: x["importance_score"], reverse=True)
        filtered_urls = filtered_urls[:target_count]

        print(f"\n{'='*60}\n📊 EXTRACTION STATISTICS\n{'='*60}")
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
        print(f"Duplicates removed:   {combined_stats['duplicates']}")
        print(f"Final count:          {len(filtered_urls)}")
        print(f"Priority sources:     {sum(1 for u in filtered_urls if u['priority'])}")

        # Check if no URLs found FIRST
        if not filtered_urls or len(filtered_urls) == 0:
            print(f"\n{'='*60}\n⚠️  NO ARTICLES FOUND\n{'='*60}")
            print(f"No news articles found for '{company_name}'")
            print(f"Date range: {start_date} to {end_date}")
            print(
                f"Try:\n  - Expanding the date range\n  - Using a different company name"
            )
            print(f"  - Checking if the company has been in the news\n{'='*60}\n")
            with open("extracted_urls.json", "w", encoding="utf-8") as f:
                json.dump([], f)
            return []

        # Calculate importance scores (only if we have results)
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
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(urls, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved to {filename}")


if __name__ == "__main__":
    extractor = URLExtractor(similarity_threshold=0.75)
    urls = extractor.extract_urls(
        company_name=COMPANY_NAME,
        start_date=START_DATE,
        end_date=END_DATE,
        target_count=50,
        language="tr",
        api_threshold=50,
    )

    print("📋 EXTRACTED URLS (sorted by importance):")
    print("=" * 60)
    for i, item in enumerate(urls, 1):
        priority_flag = "⭐" if item["priority"] else "  "
        source_indicator = "🌐" if item["source"] == "duckduckgo" else "📡"
        importance_bar = "█" * (item["importance_score"] // 10)
        print(
            f"{i:2d}. {priority_flag} {source_indicator} [{importance_bar:10s}] {item['importance_score']:3d}/100"
        )
        print(f"     {item['title'][:55]}\n     {item['url']}")
        print(
            f"     Source: {item['source']} | Published: {item.get('published_at', 'N/A')}"
        )
        print(f"     Domain Score: {item['domain_score']}\n")

    extractor.save_to_json(urls)
