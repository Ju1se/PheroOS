from __future__ import annotations

import html
import io
import ipaddress
import os
import re
import socket
import base64
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse, urlunparse

import httpx

from tools.safe_tools import ToolResult, clamp_int, truncate


MAX_FETCH_BYTES = 512_000
MAX_PAGE_TEXT_CHARS = 40_000
MAX_SEARCH_RESULTS = 8
USER_AGENT = "LocalAgentPlatform/0.1 (+https://localhost)"
DEFAULT_WEB_SEARCH_LANGUAGE = "en-US"
DEFAULT_WEB_SEARCH_COUNTRY = "us"
KNOWN_ENTITY_ENGLISH_ALIASES = {
    "药明康德": "WuXi AppTec",
    "五粮液": "Wuliangye Yibin Co Ltd",
    "贵州茅台": "Kweichow Moutai Co Ltd",
    "沪电股份": "WUS Printed Circuit Co Ltd",
}
KNOWN_ENGLISH_ENTITY_ALIASES = {
    "wuliangye": "Wuliangye Yibin Co Ltd",
    "wuxi apptec": "WuXi AppTec",
    "kweichow moutai": "Kweichow Moutai Co Ltd",
    "moutai": "Kweichow Moutai Co Ltd",
    "wus printed circuit": "WUS Printed Circuit Co Ltd",
}
QUERY_ENTITY_STOP_PHRASES = (
    "请帮我",
    "帮我",
    "帮忙",
    "一下",
    "分析",
    "研究",
    "调研",
    "查询",
    "搜索",
    "联网",
    "看看",
    "了解",
    "介绍",
    "总结",
    "报告",
    "全面",
    "深度",
    "最新",
    "近期",
    "当前",
    "现在",
    "公司",
    "企业",
    "股份",
    "股票",
    "股价",
    "财报",
    "年报",
    "季报",
    "公告",
    "新闻",
    "动态",
    "业务",
    "模式",
    "风险",
    "估值",
    "行业",
    "竞争",
    "优势",
    "劣势",
    "基本面",
    "港股",
    "a股",
    "美股",
    "上市",
    "数据",
)
ENGLISH_ENTITY_STOP_WORDS = {
    "analysis",
    "annual",
    "business",
    "company",
    "current",
    "filing",
    "filings",
    "financial",
    "investor",
    "latest",
    "news",
    "official",
    "report",
    "reports",
    "relations",
    "results",
    "research",
    "risk",
    "risks",
    "stock",
    "summary",
}
LOW_QUALITY_SEARCH_DOMAINS = (
    "zdic.net",
    "hancibao.com",
    "cidian",
    "zidian",
    "hanzi",
)
LOW_QUALITY_RESULT_HINTS = (
    "汉语",
    "汉字",
    "词典",
    "字典",
    "新华字典",
    "造句",
    "拼音",
    "释义",
    "什么意思",
    "药字",
)
NON_PRODUCTION_HOST_HINTS = (
    "test-",
    ".test.",
    "staging",
    "uat",
    "dev-",
)
PRIMARY_SOURCE_HINTS = (
    "官网",
    "官方网站",
    "official",
    "investor relations",
    "投资者关系",
    "annual report",
    "年报",
    "财报",
    "公告",
    "sse.com.cn",
    "hkexnews.hk",
    "wuxiapptec",
)
FINANCE_SOURCE_HINTS = (
    "eastmoney.com",
    "xueqiu.com",
    "finance",
    "stock",
    "quote",
    "证券",
    "财经",
)
HIGH_AUTHORITY_SOURCE_DOMAINS = (
    "wuxiapptec.com",
    "officialsite-static.wuxiapptec.com",
    "annualreports.com",
    "hkexnews.hk",
    "prnewswire.com",
    "globenewswire.com",
    "reuters.com",
    "sec.gov",
    "marketscreener.com",
    "biospace.com",
)
LOW_VALUE_SOURCE_DOMAINS = (
    "finance.yahoo.com",
    "markets.businessinsider.com",
    "linkedin.com",
    "crunchbase.com",
    "owler.com",
    "wikipedia.org",
    "matrixbcg.com",
    "businessmodelcanvastemplate.com",
    "quaintel.com",
)
CHINESE_SOURCE_DOMAINS = (
    ".cn",
    ".com.cn",
    "baidu.com",
    "eastmoney.com",
    "sina.com.cn",
    "xueqiu.com",
    "10jqka.com.cn",
    "hexun.com",
    "sohu.com",
    "163.com",
    "qq.com",
)


class WebTools:
    def __init__(
        self,
        *,
        timeout_seconds: float = 12.0,
        proxy_url: str | None = None,
        proxy_required: bool | None = None,
        english_only: bool | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.proxy_url = normalize_proxy_url(proxy_url or os.getenv("WEB_PROXY_URL"))
        self.proxy_required = parse_bool(os.getenv("WEB_PROXY_REQUIRED"), default=False) if proxy_required is None else proxy_required
        self.english_only = parse_bool(os.getenv("WEB_SEARCH_ENGLISH_ONLY"), default=False) if english_only is None else english_only

    def fetch_url(
        self,
        *,
        url: str,
        max_bytes: int = 200_000,
        extract_text: bool = True,
    ) -> ToolResult:
        if self.proxy_required and not self.proxy_url:
            return ToolResult(False, {"url": url}, "WEB_PROXY_URL must be configured when WEB_PROXY_REQUIRED is true")
        try:
            safe_url = validate_public_http_url(url, resolve_dns=True)
            max_bytes = clamp_int(max_bytes, minimum=1_000, maximum=MAX_FETCH_BYTES)
            response, raw, truncated = self._get_limited(safe_url, max_bytes=max_bytes)
            final_url = validate_public_http_url(str(response.url), resolve_dns=True)
        except ValueError as exc:
            return ToolResult(False, {"url": url}, str(exc))
        except httpx.HTTPError as exc:
            return ToolResult(False, {"url": url}, f"request failed: {exc}")

        content_type = response.headers.get("content-type", "")
        if is_pdf_response(final_url, content_type, raw):
            title = filename_from_url(final_url)
            page_text = extract_pdf_text(raw) if extract_text else ""
        else:
            text = decode_response_text(raw, response.encoding)
            title = extract_title(text) if "html" in content_type.lower() else ""
            page_text = extract_page_text(text) if extract_text and "html" in content_type.lower() else text
        quality = assess_text_quality(page_text)

        return ToolResult(
            True,
            {
                "url": final_url,
                "status_code": response.status_code,
                "content_type": content_type,
                "title": title,
                "text": truncate(page_text[:MAX_PAGE_TEXT_CHARS]),
                "word_count": quality["word_count"],
                "text_quality": quality["quality"],
                "bytes": len(raw),
                "truncated": truncated,
            },
        )

    def approved_source_fetch(
        self,
        *,
        url: str,
        approved_urls: list[str] | None = None,
        max_bytes: int = 200_000,
        extract_text: bool = True,
    ) -> ToolResult:
        """Fetch only URLs that were already approved by a prior source tool.

        This is the low-risk evidence recovery path used by PheroOS. It keeps
        arbitrary network access disabled while allowing full-text verification
        for URLs returned by provider-native search or another approved source.
        """

        approved = {normalize_url_for_approval(item) for item in approved_urls or [] if str(item or "").strip()}
        requested = normalize_url_for_approval(url)
        if not requested or requested not in approved:
            return ToolResult(
                False,
                {"url": url, "approved_url_count": len(approved)},
                "approved_source_fetch requires url to match a prior approved source URL",
            )
        result = self.fetch_url(url=url, max_bytes=max_bytes, extract_text=extract_text)
        if not result.ok:
            return result
        return ToolResult(True, {**result.data, "approved_source_fetch": True, "source_approval": "provider_search_result"})

    def web_search(
        self,
        *,
        query: str,
        max_results: int = 5,
    ) -> ToolResult:
        if not isinstance(query, str) or not query.strip():
            return ToolResult(False, {"query": query}, "query must be a non-empty string")
        if self.proxy_required and not self.proxy_url:
            return ToolResult(False, {"query": query}, "WEB_PROXY_URL must be configured when WEB_PROXY_REQUIRED is true")

        max_results = clamp_int(max_results, minimum=1, maximum=MAX_SEARCH_RESULTS)
        original_query = query.strip()
        errors = []
        query_variants = build_search_queries(original_query, english_only=self.english_only)
        collected: list[dict[str, str]] = []
        collected_urls: set[str] = set()
        searched_queries: list[str] = []
        selected_engine = ""
        for search_query in query_variants:
            for engine, search_url, parser in search_engines(search_query):
                try:
                    response, raw, _ = self._get_limited(search_url, max_bytes=300_000)
                except httpx.HTTPError as exc:
                    errors.append(f"{engine}: {exc}")
                    continue

                text = decode_response_text(raw, response.encoding)
                parser.feed(text)
                results = filter_search_results(
                    parser.results,
                    max_results=max_results,
                    query=search_query,
                    english_only=self.english_only,
                )
                if not results:
                    continue

                if not selected_engine:
                    selected_engine = engine
                searched_queries.append(search_query)
                for result in results:
                    if result["url"] in collected_urls:
                        continue
                    collected.append(result)
                    collected_urls.add(result["url"])
                if len(collected) >= max_results:
                    payload = build_search_payload(
                        original_query=original_query,
                        searched_query=search_query,
                        query_variants=query_variants,
                        searched_queries=searched_queries,
                        engine=selected_engine,
                        results=rank_search_results(collected, query=query_variants[0])[:max_results],
                        english_only=self.english_only,
                        proxy_url=self.proxy_url,
                    )
                    return ToolResult(True, payload)
                break

        if collected:
            ranked_results = rank_search_results(collected, query=query_variants[0])[:max_results]
            payload = build_search_payload(
                original_query=original_query,
                searched_query=searched_queries[0] if searched_queries else query_variants[0],
                query_variants=query_variants,
                searched_queries=searched_queries,
                engine=selected_engine,
                results=ranked_results,
                english_only=self.english_only,
                proxy_url=self.proxy_url,
            )
            if search_results_are_relevant(ranked_results, query_variants[0]):
                return ToolResult(True, payload)
            return ToolResult(False, payload, "search results did not match the requested entity well enough")

        error = "; ".join(errors) if errors else "no search results found"
        return ToolResult(False, {"query": original_query, "engines": ["bing", "duckduckgo"]}, error)

    def _get_limited(self, url: str, *, max_bytes: int) -> tuple[httpx.Response, bytes, bool]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.8",
        }
        chunks = []
        total = 0
        truncated = False
        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            max_redirects=5,
            trust_env=False,
            headers=headers,
            proxy=self.proxy_url,
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        keep = max_bytes - sum(len(item) for item in chunks)
                        if keep > 0:
                            chunks.append(chunk[:keep])
                        truncated = True
                        break
                    chunks.append(chunk)
                return response, b"".join(chunks), truncated


@dataclass
class SearchResultDraft:
    url: str
    title_parts: list[str]
    snippet_parts: list[str]


class DuckDuckGoResultParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.results: list[dict[str, str]] = []
        self._current: SearchResultDraft | None = None
        self._capture_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        class_name = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in class_name:
            href = attrs_dict.get("href", "")
            self._current = SearchResultDraft(
                url=urljoin(self.base_url, href),
                title_parts=[],
                snippet_parts=[],
            )
        elif self._current and tag in {"a", "span"} and "result__snippet" in class_name:
            self._capture_snippet = True

    def handle_data(self, data: str) -> None:
        if not self._current:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._capture_snippet:
            self._current.snippet_parts.append(cleaned)
        else:
            self._current.title_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if self._current and tag == "a":
            title = html.unescape(" ".join(self._current.title_parts)).strip()
            if title and self._current.url:
                self.results.append(
                    {
                        "title": title,
                        "url": self._current.url,
                        "snippet": html.unescape(" ".join(self._current.snippet_parts)).strip(),
                    }
                )
            self._current = None
            self._capture_snippet = False
        elif self._capture_snippet and tag in {"a", "span"}:
            self._capture_snippet = False


class BingResultParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.results: list[dict[str, str]] = []
        self._current: dict[str, Any] | None = None
        self._in_title_link = False
        self._capture_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        class_name = attrs_dict.get("class", "")
        if tag == "li" and "b_algo" in class_name:
            self._current = {"url": "", "title_parts": [], "snippet_parts": []}
        elif self._current is not None and tag == "a" and not self._current["url"]:
            href = attrs_dict.get("href", "")
            if href.startswith("http"):
                self._current["url"] = urljoin(self.base_url, href)
                self._in_title_link = True
        elif self._current is not None and tag == "p":
            self._capture_snippet = True

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title_link:
            self._current["title_parts"].append(cleaned)
        elif self._capture_snippet:
            self._current["snippet_parts"].append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a" and self._in_title_link:
            self._in_title_link = False
        elif tag == "p" and self._capture_snippet:
            self._capture_snippet = False
        elif tag == "li":
            title = html.unescape(" ".join(self._current["title_parts"])).strip()
            url = self._current["url"]
            if title and url:
                self.results.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": html.unescape(" ".join(self._current["snippet_parts"])).strip(),
                    }
                )
            self._current = None
            self._in_title_link = False
            self._capture_snippet = False


def validate_public_http_url(url: str, *, resolve_dns: bool) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http and https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("url host is required")

    host = parsed.hostname.rstrip(".").lower()
    if is_blocked_hostname(host):
        raise ValueError("localhost and internal hosts are not allowed")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and not ip.is_global:
        raise ValueError("private, loopback, reserved, and link-local IPs are not allowed")

    if resolve_dns and ip is None:
        for resolved_ip in resolve_host(host):
            if not resolved_ip.is_global:
                raise ValueError("host resolves to a private, loopback, reserved, or link-local IP")

    normalized = parsed._replace(fragment="")
    return urlunparse(normalized)


def search_engines(query: str) -> list[tuple[str, str, HTMLParser]]:
    encoded = quote_plus(query)
    language = os.getenv("WEB_SEARCH_LANGUAGE", DEFAULT_WEB_SEARCH_LANGUAGE)
    country = os.getenv("WEB_SEARCH_COUNTRY", DEFAULT_WEB_SEARCH_COUNTRY)
    return [
        (
            "bing",
            f"https://www.bing.com/search?q={encoded}&setlang={quote_plus(language)}&cc={quote_plus(country)}&mkt=en-US",
            BingResultParser(base_url="https://www.bing.com/search"),
        ),
        (
            "duckduckgo",
            f"https://duckduckgo.com/html/?q={encoded}&kl=us-en",
            DuckDuckGoResultParser(base_url="https://duckduckgo.com/html/"),
        ),
    ]


def build_search_queries(query: str, *, english_only: bool = False) -> list[str]:
    normalized = normalize_query(query)
    if english_only:
        normalized = to_english_search_query(normalized)
    entity = known_english_entity_for_query(normalized) or extract_research_entity(normalized)
    variants = []
    if english_only and entity and entity != normalized:
        exact_normalized = quote_entity_phrase(normalized, entity)
        variants.append(exact_normalized)
        variants.extend(
            [
                f'"{entity}" annual report investor relations',
                f'"{entity}" official financial reports',
                f'"{entity}" filings',
                entity,
            ]
        )
        return unique_non_empty(variants)

    if entity and entity != normalized:
        variants.append(entity)
        if has_cjk(entity):
            variants.extend([f"{entity} 官网", f"{entity} 年报 财报"])
        else:
            variants.extend([f"{entity} official", f"{entity} annual report"])
    variants.append(normalized)
    return unique_non_empty(variants)


def to_english_search_query(query: str) -> str:
    normalized = normalize_query(query)
    if not has_cjk(normalized):
        return normalize_known_english_entity_query(normalized)

    entity = extract_research_entity(normalized)
    alias = KNOWN_ENTITY_ENGLISH_ALIASES.get(entity or "")
    if not alias:
        for chinese_name, english_name in KNOWN_ENTITY_ENGLISH_ALIASES.items():
            if chinese_name in normalized:
                alias = english_name
                break

    terms = []
    if any(word in normalized for word in ("分析", "研究", "调研", "报告", "业务", "风险")):
        terms.extend(["analysis", "business", "risks"])
    if any(word in normalized for word in ("财报", "年报", "季报", "公告", "股票", "股价", "估值")):
        terms.extend(["financial results", "annual report", "filings"])
    if any(word in normalized for word in ("新闻", "动态", "近期", "最新", "当前")):
        terms.extend(["latest news"])
    if any(word in normalized for word in ("官网", "官方")):
        terms.extend(["official", "investor relations"])

    if alias:
        return unique_non_empty([alias, *terms])[0] if not terms else " ".join(unique_non_empty([alias, *terms]))

    ascii_tokens = [token for token in re.findall(r"[A-Za-z][A-Za-z0-9&.-]*", normalized) if token.lower() not in ENGLISH_ENTITY_STOP_WORDS]
    if ascii_tokens:
        return " ".join(unique_non_empty([*ascii_tokens, *terms]))
    return " ".join(unique_non_empty(terms)) or normalized


def normalize_known_english_entity_query(query: str) -> str:
    normalized = normalize_query(query)
    lowered = normalized.lower()
    for marker, canonical in KNOWN_ENGLISH_ENTITY_ALIASES.items():
        if marker not in lowered:
            continue
        suffix_terms = []
        for term in (
            "annual report",
            "financial results",
            "filings",
            "investor relations",
            "latest news",
            "business",
            "risks",
            "baijiu",
        ):
            if term in lowered:
                suffix_terms.append(term)
        if "liquor" in lowered and "baijiu" not in suffix_terms:
            suffix_terms.append("baijiu")
        return " ".join(unique_non_empty([canonical, *suffix_terms]))
    return normalized


def known_english_entity_for_query(query: str) -> str | None:
    lowered = normalize_query(query).lower()
    for marker, canonical in KNOWN_ENGLISH_ENTITY_ALIASES.items():
        if marker in lowered:
            return canonical
    return None


def quote_entity_phrase(query: str, entity: str) -> str:
    if not entity or " " not in entity or f'"{entity}"' in query:
        return query
    return re.sub(re.escape(entity), f'"{entity}"', query, count=1, flags=re.IGNORECASE)


def extract_research_entity(query: str) -> str | None:
    cleaned = normalize_query(query)
    if not cleaned:
        return None
    for phrase in sorted(QUERY_ENTITY_STOP_PHRASES, key=len, reverse=True):
        cleaned = re.sub(re.escape(phrase), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"""["'“”‘’（）()：:，,。.;；!?？/\\|]+""", " ", cleaned)
    cleaned = normalize_query(cleaned)
    if not cleaned:
        return None

    for candidate in re.findall(r"[\u4e00-\u9fff]{2,20}", cleaned):
        if candidate not in QUERY_ENTITY_STOP_PHRASES:
            return candidate

    tokens = [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9&.-]*", cleaned)
        if token.lower() not in ENGLISH_ENTITY_STOP_WORDS
    ]
    if len(tokens) >= 2:
        return " ".join(tokens[:3])
    if len(tokens) == 1:
        return tokens[0]
    return None


def filter_search_results(
    results: list[dict[str, str]],
    *,
    max_results: int,
    query: str | None = None,
    english_only: bool = False,
) -> list[dict[str, str]]:
    candidates = []
    seen = set()
    entity = extract_research_entity(query or "") if query else None
    for index, result in enumerate(results):
        url = unwrap_search_url(result["url"])
        try:
            safe_url = validate_public_http_url(url, resolve_dns=False)
        except ValueError:
            continue
        if safe_url in seen:
            continue
        seen.add(safe_url)
        payload = {
            "title": result["title"],
            "url": safe_url,
            "snippet": result.get("snippet", ""),
        }
        if english_only and not is_english_source_result(payload):
            continue
        score = score_search_result(payload, query or "")
        if entity and score < 8:
            continue
        candidates.append((score, index, payload))

    if query:
        candidates.sort(key=lambda item: (-item[0], item[1]))
    return [payload for _, _, payload in candidates[:max_results]]


def rank_search_results(results: list[dict[str, str]], *, query: str) -> list[dict[str, str]]:
    return [
        item
        for _, _, item in sorted(
            ((score_search_result(item, query), -index, item) for index, item in enumerate(results)),
            reverse=True,
        )
    ]


def build_search_payload(
    *,
    original_query: str,
    searched_query: str,
    query_variants: list[str],
    searched_queries: list[str],
    engine: str,
    results: list[dict[str, str]],
    english_only: bool,
    proxy_url: str | None,
) -> dict[str, Any]:
    return {
        "query": original_query,
        "searched_query": searched_query,
        "searched_queries": searched_queries,
        "query_variants": query_variants,
        "engine": engine,
        "english_only": english_only,
        "proxy_url": redact_proxy_url(proxy_url),
        "results": results,
    }


def score_search_result(result: dict[str, str], query: str) -> int:
    title = str(result.get("title") or "")
    url = str(result.get("url") or "")
    snippet = str(result.get("snippet") or "")
    haystack = f"{title} {url} {snippet}"
    host = urlparse(url).netloc.lower()
    normalized_haystack = normalize_for_match(haystack)
    entity = extract_research_entity(query) or normalize_query(query)
    normalized_entity = normalize_for_match(entity)

    score = 0
    entity_matched = bool(normalized_entity and normalized_entity in normalized_haystack)
    if entity_matched:
        score += 20
    if any(hint in normalized_haystack for hint in PRIMARY_SOURCE_HINTS):
        score += 6
    if any(hint in normalized_haystack for hint in FINANCE_SOURCE_HINTS):
        score += 4
    if any(host == domain or host.endswith(f".{domain}") for domain in HIGH_AUTHORITY_SOURCE_DOMAINS):
        score += 10
    if any(host == domain or host.endswith(f".{domain}") for domain in LOW_VALUE_SOURCE_DOMAINS):
        score -= 8
    if any(term in normalized_haystack for term in ("annualreport", "investorrelations", "financialreports", "filings")):
        score += 8
    if any(term in normalized_haystack for term in ("stockquote", "/quote/", "markets/stocks", "stockprice")):
        score -= 10
    if any(term in normalized_haystack for term in ("pestleanalysis", "swot", "template", "companyprofile")):
        score -= 8
    if looks_non_production_result(result):
        score -= 12
    if is_chinese_source_domain(url):
        score -= 15
    if looks_low_quality_result(result, entity_matched=entity_matched):
        score -= 20
    return score


def search_results_are_relevant(results: list[dict[str, str]], query: str) -> bool:
    entity = extract_research_entity(query)
    if not entity:
        return True
    scores = [score_search_result(result, query) for result in results]
    return bool(scores and max(scores) >= 8)


def looks_low_quality_result(result: dict[str, str], *, entity_matched: bool) -> bool:
    if entity_matched:
        return False
    parsed = urlparse(str(result.get("url") or ""))
    domain = parsed.netloc.lower()
    haystack = normalize_for_match(
        f"{result.get('title') or ''} {result.get('url') or ''} {result.get('snippet') or ''}"
    )
    return any(domain.endswith(domain_hint) for domain_hint in LOW_QUALITY_SEARCH_DOMAINS) or any(
        hint in haystack for hint in LOW_QUALITY_RESULT_HINTS
    )


def looks_non_production_result(result: dict[str, str]) -> bool:
    parsed = urlparse(str(result.get("url") or ""))
    host = parsed.netloc.lower()
    return any(hint in host for hint in NON_PRODUCTION_HOST_HINTS)


def is_english_source_result(result: dict[str, str]) -> bool:
    url = str(result.get("url") or "")
    if is_chinese_source_domain(url):
        return False
    text = f"{result.get('title') or ''} {result.get('snippet') or ''}"
    return cjk_ratio(text) <= 0.08


def is_chinese_source_domain(url: str) -> bool:
    host = urlparse(str(url or "")).netloc.lower()
    return any(host == domain.lstrip(".") or host.endswith(domain) for domain in CHINESE_SOURCE_DOMAINS)


def cjk_ratio(text: str) -> float:
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return 0.0
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", compact))
    return cjk_count / len(compact)


def normalize_query(query: str) -> str:
    return " ".join(str(query or "").split()).strip()


def normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", unquote(html.unescape(str(text or ""))).lower())


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def unique_non_empty(values: list[str]) -> list[str]:
    unique = []
    seen = set()
    for value in values:
        normalized = normalize_query(value)
        key = normalized.lower()
        if normalized and key not in seen:
            unique.append(normalized)
            seen.add(key)
    return unique


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_proxy_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname:
        raise ValueError("WEB_PROXY_URL must be an http, https, socks5, or socks5h proxy URL")
    return urlunparse(parsed._replace(fragment=""))


def redact_proxy_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.username or parsed.password:
        parsed = parsed._replace(netloc=f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname or "")
    return urlunparse(parsed)


def is_blocked_hostname(host: str) -> bool:
    return host in {"localhost", "local"} or host.endswith(".localhost") or host.endswith(".local")


def resolve_host(host: str) -> list[ipaddress._BaseAddress]:
    try:
        records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve host: {host}") from exc

    addresses = []
    for record in records:
        address = record[4][0]
        try:
            addresses.append(ipaddress.ip_address(address))
        except ValueError:
            continue
    if not addresses:
        raise ValueError(f"could not resolve host: {host}")
    return addresses


def unwrap_search_url(url: str) -> str:
    return unwrap_bing_url(unwrap_duckduckgo_url(url))


def unwrap_bing_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/"):
        target = parse_qs(parsed.query).get("u", [""])[0]
        decoded = decode_bing_target(target)
        if decoded:
            return decoded
    return url


def decode_bing_target(value: str) -> str | None:
    if not value:
        return None
    candidate = value[2:] if value.startswith("a1") else value
    padding = "=" * (-len(candidate) % 4)
    try:
        decoded = base64.urlsafe_b64decode(candidate + padding).decode("utf-8", errors="replace")
    except ValueError:
        return None
    return decoded if decoded.startswith(("http://", "https://")) else None


def unwrap_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return uddg[0]
    return url


def decode_response_text(raw: bytes, encoding: str | None) -> str:
    return raw.decode(encoding or "utf-8", errors="replace")


def extract_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return html.unescape(" ".join(match.group(1).split()))


def extract_page_text(text: str) -> str:
    candidates: list[tuple[int, str]] = []
    for pattern in (
        r"(?is)<article\b[^>]*>.*?</article>",
        r"(?is)<main\b[^>]*>.*?</main>",
        r"""(?is)<(?:div|section)\b[^>]*(?:class|id)=["'][^"']*(?:article|story|body|content|press|release|news|main)[^"']*["'][^>]*>.*?</(?:div|section)>""",
    ):
        for match in re.finditer(pattern, text):
            candidate = extract_visible_text(match.group(0))
            score = text_candidate_score(candidate)
            if score > 0:
                candidates.append((score, candidate))

    full_text = extract_visible_text(text)
    candidates.append((text_candidate_score(full_text) - 25, full_text))
    best = max(candidates, key=lambda item: item[0])[1] if candidates else full_text

    title = extract_title(text)
    description = extract_meta_description(text)
    return join_unique_text_parts([title, description, best])


def is_pdf_response(url: str, content_type: str, raw: bytes) -> bool:
    return (
        "pdf" in content_type.lower()
        or urlparse(url).path.lower().endswith(".pdf")
        or raw.startswith(b"%PDF")
    )


def filename_from_url(url: str) -> str:
    filename = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return filename or "PDF document"


def extract_pdf_text(raw: bytes, *, max_pages: int = 20) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "PDF text extraction requires the pypdf package."

    reader = PdfReader(io.BytesIO(raw))
    chunks = []
    for page in reader.pages[:max_pages]:
        text = page.extract_text() or ""
        cleaned = "\n".join(clean_visible_lines(text))
        if cleaned:
            chunks.append(cleaned)
    return "\n\n".join(chunks).strip()


def extract_visible_text(text: str) -> str:
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<(script|style|noscript|svg|canvas|template)\b[^>]*>.*?(?:</\1>|$)", " ", text)
    text = re.sub(
        r"(?is)</?(?:p|div|section|article|main|header|footer|nav|aside|br|li|ul|ol|h[1-6]|tr|table|blockquote)\b[^>]*>",
        "\n",
        text,
    )
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return "\n".join(clean_visible_lines(text)).strip()


def clean_visible_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line or is_boilerplate_line(line):
            continue
        lines.append(line)
    return lines


def is_boilerplate_line(line: str) -> bool:
    lowered = line.lower()
    if len(line) <= 2:
        return True
    if re.search(r"[{};][a-z-]+:", lowered):
        return True
    return lowered in {
        "skip to navigation",
        "skip to main content",
        "skip to right column",
        "accessibility statement",
        "client login",
        "search",
        "no results found.",
        "oops, something went wrong",
    }


def extract_meta_description(text: str) -> str:
    match = re.search(
        r"""(?is)<meta\b(?=[^>]*(?:name|property)=["'](?:description|og:description)["'])[^>]*content=["']([^"']+)["'][^>]*>""",
        text,
    )
    return html.unescape(" ".join(match.group(1).split())) if match else ""


def text_candidate_score(text: str) -> int:
    quality = assess_text_quality(text)
    return quality["word_count"] + min(len(re.findall(r"[.!?]\s|。|！|？", text)) * 8, 80)


def assess_text_quality(text: str) -> dict[str, int | str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'&.-]*", text)
    word_count = len(words)
    lowered = text.lower()
    quality = "good"
    if word_count < 120:
        quality = "short"
    if "oops, something went wrong" in lowered or "enable javascript" in lowered:
        quality = "poor"
    return {"word_count": word_count, "quality": quality}


def join_unique_text_parts(parts: list[str]) -> str:
    output = []
    seen = set()
    for part in parts:
        cleaned = "\n".join(clean_visible_lines(part))
        key = normalize_for_match(cleaned)
        if cleaned and key not in seen:
            output.append(cleaned)
            seen.add(key)
    return "\n\n".join(output)


def normalize_url_for_approval(value: Any) -> str:
    try:
        safe = validate_public_http_url(str(value or ""), resolve_dns=False)
    except ValueError:
        return ""
    parsed = urlparse(safe)
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))
