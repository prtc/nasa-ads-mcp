"""NASA ADS MCP Server - Main server implementation."""

import asyncio
import html
import logging
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal, get_args

import httpx
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import TextContent, ToolAnnotations
from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from nasa_ads_mcp import __version__

# Load environment variables: from the current directory, then from the project root
load_dotenv()
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Logging goes to stderr, which is safe for MCP: only stdout carries the protocol,
# and Claude Desktop / Claude Code keep stderr in their MCP logs.
# Set NASA_ADS_LOG_FILE to also write a log file (useful when chasing disconnects).
_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
_log_file = os.getenv("NASA_ADS_LOG_FILE")
if _log_file:
    _log_handlers.append(logging.FileHandler(os.path.expanduser(_log_file)))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=_log_handlers,
)
logger = logging.getLogger("nasa-ads-mcp")
# httpx logs every request at INFO level; keep only its warnings
logging.getLogger("httpx").setLevel(logging.WARNING)

# API endpoints
ADS_API_BASE = "https://api.adsabs.harvard.edu/v1"
ADS_ABS_URL = "https://ui.adsabs.harvard.edu/abs"

# Largest number of rows the ADS search API returns in one request
ADS_MAX_ROWS = 2000

# Tests replace this with an httpx.MockTransport to simulate ADS responses
_transport: httpx.AsyncBaseTransport | None = None


class ADSError(ToolError):
    """An error talking to ADS, with a message meant for the user.

    A ToolError reaches Claude as a result marked is_error=True, with this
    message; the SDK hides the text of any other exception.
    """


# Where the `ads` Python package keeps the token; many astronomers already have it
ADS_DEV_KEY_FILE = Path("~/.ads/dev_key")


def _get_token() -> str:
    """Find the ADS token: ADS_API_TOKEN, then ADS_DEV_KEY, then ~/.ads/dev_key."""
    for name in ("ADS_API_TOKEN", "ADS_DEV_KEY"):
        token = (os.getenv(name) or "").strip()
        # A plugin option the user left unset can arrive as the literal placeholder
        if token and not token.startswith("${"):
            return token
    key_file = ADS_DEV_KEY_FILE.expanduser()
    if key_file.is_file():
        token = key_file.read_text().strip()
        if token:
            return token
    raise ADSError(
        "No ADS API token found. Get one at "
        "https://ui.adsabs.harvard.edu/user/settings/token, then either enter it "
        "in the plugin's settings, set ADS_API_TOKEN (or ADS_DEV_KEY), for example "
        "in the .env file of the nasa-ads-mcp folder, or save it in ~/.ads/dev_key "
        "(see README)."
    )


async def _api(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
) -> dict[str, Any]:
    """Call the ADS API and return the decoded JSON, raising ADSError on failure."""
    headers = {"Authorization": f"Bearer {_get_token()}"}
    async with httpx.AsyncClient(
        base_url=ADS_API_BASE, headers=headers, timeout=30, transport=_transport
    ) as client:
        try:
            response = await client.request(method, path, params=params, json=json)
        except httpx.HTTPError as e:
            raise ADSError(f"Could not reach ADS: {e}") from e

    if response.status_code == 401:
        raise ADSError("ADS rejected the API token (401). Check ADS_API_TOKEN.")
    if response.status_code == 429:
        reset = response.headers.get("X-RateLimit-Reset", "unknown")
        raise ADSError(f"ADS rate limit reached (429). Limit resets at epoch time {reset}.")
    if response.status_code == 404:
        raise ADSError(f"ADS returned 'not found' for {path}.")
    if response.status_code >= 400:
        try:
            detail = response.json().get("error") or response.text
        except ValueError:
            detail = response.text
        raise ADSError(f"ADS error {response.status_code}: {detail}")
    return response.json()


async def _search(
    q: str,
    fl: list[str],
    rows: int,
    sort: str | None = None,
    start: int = 0,
    fq: str | None = None,
) -> dict[str, Any]:
    """Run an ADS search query and return the Solr 'response' object."""
    params: dict[str, Any] = {"q": q, "fl": ",".join(fl), "rows": rows}
    if sort:
        params["sort"] = sort
    if start:
        params["start"] = start
    if fq:
        params["fq"] = fq
    data = await _api("GET", "/search/query", params=params)
    return data.get("response", {})


def _clamp(value: Any, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _offset(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _num(value: Any, fmt: str = "") -> str:
    """Format a metric that ADS may return as a number or as null."""
    if value is None:
        return "n/a"
    return format(value, fmt)


# ADS marks sub- and superscripts with HTML tags and escapes <, > and & as entities
_SUBSUP = re.compile(r"<(SUB|SUP)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_BREAK = re.compile(r"<(BR|P)\b[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def _clean(text: str) -> str:
    """Turn ADS's HTML markup into plain text with LaTeX-style sub/superscripts.

    H<SUB>2</SUB> becomes H$_{2}$, so titles can be pasted into a manuscript.
    Unicode (Greek letters, μm) is left as it is.
    """
    def latex(match: re.Match[str]) -> str:
        mark = "_" if match.group(1).upper() == "SUB" else "^"
        return f"${mark}{{{match.group(2)}}}$"

    text = _SUBSUP.sub(latex, text)
    text = _BREAK.sub(" ", text)
    text = _TAG.sub("", text)
    return html.unescape(text)


def _title(doc: dict[str, Any]) -> str:
    title = doc.get("title")
    return _clean(title[0]) if title else "No title"


def _authors(doc: dict[str, Any], limit: int, total_note: bool = True) -> str:
    authors = doc.get("author") or ["Unknown"]
    text = "; ".join(authors[:limit])
    if len(authors) > limit:
        text += f" et al. ({len(authors)} authors)" if total_note else " et al."
    return text


# Fields that let a reference be checked without another call
_REFERENCE_FIELDS = ["pub", "volume", "page", "doi", "identifier"]


def _reference(doc: dict[str, Any]) -> str:
    """Journal, volume, page, DOI and arXiv ID, as far as ADS has them."""
    page = (doc.get("page") or [None])[0]
    published = ", ".join(p for p in (doc.get("pub"), doc.get("volume"), page) if p)
    # ADS lists arXiv's own DOI (10.48550/arXiv...) next to the journal's
    doi = next((d for d in doc.get("doi") or [] if not d.lower().startswith("10.48550/")), None)
    arxiv = next(
        (i[len("arXiv:"):] for i in doc.get("identifier") or [] if i.startswith("arXiv:")), None
    )
    parts = [published or "Publication unknown"]
    if doi:
        parts.append(f"DOI: {doi}")
    if arxiv and arxiv not in published:
        parts.append(f"arXiv: {arxiv}")
    return " | ".join(parts)


# ADS collections (its "database" field). "all" means no filter.
Collection = Literal["astronomy", "physics", "earthscience", "general", "all"]
COLLECTIONS = list(get_args(Collection))


def _filters(
    collection: str | None,
    max_authors: int | None = None,
    refereed_only: bool = False,
) -> list[tuple[str, str]]:
    """The filters asked for, as (ADS filter query, description for the result)."""
    filters = []
    if collection and collection != "all":
        if collection not in COLLECTIONS:
            raise ADSError(f"Unknown collection '{collection}'. Use one of: {', '.join(COLLECTIONS)}.")
        filters.append((f"collection:{collection}", f"collection:{collection}"))
    if max_authors is not None:
        try:
            limit = int(max_authors)
        except (TypeError, ValueError):
            raise ADSError(f"max_authors must be a whole number, not '{max_authors}'.") from None
        if limit < 1:
            raise ADSError("max_authors must be at least 1.")
        filters.append((f"author_count:[1 TO {limit}]", f"at most {limit} authors"))
    if refereed_only:
        filters.append(("property:refereed", "refereed only"))
    return filters


def _fq(filters: list[tuple[str, str]]) -> str | None:
    return " AND ".join(query for query, _ in filters) or None


async def _filter_note(q: str, filters: list[tuple[str, str]], num_found: int) -> str | None:
    """Say what the filters left out, so their effect is never silent."""
    if not filters:
        return None
    label = ("Filter: " if len(filters) == 1 else "Filters: ") + ", ".join(d for _, d in filters)
    total = (await _search(q=q, fl=["bibcode"], rows=0)).get("numFound", 0)
    if total <= num_found:
        return f"{label} (left out none of the {total:,} matches)."
    left_out = total - num_found
    note = (
        f"{label}, so {num_found:,} of {total:,} matching papers are included; "
        + ("the other one is left out." if left_out == 1 else f"the other {left_out:,} are left out.")
    )
    if any(query.startswith("collection:") for query, _ in filters):
        note += " collection='all' includes other collections."
    return note


def _bare_id(identifier: str) -> str:
    """Drop the URL or 'doi:' prefix people often paste with a DOI."""
    identifier = identifier.strip().replace('"', "")
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if identifier.lower().startswith(prefix):
            return identifier[len(prefix):]
    return identifier


def _id_key(identifier: str) -> str:
    """A form of an identifier that compares equal to ADS's own listing of it."""
    key = _bare_id(identifier).lower()
    return key[len("arxiv:"):] if key.startswith("arxiv:") else key


# Identifiers (or bibcodes) per search, to keep each search URL short
_SEARCH_CHUNK = 50


async def _lookup(identifiers: list[str], fl: list[str]) -> dict[str, dict[str, Any]]:
    """Find papers by bibcode, DOI or arXiv ID: {identifier as given: ADS record}.

    Searches ADS's identifier field, not bibcode: a paper keeps its earlier
    bibcodes there (the arXiv preprint's, MNRAS's temporary '.tmp.' one), so
    references written before publication still resolve to the paper.
    """
    fl = list(dict.fromkeys(["bibcode", "identifier", *fl]))
    found: dict[str, dict[str, Any]] = {}
    for i in range(0, len(identifiers), _SEARCH_CHUNK):
        chunk = identifiers[i:i + _SEARCH_CHUNK]
        quoted = " OR ".join(f'"{_bare_id(x)}"' for x in chunk)
        result = await _search(q=f"identifier:({quoted})", fl=fl, rows=2 * len(chunk))
        by_key: dict[str, dict[str, Any]] = {}
        for doc in result.get("docs", []):
            for ident in [doc.get("bibcode") or "", *(doc.get("identifier") or [])]:
                by_key[_id_key(ident)] = doc
        for identifier in chunk:
            doc = by_key.get(_id_key(identifier))
            if doc is not None:
                found[identifier] = doc
    return found


_NOT_FOUND_HELP = (
    "The lookup used ADS's identifier field, which matches current and earlier "
    "bibcodes, DOIs and arXiv IDs, so these are most likely mistyped (a bibcode has "
    "19 characters, padded with dots, e.g. 2005A&A...443..735C) or not in ADS."
)


def _renamed(requested: list[str], found: dict[str, dict[str, Any]]) -> list[str]:
    """'given → bibcode' for papers asked for by a DOI, arXiv ID or earlier bibcode."""
    return [
        f"{r} → {found[r]['bibcode']}"
        for r in requested
        if r in found and found[r].get("bibcode") != r
    ]


async def _resolve(identifiers: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Current bibcodes for the identifiers, plus notes on renamed and missing ones."""
    found = await _lookup(identifiers, fl=[])
    bibcodes = list(dict.fromkeys(found[i]["bibcode"] for i in identifiers if i in found))
    missing = [i for i in identifiers if i not in found]
    return bibcodes, _renamed(identifiers, found), missing


# The MCP server. Each tool below is a function registered with @app.tool: the
# SDK builds its input schema from the type hints, and the Field descriptions are
# what Claude reads about each parameter.
# The version is reported to Claude when it connects (2.x would otherwise send "").
app = MCPServer("nasa-ads-mcp", version=__version__)

_READ_ONLY = dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

# An optional parameter, advertised with its plain type as in the hand-written
# schemas before 0.6.0 (no anyOf with null); null is still accepted as "not given".
OptionalStr = str | SkipJsonSchema[None]

Identifiers = Annotated[list[str], Field(
    description=(
        "Bibcodes (e.g. '2005A&A...443..735C'), DOIs or arXiv IDs (e.g. 'arXiv:1404.3243'). "
        "Earlier bibcodes (arXiv preprint, MNRAS '.tmp.') also work."
    ),
    min_length=1,
)]

LibraryId = Annotated[str, Field(description="Library ID (from list_libraries)")]

Offset = Annotated[int, Field(
    description="Number of results to skip, for the next page (default: 0)", ge=0,
)]

_COLLECTION_HELP = (
    "ADS collection to search: 'astronomy', 'physics', 'earthscience', 'general', "
    "or 'all' for no filter."
)

# The options shared by get_author_papers and get_author_metrics
AuthorCollection = Annotated[Collection, Field(
    description=(
        _COLLECTION_HELP + " Default 'astronomy': common surnames otherwise bring in "
        "biology, geoscience and other fields. Use 'all' to match ADS's web search, "
        "or when the author's work includes physics-only papers (e.g. atomic and "
        "molecular data). The result always states the filter and what it left out."
    ),
)]
Orcid = Annotated[OptionalStr, Field(
    description=(
        "Optional ORCID iD (e.g. '0000-0003-1846-4826'), the best way to tell apart "
        "people with the same name. Only papers with this ORCID recorded in ADS "
        "(from the publisher or claimed by the author) are included, so unclaimed "
        "older papers are left out."
    ),
)]
Affiliation = Annotated[OptionalStr, Field(
    description=(
        "Optional affiliation words (e.g. 'Sao Paulo'). Matches the affiliation of "
        "any author on the paper, and affiliations change over a career, so best "
        "combined with a year range."
    ),
)]
Position = Annotated[OptionalStr, Field(
    description=(
        "Optional author position: '1' (first author), '2' (second), or a range "
        "such as '1-3'. Uses ADS's pos() operator on the author list."
    ),
)]
# The minimum sits on int itself: on the union it would be advertised as an
# unknown "ge" keyword instead of "minimum"
MaxAuthors = Annotated[Annotated[int, Field(ge=1)] | SkipJsonSchema[None], Field(
    description=(
        "Optional: only papers with at most this many authors (e.g. 20), to leave out "
        "large collaboration papers. The result states how many papers this removed."
    ),
)]
RefereedOnly = Annotated[bool, Field(description="Optional: only refereed papers (default: false).")]


def _showing(offset: int, shown: int, num_found: int) -> str:
    """'showing 11-20'; empty when every result is shown."""
    if offset == 0 and shown >= num_found:
        return ""
    if shown == 1:
        return f" (showing {offset + 1})"
    return f" (showing {offset + 1}-{offset + shown})"


def _next_page(offset: int, shown: int, num_found: int) -> str | None:
    if offset + shown >= num_found:
        return None
    return f"More results: call again with offset={offset + shown}."


_EMPTY_SEARCH_HELP = (
    "ADS requires every word to match, so one word written differently from the record "
    "('microns' vs 'μm') hides a paper. Try fewer, distinctive words, title:(...) or "
    "abs:(...) without quotes, author:\"Lastname, F\" with year:, or get_paper_details "
    "with a bibcode, DOI or arXiv ID."
)


# A field followed by one bare word and then more bare words, as in
# "title:Stellar populations: a review": ADS applies the field to the first word only.
_LOOSE_FIELD = re.compile(
    r'(?<![\w.])(title|abs|abstract|author|first_author|aff|keyword|full|body|object):'
    r'([^\s"()]+)((?:\s+(?!(?:AND|OR|NOT)\b)[^\s"():\-][^\s"():]*:?(?=\s|$))+)'
)


def _field_scope_hint(query: str) -> str | None:
    """Warn when a field reaches only the first of several words."""
    match = _LOOSE_FIELD.search(query)
    if match is None:
        return None
    field, first = match.group(1), match.group(2).rstrip(":")
    rest = [w.rstrip(":") for w in match.group(3).split()]
    words = " ".join([first, *rest])
    fixed = f'{field}:"{words}"' if field in ("author", "first_author") else f"{field}:({words})"
    return (
        f"Note: {field}: applies only to '{first}'; '{' '.join(rest)}' is searched in all "
        f"fields, which can bring in loosely related papers. To keep every word in "
        f"{field}, write {fixed}."
    )


@app.tool(
    title="Search papers",
    description=(
        "Search NASA ADS for papers. Each result shows title, authors, year, "
        "citations, publication (journal, volume, page), DOI, arXiv ID and bibcode.\n\n"
        "How ADS queries work:\n"
        "- Every word must match. One word written differently from the record "
        "('microns' vs 'μm', a missing hyphen) returns nothing, so search a few "
        "distinctive words rather than a pasted full title.\n"
        "- Fielded queries are the most reliable: author:\"Coelho, P\", "
        "first_author:\"Coelho, P\", title:(synthetic stellar spectra) (these words, "
        "any order), abs:(...) (title, abstract and keywords), year:2020 or "
        "year:2018-2024, property:refereed, doi:..., bibcode:(A OR B).\n"
        "- Quotes ask for an exact phrase, which is fragile with titles. A field "
        "applies only to the next word or parenthesized group: in "
        "title:Stellar populations, only 'Stellar' is searched in titles.\n"
        "- Words combine with AND; OR and a leading minus also work.\n"
        "- Author position: pos(author:\"Coelho, P\", 2) (second author), "
        "pos(author:\"Coelho, P\", 1, 3) (first to third). Team size: "
        "author_count:[1 TO 20].\n"
        "- Citation networks: citations(bibcode:X) (papers citing X), "
        "references(bibcode:X), similar(bibcode:X), trending(query).\n"
        "- With a bibcode, DOI or arXiv ID in hand, use get_paper_details instead.\n"
        "Sorted newest first by default; sort='relevance' suits topical searches. "
        "Page through long result lists with offset."
    ),
    annotations=ToolAnnotations(title="Search papers", **_READ_ONLY),
)
async def search_papers(
    query: Annotated[str, Field(
        description="ADS query, e.g. 'title:(stellar populations) year:2020-2024'",
    )],
    max_results: Annotated[int, Field(
        description="Maximum number of results to return (default: 10, max: 50)", ge=1, le=50,
    )] = 10,
    sort: Annotated[Literal["date", "citation_count", "relevance"], Field(
        description="Sort order: 'date' (newest first), 'citation_count' (most cited), or 'relevance'",
    )] = "date",
    offset: Offset = 0,
    collection: Annotated[Collection, Field(
        description=(
            _COLLECTION_HELP + " Default 'all'. 'astronomy' cuts noise from "
            "other fields but hides physics-only papers such as atomic and "
            "molecular data; the result states what the filter left out."
        ),
    )] = "all",
) -> list[TextContent]:
    """Search ADS for papers."""
    sort_map = {
        "date": "date desc",
        "citation_count": "citation_count desc",
        "relevance": "score desc",
    }
    offset = _offset(offset)
    filters = _filters(collection)
    result = await _search(
        q=query,
        fl=["bibcode", "title", "author", "year", "citation_count", *_REFERENCE_FIELDS],
        rows=_clamp(max_results, 10, 50),
        sort=sort_map.get(sort, "date desc"),
        start=offset,
        fq=_fq(filters),
    )
    docs = result.get("docs", [])
    num_found = result.get("numFound", len(docs))
    note = await _filter_note(query, filters, num_found)
    hint = _field_scope_hint(query)

    if not docs:
        if offset and num_found:
            text = f"No more results: '{query}' found {num_found} papers, fewer than offset={offset}."
        else:
            text = f"No papers found for query: {query}\n\n{_EMPTY_SEARCH_HELP}"
        return [TextContent(type="text", text="\n".join(filter(None, [text, hint, note])))]

    results = [
        f"{i}. {_title(doc)}\n"
        f"   Authors: {_authors(doc, 3)}\n"
        f"   Year: {doc.get('year', 'n/a')} | Citations: {doc.get('citation_count') or 0}\n"
        f"   Published: {_reference(doc)}\n"
        f"   Bibcode: {doc.get('bibcode')}\n"
        for i, doc in enumerate(docs, offset + 1)
    ]
    header = f"Found {num_found} papers for '{query}'" + _showing(offset, len(docs), num_found)
    lines = [header + ":", hint, note, "", "\n".join(results), _next_page(offset, len(docs), num_found)]
    return [TextContent(type="text", text="\n".join(line for line in lines if line is not None).rstrip())]


@app.tool(
    title="Get paper details",
    description=(
        "Get full details for up to 20 papers in one call: abstract, authors, "
        "publication (journal, volume, page), DOI, arXiv ID, keywords and citations. "
        "Accepts bibcodes, DOIs and arXiv IDs, and says which ones ADS doesn't have."
    ),
    annotations=ToolAnnotations(title="Get paper details", **_READ_ONLY),
)
async def get_paper_details(bibcodes: Annotated[Identifiers, Field(max_length=20)]) -> list[TextContent]:
    """Get detailed information about papers, by bibcode, DOI or arXiv ID."""
    if not bibcodes:
        raise ADSError("No bibcodes provided.")
    if len(bibcodes) > 20:
        raise ADSError(f"At most 20 papers per call ({len(bibcodes)} given); split the list.")
    found = await _lookup(
        bibcodes,
        fl=["title", "author", "year", "citation_count", "abstract", "keyword", *_REFERENCE_FIELDS],
    )

    sections = []
    for requested in bibcodes:
        paper = found.get(requested)
        if paper is None:
            continue
        bibcode = paper.get("bibcode")
        keywords = paper.get("keyword")
        details = [
            f"Title: {_title(paper)}",
            f"Authors: {_authors(paper, 30)}",
            f"Year: {paper.get('year', 'n/a')} | Citations: {paper.get('citation_count') or 0}",
            f"Published: {_reference(paper)}",
            f"Keywords: {_clean(', '.join(keywords)) if keywords else 'None'}",
            f"Bibcode: {bibcode}",
        ]
        if bibcode != requested:
            details.append(f"Requested as: {requested}")
        details += [
            f"ADS: {ADS_ABS_URL}/{bibcode}",
            "",
            "Abstract:",
            _clean(paper.get("abstract") or "No abstract available"),
        ]
        sections.append("\n".join(details))

    missing = [b for b in bibcodes if b not in found]
    if missing:
        sections.append(f"Not found in ADS: {', '.join(missing)}\n{_NOT_FOUND_HELP}")
    return [TextContent(type="text", text="\n\n---\n\n".join(sections))]


_POSITION = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$")


def _author_query(
    author: str,
    orcid: str | None = None,
    affiliation: str | None = None,
    years: str | None = None,
    position: str | int | None = None,
) -> str:
    if position is not None and str(position).strip():
        match = _POSITION.match(str(position))
        first = int(match.group(1)) if match else 0
        last = int(match.group(2) or first) if match else 0
        if first < 1 or last < first:
            raise ADSError(f"position must be a number like '2' or a range like '1-3', not '{position}'.")
        span = f"{first}, {last}" if last != first else str(first)
        query = f'pos(author:"{author}", {span})'
    else:
        query = f'author:"{author}"'
    if orcid:
        query += f" orcid:{orcid.strip().removeprefix('https://orcid.org/')}"
    if affiliation:
        query += f' aff:"{affiliation}"'
    if years:
        query += f" year:{years}"
    return query


@app.tool(
    title="Get author papers",
    description=(
        "Find papers by an author. Returns titles, years, publication details, "
        "citations and bibcodes. Searches the astronomy collection unless told "
        "otherwise; use orcid to tell apart people who share a name."
    ),
    annotations=ToolAnnotations(title="Get author papers", **_READ_ONLY),
)
async def get_author_papers(
    author: Annotated[str, Field(
        description=(
            "Author name, 'Lastname, F' or 'Lastname, First' "
            "(e.g. 'Coelho, P' matches every first name starting with P)"
        ),
    )],
    max_results: Annotated[int, Field(
        description="Maximum number of results (default: 20, max: 100)", ge=1, le=100,
    )] = 20,
    sort: Annotated[Literal["date", "citation_count"], Field(
        description="Sort by 'date' or 'citation_count'",
    )] = "date",
    offset: Offset = 0,
    collection: AuthorCollection = "astronomy",
    orcid: Orcid = None,
    affiliation: Affiliation = None,
    position: Position = None,
    max_authors: MaxAuthors = None,
    refereed_only: RefereedOnly = False,
) -> list[TextContent]:
    """Get papers by a specific author."""
    query = _author_query(author, orcid, affiliation, position=position)
    filters = _filters(collection, max_authors, refereed_only)
    offset = _offset(offset)
    result = await _search(
        q=query,
        fl=["bibcode", "title", "year", "citation_count", *_REFERENCE_FIELDS],
        rows=_clamp(max_results, 20, 100),
        sort="citation_count desc" if sort == "citation_count" else "date desc",
        start=offset,
        fq=_fq(filters),
    )
    docs = result.get("docs", [])
    num_found = result.get("numFound", len(docs))
    note = await _filter_note(query, filters, num_found)

    if not docs:
        text = f"No papers found for {query}"
        if offset and num_found:
            text = f"No more results: {query} found {num_found} papers, fewer than offset={offset}."
        return [TextContent(type="text", text="\n".join(filter(None, [text, note])))]

    total_citations = sum(doc.get("citation_count") or 0 for doc in docs)
    results = [
        f"{i}. {_title(doc)} ({doc.get('year', 'n/a')})\n"
        f"   {_reference(doc)}\n"
        f"   Citations: {doc.get('citation_count') or 0} | Bibcode: {doc.get('bibcode')}\n"
        for i, doc in enumerate(docs, offset + 1)
    ]
    header = f"Found {num_found} papers for {query}" + _showing(offset, len(docs), num_found)
    header += f" (citations of papers shown: {total_citations})"
    lines = [header + ":", note, "", "\n".join(results), _next_page(offset, len(docs), num_found)]
    return [TextContent(type="text", text="\n".join(line for line in lines if line is not None).rstrip())]


@app.tool(
    title="Export BibTeX",
    description=(
        "Export BibTeX citations for one or more papers, exactly as ADS formats them "
        "(journal macros, volume, pages, DOI, eprint). "
        "Accepts bibcodes, DOIs and arXiv IDs; the BibTeX key is always ADS's "
        "current bibcode, and the result notes any that changed. "
        "Useful for adding references to LaTeX/Quarto documents."
    ),
    annotations=ToolAnnotations(title="Export BibTeX", **_READ_ONLY),
)
async def export_bibtex(bibcodes: Identifiers) -> list[TextContent]:
    """Export BibTeX citations using the ADS export service.

    The BibTeX is ADS's own and is passed on untouched (no _clean): ADS already
    writes sub/superscripts and special characters as LaTeX there.
    """
    if not bibcodes:
        raise ADSError("No bibcodes provided.")
    current, renamed, missing = await _resolve(bibcodes)
    if not current:
        return [TextContent(
            type="text", text=f"Not found in ADS: {', '.join(missing)}\n{_NOT_FOUND_HELP}"
        )]

    data = await _api("POST", "/export/bibtex", json={"bibcode": current})
    bibtex = (data.get("export") or "").strip()
    if not bibtex:
        return [TextContent(type="text", text="ADS returned no BibTeX for these bibcodes.")]

    text = "BibTeX Citations:\n\n" + bibtex
    if renamed:
        text += "\n\n% Keys are ADS's current bibcodes: "
        text += "; ".join(renamed)
    if missing:
        text += "\n\n% Not found in ADS: " + ", ".join(missing)
    return [TextContent(type="text", text=text)]


def _format_metrics(data: dict[str, Any], indent: str = "") -> list[str]:
    """Format the sections of an ADS metrics response."""
    lines: list[str] = []
    basic = data.get("basic stats") or {}
    cites = data.get("citation stats") or {}
    indicators = data.get("indicators") or {}

    if cites:
        lines += [
            "Citation Statistics:",
            f"{indent}Total Citations: {_num(cites.get('total number of citations'))}",
            f"{indent}Refereed Citations: {_num(cites.get('total number of refereed citations'))}",
            f"{indent}Self-Citations: {_num(cites.get('number of self-citations'))}",
            f"{indent}Average Citations/Paper: {_num(cites.get('average number of citations'), '.1f')}",
            f"{indent}Median Citations: {_num(cites.get('median number of citations'), '.1f')}",
            f"{indent}Normalized Citations: {_num(cites.get('normalized number of citations'), '.1f')}",
        ]

    if indicators:
        lines += [
            "",
            "Impact Indicators:",
            f"{indent}h-index: {_num(indicators.get('h'))}",
            f"{indent}m-index: {_num(indicators.get('m'), '.3f')}",
            f"{indent}i10-index: {_num(indicators.get('i10'))}",
            f"{indent}i100-index: {_num(indicators.get('i100'))}",
            f"{indent}g-index: {_num(indicators.get('g'))}",
            f"{indent}tori-index: {_num(indicators.get('tori'), '.1f')}",
            f"{indent}riq-index: {_num(indicators.get('riq'))}",
        ]

    # Reads live in "basic stats", not "citation stats"
    if basic:
        lines += [
            "",
            "Read Statistics:",
            f"{indent}Total Reads: {_num(basic.get('total number of reads'))}",
            f"{indent}Average Reads/Paper: {_num(basic.get('average number of reads'), '.1f')}",
            f"{indent}Median Reads: {_num(basic.get('median number of reads'), '.1f')}",
            f"{indent}Recent Reads (last 90 days): {_num(basic.get('recent number of reads'))}",
        ]

    skipped = data.get("skipped bibcodes") or []
    if skipped:
        lines += ["", f"Skipped (not found in ADS): {', '.join(skipped)}"]
    return lines


@app.tool(
    title="Get paper metrics",
    description=(
        "Get detailed metrics for specific papers including citation count, "
        "reads, and impact indicators. Accepts bibcodes, DOIs and arXiv IDs. "
        "Useful for tracking paper impact over time."
    ),
    annotations=ToolAnnotations(title="Get paper metrics", **_READ_ONLY),
)
async def get_paper_metrics(bibcodes: Identifiers) -> list[TextContent]:
    """Get metrics for specific papers."""
    if not bibcodes:
        raise ADSError("No bibcodes provided.")
    current, renamed, missing = await _resolve(bibcodes)
    notes = []
    if renamed:
        notes.append(f"Resolved to ADS's current bibcodes: {'; '.join(renamed)}")
    if missing:
        notes.append(f"Not found in ADS: {', '.join(missing)}")
    if not current:
        return [TextContent(type="text", text="\n".join(notes + [_NOT_FOUND_HELP]))]

    data = await _api("POST", "/metrics", json={"bibcodes": current})
    lines = _format_metrics(data, indent="  ")
    if not lines:
        return [TextContent(type="text", text="\n".join(["No metrics available for these papers", *notes]))]
    header = [f"Paper Metrics ({len(current)} papers):", ""]
    return [TextContent(type="text", text="\n".join(header + lines + ([""] + notes if notes else [])))]


@app.tool(
    title="Get author metrics",
    description=(
        "Get comprehensive metrics for an author including h-index, "
        "total citations, paper count, and citation statistics. "
        "Useful for CV preparation and tracking research impact. "
        "Matches names, not people: searches the astronomy collection unless "
        "told otherwise, and the result states the filter, so numbers can differ "
        "from ADS's web page, which counts all collections. For a common name, "
        "give the orcid. For a CV, refereed_only and max_authors give a figure for "
        "the author's own work, without large collaboration papers."
    ),
    annotations=ToolAnnotations(title="Get author metrics", **_READ_ONLY),
)
async def get_author_metrics(
    author: Annotated[str, Field(description="Author name (e.g. 'Coelho, P' or 'Coelho, Paula R. T.')")],
    years: Annotated[OptionalStr, Field(description="Optional year range (e.g., '2020-2025')")] = None,
    collection: AuthorCollection = "astronomy",
    orcid: Orcid = None,
    affiliation: Affiliation = None,
    position: Position = None,
    max_authors: MaxAuthors = None,
    refereed_only: RefereedOnly = False,
) -> list[TextContent]:
    """Get comprehensive metrics for an author."""
    query = _author_query(author, orcid, affiliation, years, position)
    filters = _filters(collection, max_authors, refereed_only)
    result = await _search(q=query, fl=["bibcode"], rows=ADS_MAX_ROWS, fq=_fq(filters))
    bibcodes = [doc["bibcode"] for doc in result.get("docs", []) if doc.get("bibcode")]
    note = await _filter_note(query, filters, result.get("numFound", len(bibcodes)))
    if not bibcodes:
        return [TextContent(type="text", text="\n".join(filter(None, [f"No papers found for {query}", note])))]

    data = await _api("POST", "/metrics", json={"bibcodes": bibcodes})

    lines = [f"Author Metrics for {query}", f"Total Papers: {len(bibcodes)}"]
    if note:
        lines.append(note + " ADS's web page for the same search applies none of these filters.")
    if result.get("numFound", 0) > len(bibcodes):
        lines.append(
            f"Note: ADS found {result['numFound']} papers; metrics use the first {len(bibcodes)}."
        )
    lines.append("")
    lines += _format_metrics(data, indent="  ")
    return [TextContent(type="text", text="\n".join(lines))]


@app.tool(
    title="List libraries",
    description=(
        "List all your personal paper libraries/collections in ADS. "
        "Shows library names, descriptions, and paper counts."
    ),
    annotations=ToolAnnotations(title="List libraries", **_READ_ONLY),
)
async def list_libraries() -> list[TextContent]:
    """List all user libraries."""
    data = await _api("GET", "/biblib/libraries")
    libraries = data.get("libraries", [])

    if not libraries:
        return [TextContent(
            type="text",
            text="No libraries found. Create one with the create_library tool!"
        )]

    lib_lines = ["Your ADS Libraries:\n"]
    for lib in libraries:
        lib_lines.append(
            f"• {lib.get('name', 'Unnamed')} (ID: {lib.get('id', 'unknown')})\n"
            f"  {lib.get('description') or 'No description'}\n"
            f"  Papers: {lib.get('num_documents', 0)} | "
            f"{'Public' if lib.get('public') else 'Private'}\n"
        )
    return [TextContent(type="text", text="\n".join(lib_lines))]


# Page size when reading a library
_LIBRARY_PAGE = 100


@app.tool(
    title="Get library papers",
    description=(
        "Get all papers from a specific library. "
        "Returns paper details for papers in the specified collection."
    ),
    annotations=ToolAnnotations(title="Get library papers", **_READ_ONLY),
)
async def get_library_papers(library_id: LibraryId) -> list[TextContent]:
    """Get papers from a library, reading every page of it."""
    bibcodes: list[str] = []
    metadata: dict[str, Any] = {}
    while True:
        data = await _api(
            "GET",
            f"/biblib/libraries/{library_id}",
            params={"start": len(bibcodes), "rows": _LIBRARY_PAGE},
        )
        metadata = data.get("metadata") or metadata
        page = data.get("documents", [])
        bibcodes += page
        total = metadata.get("num_documents", len(bibcodes))
        if not page or len(bibcodes) >= total:
            break

    name = metadata.get("name", library_id)
    if not bibcodes:
        return [TextContent(type="text", text=f"No papers in library '{name}'")]

    docs = await _lookup(bibcodes, fl=["title", "author", "year", "citation_count"])

    paper_lines = [f"Papers in library '{name}' ({len(bibcodes)} papers):\n"]
    for i, bibcode in enumerate(bibcodes, 1):
        doc = docs.get(bibcode)
        if doc is None:
            paper_lines.append(f"{i}. (metadata not found)\n   Bibcode: {bibcode}\n")
            continue
        current = doc.get("bibcode")
        paper_lines.append(
            f"{i}. {_title(doc)}\n"
            f"   {_authors(doc, 2, total_note=False)} ({doc.get('year', 'n/a')}) | "
            f"Citations: {doc.get('citation_count') or 0}\n"
            f"   Bibcode: {bibcode}"
            + (f" (now {current} in ADS)" if current != bibcode else "")
            + "\n"
        )
    return [TextContent(type="text", text="\n".join(paper_lines))]


@app.tool(
    title="Create library",
    description=(
        "Create a new paper library/collection in the user's ADS account. "
        "Useful for organizing papers by topic, project, or reading status."
    ),
    annotations=ToolAnnotations(
        title="Create library",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def create_library(
    name: Annotated[str, Field(description="Name for the library (e.g., 'Stellar Populations Review')")],
    description: Annotated[str, Field(description="Description of the library")] = "",
    public: Annotated[bool, Field(description="Whether the library should be public (default: false)")] = False,
) -> list[TextContent]:
    """Create a new library."""
    payload = {"name": name, "description": description, "public": public}
    data = await _api("POST", "/biblib/libraries", json=payload)
    return [TextContent(
        type="text",
        text=(
            f"✓ Created library '{data.get('name', name)}'\n"
            f"Library ID: {data.get('id')}\n\n"
            "Use add_to_library to add papers to this library."
        ),
    )]


@app.tool(
    title="Add papers to library",
    description=(
        "Add papers to an existing library in the user's ADS account. "
        "Provide library ID and list of bibcodes to add. "
        "Papers already in the library are not duplicated."
    ),
    annotations=ToolAnnotations(
        title="Add papers to library",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def add_to_library(
    library_id: LibraryId,
    bibcodes: Annotated[list[str], Field(description="List of bibcodes to add to the library", min_length=1)],
) -> list[TextContent]:
    """Add papers to a library, reporting how many ADS actually added."""
    if not bibcodes:
        raise ADSError("No bibcodes provided.")
    data = await _api(
        "POST",
        f"/biblib/documents/{library_id}",
        json={"bibcode": bibcodes, "action": "add"},
    )
    added = data.get("number_added")
    if added is None:
        text = f"✓ Sent {len(bibcodes)} paper(s) to library {library_id}"
    else:
        text = f"✓ Added {added} of {len(bibcodes)} paper(s) to library {library_id}"
        if added < len(bibcodes):
            text += (
                f"\n{len(bibcodes) - added} were not added: already in the library "
                "or not recognized by ADS."
            )
    return [TextContent(type="text", text=text)]


async def main():
    """Run the MCP server over stdio."""
    try:
        _get_token()
    except ADSError:
        logger.warning("No ADS token found; tools will return an error until one is set.")

    logger.info("NASA ADS MCP Server starting...")
    try:
        await app.run_stdio_async()
    except Exception as e:
        logger.exception(f"NASA ADS MCP Server crashed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
