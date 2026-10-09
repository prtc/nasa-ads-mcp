"""Tests for the NASA ADS MCP server, using simulated ADS responses (no network, no token)."""

import json

import httpx
import pytest
from mcp import Client

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

@pytest.fixture
def no_token(monkeypatch, tmp_path):
    """No token anywhere: no environment variables and no ~/.ads/dev_key."""
    monkeypatch.delenv("ADS_API_TOKEN", raising=False)
    monkeypatch.delenv("ADS_DEV_KEY", raising=False)
    monkeypatch.setattr(server, "ADS_DEV_KEY_FILE", tmp_path / "dev_key")
    return tmp_path / "dev_key"


async def test_missing_token_gives_helpful_error(no_token):
    with pytest.raises(server.ADSError, match="No ADS API token found"):
        await server.search_papers("stellar populations")


def test_unset_plugin_option_placeholder_is_not_a_token(no_token, monkeypatch):
    monkeypatch.setenv("ADS_API_TOKEN", "${user_config.ads_api_token}")
    with pytest.raises(server.ADSError):
        server._get_token()


def test_token_from_ads_dev_key_file(no_token, monkeypatch):
    no_token.write_text("file-token\n")
    monkeypatch.setenv("ADS_API_TOKEN", "")  # a plugin option left empty
    assert server._get_token() == "file-token"


def test_environment_token_wins_over_file(no_token, monkeypatch):
    no_token.write_text("file-token")
    monkeypatch.setenv("ADS_DEV_KEY", "env-token")
    assert server._get_token() == "env-token"


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
        "pub": "Astronomy and Astrophysics",
        "volume": "443",
        "page": ["735"],
        "doi": ["10.1051/0004-6361:20053511", "10.48550/arXiv.astro-ph/0505511"],
        "identifier": ["2005A&A...443..735C", "arXiv:astro-ph/0505511", "2005astro.ph..5511C"],
    }]
    fake = ads(lambda r: search_response(docs, num_found=42))
    text = text_of(await server.search_papers("stellar spectra", max_results=500, sort="relevance"))

    assert len(fake.requests) == 1  # no collection filter, so no count to compare against
    params = fake.requests[0].url.params
    assert fake.requests[0].url.path == "/v1/search/query"
    assert params["q"] == "stellar spectra"
    assert params["rows"] == "50"  # clamped to the maximum
    assert params["sort"] == "score desc"
    assert "fq" not in params and "start" not in params
    assert "Found 42 papers" in text and "showing 1)" in text
    assert "et al. (4 authors)" in text
    assert "2005A&A...443..735C" in text
    # verification in one call: no backing volume and page out of the bibcode
    assert "Astronomy and Astrophysics, 443, 735" in text
    assert "DOI: 10.1051/0004-6361:20053511" in text  # the journal's DOI, not arXiv's
    assert "arXiv: astro-ph/0505511" in text
    assert "call again with offset=1" in text


async def test_search_papers_pages_with_offset(ads):
    docs = [{"bibcode": f"b{i}", "title": [f"T{i}"]} for i in (11, 12)]
    fake = ads(lambda r: search_response(docs, num_found=12))
    text = text_of(await server.search_papers("x", max_results=10, offset=10))
    assert fake.requests[0].url.params["start"] == "10"
    assert "showing 11-12" in text
    assert "11. T11" in text  # numbering continues across pages
    assert "offset=" not in text  # the last page has no next page


async def test_search_papers_offset_past_the_end(ads):
    ads(lambda r: search_response([], num_found=5))
    text = text_of(await server.search_papers("x", offset=10))
    assert "No more results" in text and "found 5 papers" in text


async def test_search_papers_no_results_explains_ads_matching(ads):
    ads(lambda r: search_response([]))
    text = text_of(await server.search_papers("nothing"))
    assert "No papers found" in text
    assert "every word to match" in text and "title:(...)" in text


async def test_search_papers_collection_filter_says_what_it_left_out(ads):
    def handler(request):
        if "fq" in request.url.params:
            return search_response([{"bibcode": "b1", "title": ["T"]}], num_found=448)
        return search_response([], num_found=8132)

    fake = ads(handler)
    text = text_of(await server.search_papers('author:"Silva, A."', collection="astronomy"))
    assert fake.requests[0].url.params["fq"] == "collection:astronomy"
    assert fake.requests[1].url.params["q"] == 'author:"Silva, A."'
    assert "Filter: collection:astronomy" in text
    assert "448 of 8,132" in text and "the other 7,684 are left out" in text
    assert "collection='all' includes other collections" in text


async def test_search_papers_warns_when_a_field_reaches_one_word(ads):
    ads(lambda r: search_response([{"bibcode": "b1", "title": ["T"]}], num_found=1087))
    text = text_of(await server.search_papers("title:Stellar populations: a review"))
    assert "title: applies only to 'Stellar'" in text
    assert "title:(Stellar populations a review)" in text


def test_field_scope_hint_only_for_the_trap():
    hint = server._field_scope_hint
    assert hint('author:Coelho Paula year:2020') is not None
    assert 'author:"Coelho Paula"' in hint('author:Coelho Paula year:2020')
    for fine in (
        'author:"Coelho, P" year:2020',
        "title:(stellar populations) abs:x year:2020",
        'abs:"dark matter" halo',
        "title:galaxy -cluster",
        "title:galaxy AND year:2020",
        "stellar populations",
    ):
        assert hint(fine) is None, fine


async def test_unknown_collection_is_an_error(ads):
    ads(lambda r: search_response([]))
    with pytest.raises(server.ADSError, match="Unknown collection"):
        await server.search_papers("x", collection="biology")


async def test_author_papers_query(ads):
    def handler(request):
        if "fq" in request.url.params:
            return search_response([{"bibcode": "b1", "title": ["T"], "year": "2020", "citation_count": 5}])
        return search_response([], num_found=3)

    fake = ads(handler)
    text = text_of(await server.get_author_papers("Coelho, P.", sort="citation_count"))
    assert fake.requests[0].url.params["q"] == 'author:"Coelho, P."'
    assert fake.requests[0].url.params["sort"] == "citation_count desc"
    # astronomy by default for author tools, and the result says so
    assert fake.requests[0].url.params["fq"] == "collection:astronomy"
    assert "Filter: collection:astronomy" in text and "1 of 3" in text
    assert "citations of papers shown: 5" in text


async def test_author_papers_orcid_affiliation_and_no_filter(ads):
    fake = ads(lambda r: search_response([{"bibcode": "b1", "title": ["T"]}]))
    text = text_of(await server.get_author_papers(
        "Coelho, P", collection="all",
        orcid="https://orcid.org/0000-0003-1846-4826", affiliation="Sao Paulo",
    ))
    assert len(fake.requests) == 1
    params = fake.requests[0].url.params
    assert params["q"] == 'author:"Coelho, P" orcid:0000-0003-1846-4826 aff:"Sao Paulo"'
    assert "fq" not in params and "Filter" not in text


# --- titles and abstracts ----------------------------------------------------------

def test_clean_turns_ads_html_into_latex():
    assert server._clean("The CO-to-H<SUB>2</SUB> Conversion Factor") == "The CO-to-H$_{2}$ Conversion Factor"
    assert server._clean("km s<SUP>-1</SUP>") == "km s$^{-1}$"
    assert server._clean("<SUP>13</SUP>C<SUP>14</SUP>N") == "$^{13}$C$^{14}$N"
    assert server._clean("T<sub>eff</sub> &gt; 5000 K &amp; log g") == "T$_{eff}$ > 5000 K & log g"
    assert server._clean("first<BR />second") == "first second"
    assert server._clean("the <I>Gaia</I>-ESO survey") == "the Gaia-ESO survey"
    assert server._clean("A<SUP>2</SUP>Π, 1.8 μm, α-enhanced") == "A$^{2}$Π, 1.8 μm, α-enhanced"


def test_clean_decodes_entities_last():
    """ADS sends markup as raw tags and escapes the text's own < and > (seen in
    real abstracts). Decoding entities first would turn these into tags and
    delete them."""
    assert server._clean("more oblate (&lt;q&gt; ~ 0.8)") == "more oblate (<q> ~ 0.8)"
    assert server._clean("range 0.6 &lt;z&lt; 1.3 within R&lt;R<SUB>vir</SUB>") == (
        "range 0.6 <z< 1.3 within R<R$_{vir}$"
    )


async def test_search_titles_are_cleaned(ads):
    ads(lambda r: search_response([{"bibcode": "b1", "title": ["The CO-to-H<SUB>2</SUB> Conversion Factor"]}]))
    assert "The CO-to-H$_{2}$ Conversion Factor" in text_of(await server.search_papers("x"))


# --- paper details ---------------------------------------------------------------

PAPER = {
    "bibcode": "2014MNRAS.440.1027C",
    "identifier": ["2014MNRAS.440.1027C", "2014arXiv1404.3243C", "arXiv:1404.3243", "10.1093/mnras/stu365"],
    "title": ["A new library of theoretical stellar spectra"],
    "author": ["Coelho, P. R. T."],
    "abstract": "covers 3000 &lt; T<SUB>eff</SUB> &lt; 25 000 K",
    "pub": "Monthly Notices of the Royal Astronomical Society",
    "volume": "440",
    "page": ["1027"],
    "doi": ["10.1093/mnras/stu365"],
}


async def test_paper_details_finds_papers_by_any_identifier(ads):
    fake = ads(lambda r: search_response([PAPER]))
    text = text_of(await server.get_paper_details(
        ["2014arXiv1404.3243C", "arXiv:1404.3243", "https://doi.org/10.1093/MNRAS/STU365", "2099XXX...1....1X"]
    ))
    assert len(fake.requests) == 1  # one call for the whole batch
    q = fake.requests[0].url.params["q"]
    assert q.startswith("identifier:(") and '"10.1093/MNRAS/STU365"' in q
    assert text.count("Title: A new library") == 3
    assert "Requested as: 2014arXiv1404.3243C" in text
    assert "Bibcode: 2014MNRAS.440.1027C" in text
    assert "Monthly Notices of the Royal Astronomical Society, 440, 1027" in text
    assert "3000 < T$_{eff}$ < 25 000 K" in text
    assert "Not found in ADS: 2099XXX...1....1X" in text
    assert "identifier field" in text  # says why it isn't an index gap


async def test_paper_details_not_found(ads):
    ads(lambda r: search_response([]))
    text = text_of(await server.get_paper_details(["2099XXX...1....1X"]))
    assert text.startswith("Not found in ADS: 2099XXX...1....1X")


async def test_paper_details_limits_batch_size(ads):
    ads(lambda r: search_response([]))
    with pytest.raises(server.ADSError, match="At most 20"):
        await server.get_paper_details([f"b{i}" for i in range(21)])


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
    paper = {"bibcode": "2005A&A...443..735C", "identifier": ["2005A&A...443..735C", "2005astro.ph..5511C"]}

    def handler(request):
        if request.url.path == "/v1/search/query":
            return search_response([paper])
        return httpx.Response(200, json={"msg": "Retrieved 1 abstracts", "export": ads_bibtex})

    fake = ads(handler)
    text = text_of(await server.export_bibtex(["2005astro.ph..5511C", "2099XXX...1....1X"]))

    request = fake.requests[1]
    assert request.method == "POST" and request.url.path == "/v1/export/bibtex"
    # only papers ADS has, under their current bibcode
    assert json.loads(request.content) == {"bibcode": ["2005A&A...443..735C"]}
    assert text.startswith("BibTeX Citations:\n\n@ARTICLE")  # ADS's BibTeX, untouched
    assert "volume = {443}" in text and "doi = " in text
    # an old bibcode is no longer reported as missing
    assert "2005astro.ph..5511C → 2005A&A...443..735C" in text
    assert "Not found in ADS: 2099XXX...1....1X" in text


async def test_export_bibtex_when_nothing_is_found(ads):
    fake = ads(lambda r: search_response([]))
    text = text_of(await server.export_bibtex(["2099XXX...1....1X"]))
    assert len(fake.requests) == 1  # no export call
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
    def handler(request):
        if request.url.path == "/v1/search/query":
            return search_response([{"bibcode": "a"}, {"bibcode": "b", "identifier": ["b", "arXiv:2001.00001"]}])
        return httpx.Response(200, json=METRICS)

    fake = ads(handler)
    text = text_of(await server.get_paper_metrics(["a", "arXiv:2001.00001", "2099XXX...1....1X"]))
    assert json.loads(fake.requests[1].content) == {"bibcodes": ["a", "b"]}
    assert "arXiv:2001.00001 → b" in text
    assert "Not found in ADS: 2099XXX...1....1X" in text
    assert "Total Reads: 1234" in text  # was always 0 in v0.1: read from the wrong section
    assert "Recent Reads (last 90 days): 56" in text
    assert "m-index: n/a" in text  # a null metric no longer crashes the formatting
    assert "Skipped (not found in ADS): 2099XXX...1....1X" in text


async def test_author_metrics_notes_truncation(ads):
    def handler(request):
        if request.url.path == "/v1/search/query":
            if "fq" in request.url.params:
                return search_response([{"bibcode": "a"}, {"bibcode": "b"}], num_found=2500)
            return search_response([], num_found=9000)
        return httpx.Response(200, json=METRICS)

    fake = ads(handler)
    text = text_of(await server.get_author_metrics("Coelho, P.", years="2020-2025"))
    assert fake.requests[0].url.params["q"] == 'author:"Coelho, P." year:2020-2025'
    assert fake.requests[0].url.params["fq"] == "collection:astronomy"
    assert json.loads(fake.requests[2].content) == {"bibcodes": ["a", "b"]}
    assert "ADS found 2500 papers" in text
    # the h-index never silently disagrees with ADS's web page
    assert "2,500 of 9,000" in text and "applies none of these filters" in text
    assert "h-index: 2" in text


async def test_author_metrics_for_a_cv(ads):
    def handler(request):
        if request.url.path == "/v1/search/query":
            if "fq" in request.url.params:
                return search_response([{"bibcode": "a"}], num_found=72)
            return search_response([], num_found=164)
        return httpx.Response(200, json=METRICS)

    fake = ads(handler)
    text = text_of(await server.get_author_metrics(
        "Coelho, P", orcid="0000-0003-1846-4826", max_authors=20, refereed_only=True, position="1-3",
    ))
    params = fake.requests[0].url.params
    assert params["q"] == 'pos(author:"Coelho, P", 1, 3) orcid:0000-0003-1846-4826'
    assert params["fq"] == "collection:astronomy AND author_count:[1 TO 20] AND property:refereed"
    assert "Filters: collection:astronomy, at most 20 authors, refereed only" in text
    assert "72 of 164" in text and "the other 92 are left out" in text


def test_author_position():
    query = server._author_query
    assert query("Coelho, P", position="2") == 'pos(author:"Coelho, P", 2)'
    assert query("Coelho, P", position=1) == 'pos(author:"Coelho, P", 1)'
    assert query("Coelho, P", position=" 1 - 3 ") == 'pos(author:"Coelho, P", 1, 3)'
    assert query("Coelho, P", position="2-2") == 'pos(author:"Coelho, P", 2)'
    assert query("Coelho, P", position="") == 'author:"Coelho, P"'
    for bad in ("second", "0", 0, "2-", "3-1", "1-0"):
        with pytest.raises(server.ADSError, match="position must be"):
            query("Coelho, P", position=bad)


async def test_bad_max_authors_is_an_error(ads):
    ads(lambda r: search_response([]))
    with pytest.raises(server.ADSError, match="max_authors"):
        await server.get_author_papers("Coelho, P", max_authors=0)


async def test_filter_note_with_one_paper_left_out(ads):
    def handler(request):
        if "fq" in request.url.params:
            return search_response([{"bibcode": "b1", "title": ["T"]}], num_found=32)
        return search_response([], num_found=33)

    ads(handler)
    text = text_of(await server.get_author_papers("Coelho, P", position="2"))
    assert "32 of 33" in text and "the other one is left out" in text


async def test_author_metrics_without_filter(ads):
    def handler(request):
        if request.url.path == "/v1/search/query":
            return search_response([{"bibcode": "a"}])
        return httpx.Response(200, json=METRICS)

    fake = ads(handler)
    text = text_of(await server.get_author_metrics("Coelho, P", collection="all"))
    assert "fq" not in fake.requests[0].url.params
    assert len(fake.requests) == 2 and "Filter" not in text


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
    assert "metadata not found" not in text


async def test_library_paper_saved_under_an_old_bibcode(ads):
    def handler(request):
        if "biblib" in request.url.path:
            return httpx.Response(200, json={
                "documents": ["2019MNRAS.tmp.2619C"], "metadata": {"name": "L", "num_documents": 1},
            })
        return search_response([{
            "bibcode": "2020MNRAS.491.2025C",
            "identifier": ["2020MNRAS.491.2025C", "2019MNRAS.tmp.2619C"],
            "title": ["To use or not to use synthetic stellar spectra"],
        }])

    ads(handler)
    text = text_of(await server.get_library_papers("lib123"))
    assert "To use or not to use" in text
    assert "2019MNRAS.tmp.2619C (now 2020MNRAS.491.2025C in ADS)" in text


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
    async with Client(server.app) as client:
        tools = (await client.list_tools()).tools
    assert len(tools) == 10
    for tool in tools:
        assert tool.title, tool.name
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is not None, tool.name
        assert tool.annotations.destructive_hint is False, tool.name
    writers = {t.name for t in tools if not t.annotations.read_only_hint}
    assert writers == {"create_library", "add_to_library"}


async def test_input_schemas_suit_claude():
    """The schemas come from type hints, so check what they advertise: the Claude API
    rejects a top-level anyOf/oneOf/allOf, every parameter needs its description,
    and optional parameters keep their plain type (no anyOf with null)."""
    standard = {"type", "description", "title", "default", "enum", "items",
                "minimum", "maximum", "minItems", "maxItems"}
    for tool in await server.app.list_tools():
        schema = tool.input_schema
        assert schema["type"] == "object", tool.name
        assert not {"anyOf", "oneOf", "allOf"} & set(schema), tool.name
        for name, prop in schema["properties"].items():
            assert prop.get("description"), (tool.name, name)
            assert "type" in prop, (tool.name, name)
            # e.g. a constraint on a union comes out as "ge" instead of "minimum"
            assert set(prop) <= standard, (tool.name, name, set(prop) - standard)


async def test_errors_reach_claude_marked_as_errors(ads):
    ads(lambda r: httpx.Response(401))
    async with Client(server.app) as client:
        result = await client.call_tool("search_papers", {"query": "x"})
    assert result.is_error is True
    assert "rejected the API token" in result.content[0].text


async def test_successful_call_is_not_an_error(ads):
    ads(lambda r: search_response([]))
    async with Client(server.app) as client:
        result = await client.call_tool("search_papers", {"query": "x"})
    assert result.is_error is False


async def test_new_parameters_reach_the_tools(ads):
    fake = ads(lambda r: search_response([PAPER]))
    async with Client(server.app) as client:
        details = await client.call_tool("get_paper_details", {"bibcodes": ["2014arXiv1404.3243C"]})
        await client.call_tool("search_papers", {"query": "x", "offset": 20, "collection": "physics"})
    assert details.is_error is False and "Requested as" in details.content[0].text
    search = fake.requests[1].url.params
    assert search["start"] == "20" and search["fq"] == "collection:physics"


async def test_author_options_reach_the_tools(ads):
    fake = ads(lambda r: search_response([{"bibcode": "a", "title": ["T"]}]))
    async with Client(server.app) as client:
        await client.call_tool("get_author_papers", {
            "author": "Coelho, P", "position": "2", "max_authors": 20,
            "refereed_only": True, "collection": "all",
        })
    params = fake.requests[0].url.params
    assert params["q"] == 'pos(author:"Coelho, P", 2)'
    assert params["fq"] == "author_count:[1 TO 20] AND property:refereed"


# --- packaging -----------------------------------------------------------------

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_versions_match():
    """Keep every version in step: the plugin only updates for users when its version
    changes, and GitHub and Zenodo cite the version in CITATION.cff."""
    import re

    # A pattern instead of tomllib, which needs Python 3.11+
    pyproject = re.search(r'^version = "(.+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    from nasa_ads_mcp import __version__

    bundle = json.loads((ROOT / "manifest.json").read_text())["version"]
    citation = re.search(r"^version: (.+)$", (ROOT / "CITATION.cff").read_text(), re.M).group(1).strip()
    assert pyproject == plugin == bundle == citation == __version__


def test_citation_date_matches_changelog():
    """CITATION.cff's release date must be the date of the newest changelog entry."""
    import re

    cited = re.search(r"^date-released: (\S+)", (ROOT / "CITATION.cff").read_text(), re.M).group(1)
    newest = re.search(r"^## \S+ — (\d{4}-\d{2}-\d{2})", (ROOT / "CHANGELOG.md").read_text(), re.M).group(1)
    assert cited == newest


async def test_bundle_manifest_lists_the_server_tools():
    """Claude Desktop shows the manifest's tool list at install time, so it must match the server."""
    manifest = json.loads((ROOT / "manifest.json").read_text())
    tools = await server.app.list_tools()
    assert [t["name"] for t in manifest["tools"]] == [t.name for t in tools]
    assert manifest["user_config"]["ads_api_token"]["sensitive"] is True
    assert manifest["server"]["mcp_config"]["env"]["ADS_API_TOKEN"] == "${user_config.ads_api_token}"


def test_bundle_never_ships_env_files():
    ignored = (ROOT / ".mcpbignore").read_text().splitlines()
    assert ".env" in ignored and ".env.*" in ignored


def test_plugin_server_points_at_real_files():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    server_config = plugin["mcpServers"]["nasa-ads"]
    paths = [a.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)) for a in server_config["args"] if "${CLAUDE_PLUGIN_ROOT}" in a]
    assert paths and all(__import__("os").path.exists(p) for p in paths)
    assert "--locked" in server_config["args"]
    assert server_config["env"]["ADS_API_TOKEN"] == "${user_config.ads_api_token}"
    assert "ads_api_token" in plugin["userConfig"]
    assert plugin["userConfig"]["ads_api_token"]["sensitive"] is True


def test_bundle_icons_exist():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    paths = [manifest["icon"]] + [icon["src"] for icon in manifest["icons"]]
    assert {icon["theme"] for icon in manifest["icons"]} == {"light", "dark"}
    for path in paths:
        assert (ROOT / path).is_file(), path
