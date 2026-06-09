from __future__ import annotations

import pytest

from runtime.skill_loader import SkillLoader
from runtime.tool_registry import ToolRegistry
from tools.safe_tools import ToolResult
from tools.web_tools import (
    BingResultParser,
    DuckDuckGoResultParser,
    WebTools,
    build_search_queries,
    extract_research_entity,
    filter_search_results,
    extract_page_text,
    is_pdf_response,
    quote_entity_phrase,
    score_search_result,
    to_english_search_query,
    unwrap_bing_url,
    unwrap_duckduckgo_url,
    validate_public_http_url,
)


def test_validate_public_http_url_rejects_private_targets() -> None:
    bad_urls = [
        "file:///etc/passwd",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://10.0.0.1",
        "http://192.168.1.10",
        "http://169.254.169.254/latest/meta-data",
    ]

    for url in bad_urls:
        with pytest.raises(ValueError):
            validate_public_http_url(url, resolve_dns=False)


def test_validate_public_http_url_accepts_public_https() -> None:
    assert validate_public_http_url("https://example.com/path#frag", resolve_dns=False) == "https://example.com/path"


def test_duckduckgo_parser_extracts_result_links() -> None:
    html = """
    <html>
      <body>
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs">Example Docs</a>
      </body>
    </html>
    """

    parser = DuckDuckGoResultParser(base_url="https://duckduckgo.com/html/?q=example")
    parser.feed(html)

    assert parser.results[0]["title"] == "Example Docs"
    assert unwrap_duckduckgo_url(parser.results[0]["url"]) == "https://example.com/docs"


def test_unwrap_bing_redirect_url() -> None:
    url = "https://www.bing.com/ck/a?!&&u=a1aHR0cHM6Ly93d3cuZXhhbXBsZS5jb20vZG9jcw&ntb=1"

    assert unwrap_bing_url(url) == "https://www.example.com/docs"


def test_bing_parser_extracts_result_links() -> None:
    html = """
    <html>
      <body>
        <li class="b_algo">
          <h2><a href="https://example.com/docs">Example Docs</a></h2>
          <p>Example documentation snippet.</p>
        </li>
      </body>
    </html>
    """

    parser = BingResultParser(base_url="https://www.bing.com/search")
    parser.feed(html)

    assert parser.results[0]["title"] == "Example Docs"
    assert parser.results[0]["url"] == "https://example.com/docs"
    assert parser.results[0]["snippet"] == "Example documentation snippet."


def test_tool_registry_includes_web_tools() -> None:
    names = ToolRegistry().names()

    assert "web_search" in names
    assert "fetch_url" in names
    assert "approved_source_fetch" in names


def test_approved_source_fetch_requires_prior_approved_url(monkeypatch: pytest.MonkeyPatch) -> None:
    tools = WebTools()

    def fake_fetch_url(*, url: str, max_bytes: int = 200_000, extract_text: bool = True) -> ToolResult:
        return ToolResult(True, {"url": url, "word_count": 120, "text": "verified source text"})

    monkeypatch.setattr(tools, "fetch_url", fake_fetch_url)

    rejected = tools.approved_source_fetch(
        url="https://unapproved.example.org/paper",
        approved_urls=["https://approved.example.org/paper"],
    )
    allowed = tools.approved_source_fetch(
        url="https://approved.example.org/paper",
        approved_urls=["https://approved.example.org/paper#section"],
    )

    assert rejected.ok is False
    assert "prior approved source URL" in rejected.error
    assert allowed.ok is True
    assert allowed.data["approved_source_fetch"] is True


def test_company_research_query_uses_exact_entity_first() -> None:
    assert extract_research_entity("分析药明康德") == "药明康德"
    assert build_search_queries("药明康德 公司 财报 新闻 业务 风险")[0] == "药明康德"


def test_web_tools_default_to_direct_non_english_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEB_PROXY_URL", raising=False)
    monkeypatch.delenv("WEB_PROXY_REQUIRED", raising=False)
    monkeypatch.delenv("WEB_SEARCH_ENGLISH_ONLY", raising=False)

    tools = WebTools()

    assert tools.proxy_url is None
    assert tools.proxy_required is False
    assert tools.english_only is False


def test_company_research_query_can_be_forced_to_english() -> None:
    query = to_english_search_query("分析药明康德")

    assert "WuXi AppTec" in query
    assert "分析" not in query
    assert build_search_queries("药明康德 公司 财报 新闻 业务 风险", english_only=True)[0].startswith('"WuXi AppTec"')
    assert to_english_search_query("五粮液") == "Wuliangye Yibin Co Ltd"
    assert to_english_search_query("Wuliangye liquor") == "Wuliangye Yibin Co Ltd baijiu"
    assert build_search_queries("Wuliangye liquor", english_only=True)[0] == '"Wuliangye Yibin Co Ltd" baijiu'


def test_quote_entity_phrase_quotes_multiword_entities() -> None:
    assert quote_entity_phrase("WuXi AppTec analysis business risks", "WuXi AppTec").startswith('"WuXi AppTec"')


def test_company_search_ranking_downranks_dictionary_results() -> None:
    official = {
        "title": "药明康德 | 官方网站",
        "url": "https://www.wuxiapptec.cn/",
        "snippet": "药明康德提供一体化药物研发和生产服务。",
    }
    dictionary = {
        "title": "药（汉语文字）_百度百科",
        "url": "https://baike.baidu.com/item/%E8%8D%AF/2361462",
        "snippet": "药，汉语常用字，释义为治病的物品。",
    }

    ranked = filter_search_results([dictionary, official], max_results=2, query="药明康德 公司 财报 新闻 业务 风险")

    assert ranked[0]["url"] == "https://www.wuxiapptec.cn/"
    assert score_search_result(official, "药明康德") > score_search_result(dictionary, "药明康德")


def test_english_only_filter_rejects_chinese_finance_sources() -> None:
    english = {
        "title": "WuXi AppTec annual report",
        "url": "https://www.wuxiapptec.com/investors",
        "snippet": "Annual report and investor relations information.",
    }
    chinese = {
        "title": "药明康德股票行情",
        "url": "https://quote.eastmoney.com/sh603259.html",
        "snippet": "东方财富网提供药明康德股票行情。",
    }

    ranked = filter_search_results([chinese, english], max_results=2, query="WuXi AppTec", english_only=True)

    assert ranked == [english]


def test_filter_search_results_removes_entity_mismatches() -> None:
    relevant = {
        "title": "WuXi AppTec annual report",
        "url": "https://www.wuxiapptec.com/investors",
        "snippet": "Financial reports for WuXi AppTec.",
    }
    city = {
        "title": "Top things to do in Wuxi",
        "url": "https://example.com/wuxi-travel",
        "snippet": "Travel guide for Wuxi city.",
    }

    ranked = filter_search_results([city, relevant], max_results=2, query='"WuXi AppTec" annual report', english_only=True)

    assert ranked == [relevant]


def test_extract_page_text_prefers_article_content_over_navigation() -> None:
    html = """
    <html>
      <head><title>Example Article</title><meta name="description" content="Short summary."></head>
      <body>
        <nav>Search Menu Login Markets Crypto Prices</nav>
        <article>
          <h1>WuXi AppTec annual report analysis</h1>
          <p>WuXi AppTec reported revenue growth from its CRDMO platform and described business risks.</p>
          <p>The company also highlighted customers across global pharmaceutical markets.</p>
        </article>
      </body>
    </html>
    """

    text = extract_page_text(html)

    assert "WuXi AppTec reported revenue growth" in text
    assert "Markets Crypto Prices" not in text


def test_pdf_response_detection() -> None:
    assert is_pdf_response("https://example.com/report.pdf", "application/octet-stream", b"")
    assert is_pdf_response("https://example.com/report", "application/pdf", b"")
    assert is_pdf_response("https://example.com/report", "application/octet-stream", b"%PDF-1.7")


def test_web_research_skill_matches_public_research_task() -> None:
    matches = SkillLoader("skills").match("Search the web for current LiteLLM Ollama documentation")

    assert "web-research" in [skill.name for skill in matches]
