"""NASA ADS MCP Server - Main server implementation."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server import Server
from mcp.types import TextContent, Tool, ToolAnnotations

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

# API endpoints
ADS_API_BASE = "https://api.adsabs.harvard.edu/v1"
ADS_ABS_URL = "https://ui.adsabs.harvard.edu/abs"

# Largest number of rows the ADS search API returns in one request
ADS_MAX_ROWS = 2000

# Tests replace this with an httpx.MockTransport to simulate ADS responses
_transport: httpx.AsyncBaseTransport | None = None


class ADSError(Exception):
    """An error talking to ADS, with a message meant for the user."""


def _get_token() -> str:
    token = os.getenv("ADS_API_TOKEN")
    if not token:
        raise ADSError(
            "ADS_API_TOKEN is not set. Get a token at "
            "https://ui.adsabs.harvard.edu/user/settings/token and put it in the "
            ".env file of the nasa-ads-mcp folder (see README)."
        )
    return token


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


async def _search(q: str, fl: list[str], rows: int, sort: str | None = None) -> dict[str, Any]:
    """Run an ADS search query and return the Solr 'response' object."""
    params: dict[str, Any] = {"q": q, "fl": ",".join(fl), "rows": rows}
    if sort:
        params["sort"] = sort
    data = await _api("GET", "/search/query", params=params)
    return data.get("response", {})


def _clamp(value: Any, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _num(value: Any, fmt: str = "") -> str:
    """Format a metric that ADS may return as a number or as null."""
    if value is None:
        return "n/a"
    return format(value, fmt)


def _title(doc: dict[str, Any]) -> str:
    title = doc.get("title")
    return title[0] if title else "No title"


def _authors(doc: dict[str, Any], limit: int, total_note: bool = True) -> str:
    authors = doc.get("author") or ["Unknown"]
    text = "; ".join(authors[:limit])
    if len(authors) > limit:
        text += f" et al. ({len(authors)} authors)" if total_note else " et al."
    return text


# Create MCP server
app = Server("nasa-ads-mcp")

_READ_ONLY = dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools for NASA ADS access."""
    return [
        Tool(
            name="search_papers",
            title="Search papers",
            description=(
                "Search NASA ADS for astronomy/astrophysics papers. "
                "Returns bibcodes, titles, authors, years, and citation counts. "
                "Use natural language queries or specific field searches. "
                "Examples: 'stellar populations', 'author:Coelho', 'year:2020-2024'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'stellar populations in elliptical galaxies')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10, max: 50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort order: 'date' (newest first), 'citation_count' (most cited), or 'relevance'",
                        "enum": ["date", "citation_count", "relevance"],
                        "default": "date",
                    },
                },
                "required": ["query"],
            },
            annotations=ToolAnnotations(title="Search papers", **_READ_ONLY),
        ),
        Tool(
            name="get_paper_details",
            title="Get paper details",
            description=(
                "Get detailed information about a specific paper using its bibcode. "
                "Returns full metadata including abstract, authors, citations, keywords, and more."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bibcode": {
                        "type": "string",
                        "description": "ADS bibcode (e.g., '2019ApJ...878...98S')",
                    },
                },
                "required": ["bibcode"],
            },
            annotations=ToolAnnotations(title="Get paper details", **_READ_ONLY),
        ),
        Tool(
            name="get_author_papers",
            title="Get author papers",
            description=(
                "Find all papers by a specific author. "
                "Returns list of papers with citations and publication details."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "author": {
                        "type": "string",
                        "description": "Author name (e.g., 'Coelho, P.' or 'Coelho, Paula')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20, max: 100)",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100,
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort by 'date' or 'citation_count'",
                        "enum": ["date", "citation_count"],
                        "default": "date",
                    },
                },
                "required": ["author"],
            },
            annotations=ToolAnnotations(title="Get author papers", **_READ_ONLY),
        ),
        Tool(
            name="export_bibtex",
            title="Export BibTeX",
            description=(
                "Export BibTeX citations for one or more papers, exactly as ADS formats them "
                "(journal macros, volume, pages, DOI, eprint). "
                "Useful for adding references to LaTeX/Quarto documents."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bibcodes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of ADS bibcodes to export",
                        "minItems": 1,
                    },
                },
                "required": ["bibcodes"],
            },
            annotations=ToolAnnotations(title="Export BibTeX", **_READ_ONLY),
        ),
        Tool(
            name="get_paper_metrics",
            title="Get paper metrics",
            description=(
                "Get detailed metrics for specific papers including citation count, "
                "reads, and impact indicators. "
                "Useful for tracking paper impact over time."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bibcodes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of ADS bibcodes (e.g., ['2019ApJ...878...98S'])",
                        "minItems": 1,
                    },
                },
                "required": ["bibcodes"],
            },
            annotations=ToolAnnotations(title="Get paper metrics", **_READ_ONLY),
        ),
        Tool(
            name="get_author_metrics",
            title="Get author metrics",
            description=(
                "Get comprehensive metrics for an author including h-index, "
                "total citations, paper count, and citation statistics. "
                "Useful for CV preparation and tracking research impact. "
                "Note: matches every paper with this author name, so common names "
                "may include other people's papers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "author": {
                        "type": "string",
                        "description": "Author name (e.g., 'Coelho, P.' or 'Coelho, Paula R. T.')",
                    },
                    "years": {
                        "type": "string",
                        "description": "Optional year range (e.g., '2020-2025')",
                    },
                },
                "required": ["author"],
            },
            annotations=ToolAnnotations(title="Get author metrics", **_READ_ONLY),
        ),
        Tool(
            name="list_libraries",
            title="List libraries",
            description=(
                "List all your personal paper libraries/collections in ADS. "
                "Shows library names, descriptions, and paper counts."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
            annotations=ToolAnnotations(title="List libraries", **_READ_ONLY),
        ),
        Tool(
            name="get_library_papers",
            title="Get library papers",
            description=(
                "Get all papers from a specific library. "
                "Returns paper details for papers in the specified collection."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "library_id": {
                        "type": "string",
                        "description": "Library ID (from list_libraries)",
                    },
                },
                "required": ["library_id"],
            },
            annotations=ToolAnnotations(title="Get library papers", **_READ_ONLY),
        ),
        Tool(
            name="create_library",
            title="Create library",
            description=(
                "Create a new paper library/collection in the user's ADS account. "
                "Useful for organizing papers by topic, project, or reading status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the library (e.g., 'Stellar Populations Review')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the library",
                    },
                    "public": {
                        "type": "boolean",
                        "description": "Whether the library should be public (default: false)",
                        "default": False,
                    },
                },
                "required": ["name"],
            },
            annotations=ToolAnnotations(
                title="Create library",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="add_to_library",
            title="Add papers to library",
            description=(
                "Add papers to an existing library in the user's ADS account. "
                "Provide library ID and list of bibcodes to add. "
                "Papers already in the library are not duplicated."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "library_id": {
                        "type": "string",
                        "description": "Library ID (from list_libraries)",
                    },
                    "bibcodes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of bibcodes to add to the library",
                        "minItems": 1,
                    },
                },
                "required": ["library_id", "bibcodes"],
            },
            annotations=ToolAnnotations(
                title="Add papers to library",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls for NASA ADS operations.

    Errors are raised, not returned: the MCP SDK turns an exception into a result
    marked isError=True, so Claude can tell a failure from an answer.
    """

    if name == "search_papers":
        return await search_papers(
            query=arguments["query"],
            max_results=arguments.get("max_results", 10),
            sort=arguments.get("sort", "date"),
        )

    elif name == "get_paper_details":
        return await get_paper_details(bibcode=arguments["bibcode"])

    elif name == "get_author_papers":
        return await get_author_papers(
            author=arguments["author"],
            max_results=arguments.get("max_results", 20),
            sort=arguments.get("sort", "date"),
        )

    elif name == "export_bibtex":
        return await export_bibtex(bibcodes=arguments["bibcodes"])

    elif name == "get_paper_metrics":
        return await get_paper_metrics(bibcodes=arguments["bibcodes"])

    elif name == "get_author_metrics":
        return await get_author_metrics(
            author=arguments["author"],
            years=arguments.get("years")
        )

    elif name == "list_libraries":
        return await list_libraries()

    elif name == "get_library_papers":
        return await get_library_papers(library_id=arguments["library_id"])

    elif name == "create_library":
        return await create_library(
            name=arguments["name"],
            description=arguments.get("description", ""),
            public=arguments.get("public", False)
        )

    elif name == "add_to_library":
        return await add_to_library(
            library_id=arguments["library_id"],
            bibcodes=arguments["bibcodes"]
        )

    else:
        raise ValueError(f"Unknown tool: {name}")


async def search_papers(query: str, max_results: int = 10, sort: str = "date") -> list[TextContent]:
    """Search ADS for papers."""
    sort_map = {
        "date": "date desc",
        "citation_count": "citation_count desc",
        "relevance": "score desc",
    }
    result = await _search(
        q=query,
        fl=["bibcode", "title", "author", "year", "citation_count"],
        rows=_clamp(max_results, 10, 50),
        sort=sort_map.get(sort, "date desc"),
    )
    docs = result.get("docs", [])

    if not docs:
        return [TextContent(type="text", text=f"No papers found for query: {query}")]

    results = [
        f"{i}. {_title(doc)}\n"
        f"   Authors: {_authors(doc, 3)}\n"
        f"   Year: {doc.get('year', 'n/a')}\n"
        f"   Citations: {doc.get('citation_count') or 0}\n"
        f"   Bibcode: {doc.get('bibcode')}\n"
        for i, doc in enumerate(docs, 1)
    ]
    header = f"Found {result.get('numFound', len(docs))} papers for '{query}'"
    if result.get("numFound", 0) > len(docs):
        header += f" (showing {len(docs)})"
    return [TextContent(type="text", text=header + ":\n\n" + "\n".join(results))]


async def get_paper_details(bibcode: str) -> list[TextContent]:
    """Get detailed information about a specific paper."""
    result = await _search(
        q=f'bibcode:"{bibcode}"',
        fl=["bibcode", "title", "author", "year", "citation_count",
            "abstract", "keyword", "doi", "pub"],
        rows=1,
    )
    docs = result.get("docs", [])
    if not docs:
        return [TextContent(type="text", text=f"Paper not found: {bibcode}")]

    paper = docs[0]
    doi = paper.get("doi")
    keywords = paper.get("keyword")
    details = [
        f"Title: {_title(paper)}",
        f"Authors: {'; '.join(paper.get('author') or ['Unknown'])}",
        f"Publication: {paper.get('pub') or 'Unknown'}",
        f"Year: {paper.get('year', 'n/a')}",
        f"Citations: {paper.get('citation_count') or 0}",
        f"DOI: {doi[0] if doi else 'N/A'}",
        f"Keywords: {', '.join(keywords) if keywords else 'None'}",
        f"Bibcode: {paper.get('bibcode')}",
        f"ADS: {ADS_ABS_URL}/{paper.get('bibcode')}",
        "",
        "Abstract:",
        paper.get("abstract") or "No abstract available",
    ]
    return [TextContent(type="text", text="\n".join(details))]


async def get_author_papers(author: str, max_results: int = 20, sort: str = "date") -> list[TextContent]:
    """Get papers by a specific author."""
    result = await _search(
        q=f'author:"{author}"',
        fl=["bibcode", "title", "year", "citation_count"],
        rows=_clamp(max_results, 20, 100),
        sort="citation_count desc" if sort == "citation_count" else "date desc",
    )
    docs = result.get("docs", [])

    if not docs:
        return [TextContent(type="text", text=f"No papers found for author: {author}")]

    total_citations = sum(doc.get("citation_count") or 0 for doc in docs)
    results = [
        f"{i}. {_title(doc)} ({doc.get('year', 'n/a')})\n"
        f"   Citations: {doc.get('citation_count') or 0} | Bibcode: {doc.get('bibcode')}\n"
        for i, doc in enumerate(docs, 1)
    ]
    header = f"Found {result.get('numFound', len(docs))} papers by '{author}'"
    if result.get("numFound", 0) > len(docs):
        header += f" (showing {len(docs)})"
    header += f" (citations of papers shown: {total_citations})"
    return [TextContent(type="text", text=header + ":\n\n" + "\n".join(results))]


async def export_bibtex(bibcodes: list[str]) -> list[TextContent]:
    """Export BibTeX citations using the ADS export service."""
    if not bibcodes:
        raise ADSError("No bibcodes provided.")
    data = await _api("POST", "/export/bibtex", json={"bibcode": bibcodes})
    bibtex = (data.get("export") or "").strip()
    if not bibtex:
        return [TextContent(type="text", text="ADS returned no BibTeX for these bibcodes.")]

    text = "BibTeX Citations:\n\n" + bibtex
    missing = [b for b in bibcodes if b not in bibtex]
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


async def get_paper_metrics(bibcodes: list[str]) -> list[TextContent]:
    """Get metrics for specific papers."""
    if not bibcodes:
        raise ADSError("No bibcodes provided.")
    data = await _api("POST", "/metrics", json={"bibcodes": bibcodes})
    lines = _format_metrics(data, indent="  ")
    if not lines:
        return [TextContent(type="text", text="No metrics available for these papers")]
    return [TextContent(type="text", text="\n".join([f"Paper Metrics ({len(bibcodes)} papers):", ""] + lines))]


async def get_author_metrics(author: str, years: str | None = None) -> list[TextContent]:
    """Get comprehensive metrics for an author."""
    query = f'author:"{author}"'
    if years:
        query += f" year:{years}"

    result = await _search(q=query, fl=["bibcode"], rows=ADS_MAX_ROWS)
    bibcodes = [doc["bibcode"] for doc in result.get("docs", []) if doc.get("bibcode")]
    if not bibcodes:
        return [TextContent(type="text", text=f"No papers found for author: {author}")]

    data = await _api("POST", "/metrics", json={"bibcodes": bibcodes})

    title = f"Author Metrics for {author}"
    if years:
        title += f" ({years})"
    lines = [title, f"Total Papers: {len(bibcodes)}"]
    if result.get("numFound", 0) > len(bibcodes):
        lines.append(
            f"Note: ADS found {result['numFound']} papers; metrics use the first {len(bibcodes)}."
        )
    lines.append("")
    lines += _format_metrics(data, indent="  ")
    return [TextContent(type="text", text="\n".join(lines))]


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


# Page size when reading a library, and bibcodes per metadata search
_LIBRARY_PAGE = 100
_SEARCH_CHUNK = 50


async def get_library_papers(library_id: str) -> list[TextContent]:
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

    # Fetch paper metadata in chunks to keep each search URL short
    docs_by_bibcode: dict[str, dict[str, Any]] = {}
    for i in range(0, len(bibcodes), _SEARCH_CHUNK):
        chunk = bibcodes[i:i + _SEARCH_CHUNK]
        quoted = " OR ".join(f'"{b}"' for b in chunk)
        result = await _search(
            q=f"bibcode:({quoted})",
            fl=["bibcode", "title", "author", "year", "citation_count"],
            rows=len(chunk),
        )
        for doc in result.get("docs", []):
            docs_by_bibcode[doc.get("bibcode")] = doc

    paper_lines = [f"Papers in library '{name}' ({len(bibcodes)} papers):\n"]
    for i, bibcode in enumerate(bibcodes, 1):
        doc = docs_by_bibcode.get(bibcode)
        if doc is None:
            paper_lines.append(f"{i}. (metadata not found)\n   Bibcode: {bibcode}\n")
            continue
        paper_lines.append(
            f"{i}. {_title(doc)}\n"
            f"   {_authors(doc, 2, total_note=False)} ({doc.get('year', 'n/a')}) | "
            f"Citations: {doc.get('citation_count') or 0}\n"
            f"   Bibcode: {bibcode}\n"
        )
    return [TextContent(type="text", text="\n".join(paper_lines))]


async def create_library(name: str, description: str = "", public: bool = False) -> list[TextContent]:
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


async def add_to_library(library_id: str, bibcodes: list[str]) -> list[TextContent]:
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
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    if not os.getenv("ADS_API_TOKEN"):
        logger.warning("ADS_API_TOKEN is not set; tools will return an error until it is.")

    async with stdio_server() as (read_stream, write_stream):
        logger.info("NASA ADS MCP Server starting...")
        try:
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
        except Exception as e:
            logger.exception(f"NASA ADS MCP Server crashed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
