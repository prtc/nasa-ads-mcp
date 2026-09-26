"""Tests for the NASA ADS MCP server, using simulated ADS responses (no network, no token)."""

import json

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from nasa_ads_mcp import server


class FakeADS:
    """Records requests and answers them from a handler function."""

    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


@pytest.fixture
def ads(monkeypatch):
    """Install a fake ADS; call it with a handler to set the responses."""
    monkeypatch.setenv("ADS_API_TOKEN", "test-token")

    def install(handler):
        fake = FakeADS(handler)
        monkeypatch.setattr(server, "_transport", httpx.MockTransport(fake))
        return fake

    return install


def search_response(docs, num_found=None):
    return httpx.Response(
        200, json={"response": {"numFound": num_found or len(docs), "docs": docs}}
    )


def text_of(result):
    return result[0].text


# --- token and errors ---------------------------------------------------------

async def test_missing_token_gives_helpful_error(monkeypatch):
    monkeypatch.delenv("ADS_API_TOKEN", raising=False)
    with pytest.raises(server.ADSError, match="ADS_API_TOKEN is not set"):
        await server.search_papers("stellar populations")


async def test_token_is_sent_as_bearer(ads):
    fake = ads(lambda r: search_response([]))
    await server.search_papers("x")
    assert fake.requests[0].headers["Authorization"] == "Bearer test-token"


async def test_invalid_token_error(ads):
    ads(lambda r: httpx.Response(401, json={"error": "Unauthorized"}))
    with pytest.raises(server.ADSError, match="rejected the API token"):
        await server.search_papers("x")


async def test_rate_limit_error(ads):
    ads(lambda r: httpx.Response(429, headers={"X-RateLimit-Reset": "1790000000"}))
    with pytest.raises(server.ADSError, match="rate limit.*1790000000"):
        await server.search_papers("x")


# --- search ------------------------------------------------------------------

async def test_search_papers_request_and_format(ads):
    docs = [{
        "bibcode": "2005A&A...443..735C",
        "title": ["A library of high resolution synthetic stellar spectra"],
        "author": ["Coelho, P.", "Barbuy, B.", "Meléndez, J.", "Schiavon, R. P."],
        "year": "2005",
        "citation_count": 300,
    }]
    fake = ads(lambda r: search_response(docs, num_found=42))
    text = text_of(await server.search_papers("stellar spectra", max_results=500, sort="relevance"))

    params = fake.requests[0].url.params
    assert fake.requests[0].url.path == "/v1/search/query"
    assert params["q"] == "stellar spectra"
    assert params["rows"] == "50"  # clamped to the maximum
    assert params["sort"] == "score desc"
    assert "Found 42 papers" in text and "showing 1" in text
    assert "et al. (4 authors)" in text
    assert "2005A&A...443..735C" in text


async def test_search_papers_no_results(ads):
    ads(lambda r: search_response([]))
    assert "No papers found" in text_of(await server.search_papers("nothing"))


async def test_paper_details_not_found(ads):
    ads(lambda r: search_response([]))
    assert "Paper not found" in text_of(await server.get_paper_details("2099XXX...1....1X"))


async def test_author_papers_query(ads):
    fake = ads(lambda r: search_response([{"bibcode": "b1", "title": ["T"], "year": "2020", "citation_count": 5}]))
    text = text_of(await server.get_author_papers("Coelho, P.", sort="citation_count"))
    assert fake.requests[0].url.params["q"] == 'author:"Coelho, P."'
    assert fake.requests[0].url.params["sort"] == "citation_count desc"
    assert "citations of papers shown: 5" in text


# --- BibTeX --------------------------------------------------------------------

async def test_export_bibtex_uses_ads_export_service(ads):
    ads_bibtex = (
        "@ARTICLE{2005A&A...443..735C,\n"
        "       author = {{Coelho}, P. and {Barbuy}, B.},\n"
        "       volume = {443},\n"
        "        pages = {735-746},\n"
        "          doi = {10.1051/0004-6361:20053511},\n"
        "}\n"
    )
    fake = ads(lambda r: httpx.Response(200, json={"msg": "Retrieved 1 abstracts", "export": ads_bibtex}))
    text = text_of(await server.export_bibtex(["2005A&A...443..735C", "2099XXX...1....1X"]))

    request = fake.requests[0]
    assert request.method == "POST" and request.url.path == "/v1/export/bibtex"
    assert json.loads(request.content) == {"bibcode": ["2005A&A...443..735C", "2099XXX...1....1X"]}
    assert "volume = {443}" in text and "doi = " in text
    assert "Not found in ADS: 2099XXX...1....1X" in text


# --- metrics -------------------------------------------------------------------

METRICS = {
    "basic stats": {
        "number of papers": 2,
        "total number of reads": 1234,
        "average number of reads": 617.0,
        "median number of reads": 617.0,
        "recent number of reads": 56,
    },
    "citation stats": {
        "total number of citations": 400,
        "total number of refereed citations": 380,
        "number of self-citations": 20,
        "average number of citations": 200.0,
        "median number of citations": 200.0,
        "normalized number of citations": 150.5,
    },
    "indicators": {"h": 2, "m": None, "i10": 2, "i100": 2, "g": 2, "tori": 12.3, "riq": 100},
    "skipped bibcodes": ["2099XXX...1....1X"],
}


async def test_paper_metrics_reads_come_from_basic_stats(ads):
    ads(lambda r: httpx.Response(200, json=METRICS))
    text = text_of(await server.get_paper_metrics(["a", "b", "2099XXX...1....1X"]))
    assert "Total Reads: 1234" in text  # was always 0 in v0.1: read from the wrong section
    assert "Recent Reads (last 90 days): 56" in text
    assert "m-index: n/a" in text  # a null metric no longer crashes the formatting
    assert "Skipped (not found in ADS): 2099XXX...1....1X" in text


async def test_author_metrics_notes_truncation(ads):
    def handler(request):
        if request.url.path == "/v1/search/query":
            return search_response([{"bibcode": "a"}, {"bibcode": "b"}], num_found=2500)
        return httpx.Response(200, json=METRICS)

    fake = ads(handler)
    text = text_of(await server.get_author_metrics("Coelho, P.", years="2020-2025"))
    assert fake.requests[0].url.params["q"] == 'author:"Coelho, P." year:2020-2025'
    assert json.loads(fake.requests[1].content) == {"bibcodes": ["a", "b"]}
    assert "ADS found 2500 papers" in text
    assert "h-index: 2" in text


# --- libraries -----------------------------------------------------------------

async def test_library_papers_reads_every_page_in_order(ads):
    library = [f"2020Lib..{i:04d}" for i in range(230)]

    def handler(request):
        if request.url.path.startswith("/v1/biblib/libraries/"):
            start = int(request.url.params["start"])
            rows = int(request.url.params["rows"])
            return httpx.Response(200, json={
                "documents": library[start:start + rows],
                "metadata": {"name": "Stellar Spectral Libraries", "num_documents": len(library)},
            })
        # search: answer for every bibcode requested, in reverse order to test re-ordering
        q = request.url.params["q"]
        found = [b for b in library if f'"{b}"' in q]
        return search_response([{"bibcode": b, "title": [f"Paper {b}"], "year": "2020"} for b in reversed(found)])

    fake = ads(handler)
    text = text_of(await server.get_library_papers("lib123"))

    biblib_calls = [r for r in fake.requests if "biblib" in r.url.path]
    search_calls = [r for r in fake.requests if "search" in r.url.path]
    assert len(biblib_calls) == 3  # 100 + 100 + 30
    assert len(search_calls) == 5  # chunks of 50
    assert "'Stellar Spectral Libraries' (230 papers)" in text
    assert "230. Paper 2020Lib..0229" in text
    assert text.index("Paper 2020Lib..0000") < text.index("Paper 2020Lib..0001")


async def test_add_to_library_reports_what_ads_added(ads):
    fake = ads(lambda r: httpx.Response(200, json={"number_added": 1}))
    text = text_of(await server.add_to_library("lib123", ["a", "b", "c"]))
    assert json.loads(fake.requests[0].content) == {"bibcode": ["a", "b", "c"], "action": "add"}
    assert "Added 1 of 3" in text
    assert "2 were not added" in text


async def test_create_library(ads):
    fake = ads(lambda r: httpx.Response(200, json={"id": "abc123", "name": "Review"}))
    text = text_of(await server.create_library("Review", "refs", public=False))
    assert json.loads(fake.requests[0].content) == {"name": "Review", "description": "refs", "public": False}
    assert "Library ID: abc123" in text


# --- the MCP layer, end to end -----------------------------------------------

async def test_every_tool_has_title_and_annotations():
    async with create_connected_server_and_client_session(server.app) as client:
        tools = (await client.list_tools()).tools
    assert len(tools) == 10
    for tool in tools:
        assert tool.title, tool.name
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is not None, tool.name
        assert tool.annotations.destructiveHint is False, tool.name
    writers = {t.name for t in tools if not t.annotations.readOnlyHint}
    assert writers == {"create_library", "add_to_library"}


async def test_errors_reach_claude_marked_as_errors(ads):
    ads(lambda r: httpx.Response(401))
    async with create_connected_server_and_client_session(server.app) as client:
        result = await client.call_tool("search_papers", {"query": "x"})
    assert result.isError is True
    assert "rejected the API token" in result.content[0].text


async def test_successful_call_is_not_an_error(ads):
    ads(lambda r: search_response([]))
    async with create_connected_server_and_client_session(server.app) as client:
        result = await client.call_tool("search_papers", {"query": "x"})
    assert result.isError is False
