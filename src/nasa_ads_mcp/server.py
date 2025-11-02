"""NASA ADS MCP Server - Main server implementation."""

import os
import logging
import requests
from typing import Any
from dotenv import load_dotenv
import ads
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from pydantic import AnyUrl

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nasa-ads-mcp")

# Initialize ADS with token
ads_token = os.getenv("ADS_API_TOKEN")
if not ads_token:
    raise ValueError(
        "ADS_API_TOKEN not found in environment. "
        "Please create a .env file with your NASA ADS API token."
    )
ads.config.token = ads_token

# API endpoints
ADS_API_BASE = "https://api.adsabs.harvard.edu/v1"
HEADERS = {
    "Authorization": f"Bearer {ads_token}",
    "Content-Type": "application/json"
}

# Create MCP server
app = Server("nasa-ads-mcp")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools for NASA ADS access."""
    return [
        Tool(
            name="search_papers",
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
        ),
        Tool(
            name="get_paper_details",
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
        ),
        Tool(
            name="get_author_papers",
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
        ),
        Tool(
            name="export_bibtex",
            description=(
                "Export BibTeX citations for one or more papers. "
                "Useful for adding references to LaTeX/Quarto documents."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bibcodes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of ADS bibcodes to export",
                    },
                },
                "required": ["bibcodes"],
            },
        ),
        Tool(
            name="get_paper_metrics",
            description=(
                "Get detailed metrics for specific papers including citation count, "
                "reference count, reads, and citation history. "
                "Useful for tracking paper impact over time."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bibcodes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of ADS bibcodes (e.g., ['2019ApJ...878...98S'])",
                    },
                },
                "required": ["bibcodes"],
            },
        ),
        Tool(
            name="get_author_metrics",
            description=(
                "Get comprehensive metrics for an author including h-index, "
                "total citations, paper count, and citation statistics. "
                "Useful for CV preparation and tracking research impact."
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
        ),
        Tool(
            name="list_libraries",
            description=(
                "List all your personal paper libraries/collections in ADS. "
                "Shows library names, descriptions, and paper counts."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_library_papers",
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
        ),
        Tool(
            name="create_library",
            description=(
                "Create a new paper library/collection. "
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
        ),
        Tool(
            name="add_to_library",
            description=(
                "Add papers to an existing library. "
                "Provide library ID and list of bibcodes to add."
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
                    },
                },
                "required": ["library_id", "bibcodes"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls for NASA ADS operations."""
    
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


async def search_papers(query: str, max_results: int, sort: str) -> list[TextContent]:
    """Search ADS for papers."""
    try:
        # Prepare sort parameter for ADS
        sort_map = {
            "date": "date desc",
            "citation_count": "citation_count desc",
            "relevance": "score desc",
        }
        
        # Perform search
        papers = ads.SearchQuery(
            q=query,
            fl=["bibcode", "title", "author", "year", "citation_count", "pubdate"],
            rows=min(max_results, 50),
            sort=sort_map.get(sort, "date desc"),
        )
        
        # Format results
        results = []
        for i, paper in enumerate(papers, 1):
            authors = paper.author[:3] if paper.author else ["Unknown"]
            author_str = ", ".join(authors)
            if paper.author and len(paper.author) > 3:
                author_str += f" et al. ({len(paper.author)} authors)"
            
            results.append(
                f"{i}. {paper.title[0] if paper.title else 'No title'}\n"
                f"   Authors: {author_str}\n"
                f"   Year: {paper.year}\n"
                f"   Citations: {paper.citation_count or 0}\n"
                f"   Bibcode: {paper.bibcode}\n"
            )
        
        if not results:
            return [TextContent(
                type="text",
                text=f"No papers found for query: {query}"
            )]
        
        response = f"Found {len(results)} papers for '{query}':\n\n" + "\n".join(results)
        return [TextContent(type="text", text=response)]
    
    except Exception as e:
        logger.error(f"Error searching papers: {e}")
        return [TextContent(
            type="text",
            text=f"Error searching papers: {str(e)}"
        )]


async def get_paper_details(bibcode: str) -> list[TextContent]:
    """Get detailed information about a specific paper."""
    try:
        papers = list(ads.SearchQuery(
            bibcode=bibcode,
            fl=["bibcode", "title", "author", "year", "citation_count", 
                "abstract", "keyword", "doi", "pubdate", "pub"],
        ))
        
        if not papers:
            return [TextContent(
                type="text",
                text=f"Paper not found: {bibcode}"
            )]
        
        paper = papers[0]
        
        # Format authors
        authors = paper.author if paper.author else ["Unknown"]
        author_str = "; ".join(authors)
        
        # Format keywords
        keywords = ", ".join(paper.keyword) if paper.keyword else "None"
        
        # Build detailed response
        details = [
            f"Title: {paper.title[0] if paper.title else 'No title'}",
            f"Authors: {author_str}",
            f"Publication: {paper.pub or 'Unknown'}",
            f"Year: {paper.year}",
            f"Citations: {paper.citation_count or 0}",
            f"DOI: {paper.doi[0] if paper.doi else 'N/A'}",
            f"Keywords: {keywords}",
            f"Bibcode: {paper.bibcode}",
            "",
            "Abstract:",
            paper.abstract or "No abstract available",
        ]
        
        return [TextContent(type="text", text="\n".join(details))]
    
    except Exception as e:
        logger.error(f"Error getting paper details: {e}")
        return [TextContent(
            type="text",
            text=f"Error getting paper details: {str(e)}"
        )]


async def get_author_papers(author: str, max_results: int, sort: str) -> list[TextContent]:
    """Get papers by a specific author."""
    try:
        # Prepare sort parameter
        sort_param = "date desc" if sort == "date" else "citation_count desc"
        
        # Search for author
        papers = ads.SearchQuery(
            author=author,
            fl=["bibcode", "title", "year", "citation_count", "pubdate"],
            rows=min(max_results, 100),
            sort=sort_param,
        )
        
        # Format results
        results = []
        total_citations = 0
        for i, paper in enumerate(papers, 1):
            citations = paper.citation_count or 0
            total_citations += citations
            results.append(
                f"{i}. {paper.title[0] if paper.title else 'No title'} ({paper.year})\n"
                f"   Citations: {citations} | Bibcode: {paper.bibcode}\n"
            )
        
        if not results:
            return [TextContent(
                type="text",
                text=f"No papers found for author: {author}"
            )]
        
        response = (
            f"Found {len(results)} papers by '{author}' "
            f"(Total citations: {total_citations}):\n\n"
            + "\n".join(results)
        )
        return [TextContent(type="text", text=response)]
    
    except Exception as e:
        logger.error(f"Error getting author papers: {e}")
        return [TextContent(
            type="text",
            text=f"Error getting author papers: {str(e)}"
        )]


async def export_bibtex(bibcodes: list[str]) -> list[TextContent]:
    """Export BibTeX citations for papers."""
    try:
        bibtex_entries = []
        
        for bibcode in bibcodes:
            # Get paper with BibTeX data
            papers = list(ads.SearchQuery(bibcode=bibcode))
            
            if not papers:
                bibtex_entries.append(f"% Paper not found: {bibcode}\n")
                continue
            
            paper = papers[0]
            
            # Generate BibTeX entry
            authors_str = " and ".join(paper.author) if paper.author else "Unknown"
            title = paper.title[0] if paper.title else "No title"
            
            entry = f"""@ARTICLE{{{bibcode},
    author = {{{authors_str}}},
    title = {{{title}}},
    journal = {{{paper.pub or 'Unknown'}}},
    year = {paper.year},
    adsurl = {{https://ui.adsabs.harvard.edu/abs/{bibcode}}},
}}
"""
            bibtex_entries.append(entry)
        
        if not bibtex_entries:
            return [TextContent(
                type="text",
                text="No valid bibcodes provided"
            )]
        
        response = "BibTeX Citations:\n\n" + "\n".join(bibtex_entries)
        return [TextContent(type="text", text=response)]
    
    except Exception as e:
        logger.error(f"Error exporting BibTeX: {e}")
        return [TextContent(
            type="text",
            text=f"Error exporting BibTeX: {str(e)}"
        )]


async def get_paper_metrics(bibcodes: list[str]) -> list[TextContent]:
    """Get metrics for specific papers."""
    try:
        # Prepare request payload
        payload = {"bibcodes": bibcodes}
        
        # Make API request
        response = requests.post(
            f"{ADS_API_BASE}/metrics",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Format response
        if "citation stats" in data:
            stats = data["citation stats"]
            metrics_lines = [
                "Paper Metrics:",
                f"Total Citations: {stats.get('total number of citations', 0)}",
                f"Total Refereed Citations: {stats.get('total number of refereed citations', 0)}",
                f"Average Citations per Paper: {stats.get('average number of citations', 0):.1f}",
                f"Median Citations: {stats.get('median number of citations', 0)}",
                f"Normalized Citations: {stats.get('normalized number of citations', 0):.1f}",
                f"Total Reads: {stats.get('total number of reads', 0)}",
                f"Average Reads per Paper: {stats.get('average number of reads', 0):.1f}",
            ]
            
            # Add indicator metrics if available
            if "indicators" in data:
                indicators = data["indicators"]
                metrics_lines.extend([
                    "",
                    "Indicators:",
                    f"h-index: {indicators.get('h', 0)}",
                    f"m-index: {indicators.get('m', 0):.2f}",
                    f"i10-index: {indicators.get('i10', 0)}",
                    f"g-index: {indicators.get('g', 0)}",
                ])
            
            return [TextContent(type="text", text="\n".join(metrics_lines))]
        else:
            return [TextContent(type="text", text="No metrics available for these papers")]
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting paper metrics: {e}")
        return [TextContent(
            type="text",
            text=f"Error getting paper metrics: {str(e)}"
        )]


async def get_author_metrics(author: str, years: str = None) -> list[TextContent]:
    """Get comprehensive metrics for an author."""
    try:
        # Build query
        query = f"author:\"{author}\""
        if years:
            query += f" year:{years}"
        
        # Get bibcodes for author's papers
        papers = ads.SearchQuery(
            q=query,
            fl=["bibcode"],
            rows=2000,  # Get many papers for accurate metrics
        )
        
        bibcodes = [paper.bibcode for paper in papers]
        
        if not bibcodes:
            return [TextContent(
                type="text",
                text=f"No papers found for author: {author}"
            )]
        
        # Get metrics for these papers
        payload = {"bibcodes": bibcodes}
        response = requests.post(
            f"{ADS_API_BASE}/metrics",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Format comprehensive author metrics
        metrics_lines = [f"Author Metrics for {author}"]
        if years:
            metrics_lines[0] += f" ({years})"
        metrics_lines.append(f"Total Papers: {len(bibcodes)}\n")
        
        if "citation stats" in data:
            stats = data["citation stats"]
            metrics_lines.extend([
                "Citation Statistics:",
                f"  Total Citations: {stats.get('total number of citations', 0)}",
                f"  Refereed Citations: {stats.get('total number of refereed citations', 0)}",
                f"  Self-Citations: {stats.get('number of self-citations', 0)}",
                f"  Average Citations/Paper: {stats.get('average number of citations', 0):.1f}",
                f"  Median Citations: {stats.get('median number of citations', 0)}",
                f"  Normalized Citations: {stats.get('normalized number of citations', 0):.1f}",
            ])
        
        if "indicators" in data:
            indicators = data["indicators"]
            metrics_lines.extend([
                "",
                "Impact Indicators:",
                f"  h-index: {indicators.get('h', 0)}",
                f"  m-index: {indicators.get('m', 0):.3f}",
                f"  i10-index: {indicators.get('i10', 0)}",
                f"  i100-index: {indicators.get('i100', 0)}",
                f"  g-index: {indicators.get('g', 0)}",
                f"  tori-index: {indicators.get('tori', 0):.1f}",
                f"  riq-index: {indicators.get('riq', 0)}",
            ])
        
        if "citation stats" in data:
            stats = data["citation stats"]
            metrics_lines.extend([
                "",
                "Read Statistics:",
                f"  Total Reads: {stats.get('total number of reads', 0)}",
                f"  Average Reads/Paper: {stats.get('average number of reads', 0):.1f}",
                f"  Median Reads: {stats.get('median number of reads', 0)}",
            ])
        
        return [TextContent(type="text", text="\n".join(metrics_lines))]
    
    except Exception as e:
        logger.error(f"Error getting author metrics: {e}")
        return [TextContent(
            type="text",
            text=f"Error getting author metrics: {str(e)}"
        )]


async def list_libraries() -> list[TextContent]:
    """List all user libraries."""
    try:
        response = requests.get(
            f"{ADS_API_BASE}/biblib/libraries",
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
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
                f"  {lib.get('description', 'No description')}\n"
                f"  Papers: {lib.get('num_documents', 0)} | "
                f"{'Public' if lib.get('public') else 'Private'}\n"
            )
        
        return [TextContent(type="text", text="\n".join(lib_lines))]
    
    except Exception as e:
        logger.error(f"Error listing libraries: {e}")
        return [TextContent(
            type="text",
            text=f"Error listing libraries: {str(e)}"
        )]


async def get_library_papers(library_id: str) -> list[TextContent]:
    """Get papers from a library."""
    try:
        response = requests.get(
            f"{ADS_API_BASE}/biblib/libraries/{library_id}",
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        bibcodes = data.get("documents", [])
        
        if not bibcodes:
            return [TextContent(
                type="text",
                text=f"No papers in library {library_id}"
            )]
        
        # Get paper details
        papers = ads.SearchQuery(
            q=f"bibcode:({' OR '.join(bibcodes)})",
            fl=["bibcode", "title", "author", "year", "citation_count"],
            rows=len(bibcodes)
        )
        
        paper_lines = [f"Papers in library {data.get('name', library_id)}:\n"]
        for i, paper in enumerate(papers, 1):
            authors = paper.author[:2] if paper.author else ["Unknown"]
            author_str = ", ".join(authors)
            if paper.author and len(paper.author) > 2:
                author_str += " et al."
            
            paper_lines.append(
                f"{i}. {paper.title[0] if paper.title else 'No title'}\n"
                f"   {author_str} ({paper.year}) | Citations: {paper.citation_count or 0}\n"
                f"   Bibcode: {paper.bibcode}\n"
            )
        
        return [TextContent(type="text", text="\n".join(paper_lines))]
    
    except Exception as e:
        logger.error(f"Error getting library papers: {e}")
        return [TextContent(
            type="text",
            text=f"Error getting library papers: {str(e)}"
        )]


async def create_library(name: str, description: str = "", public: bool = False) -> list[TextContent]:
    """Create a new library."""
    try:
        payload = {
            "name": name,
            "description": description,
            "public": public
        }
        
        response = requests.post(
            f"{ADS_API_BASE}/biblib/libraries",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        library_id = data.get("id")
        
        return [TextContent(
            type="text",
            text=f"✓ Created library '{name}'\nLibrary ID: {library_id}\n\nUse add_to_library to add papers to this library."
        )]
    
    except Exception as e:
        logger.error(f"Error creating library: {e}")
        return [TextContent(
            type="text",
            text=f"Error creating library: {str(e)}"
        )]


async def add_to_library(library_id: str, bibcodes: list[str]) -> list[TextContent]:
    """Add papers to a library."""
    try:
        payload = {
            "bibcode": bibcodes,
            "action": "add"
        }
        
        response = requests.post(
            f"{ADS_API_BASE}/biblib/documents/{library_id}",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        return [TextContent(
            type="text",
            text=f"✓ Added {len(bibcodes)} paper(s) to library {library_id}"
        )]
    
    except Exception as e:
        logger.error(f"Error adding to library: {e}")
        return [TextContent(
            type="text",
            text=f"Error adding to library: {str(e)}"
        )]


async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        logger.info("NASA ADS MCP Server starting...")
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
