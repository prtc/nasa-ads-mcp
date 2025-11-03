# NASA ADS MCP Server

A Model Context Protocol (MCP) server that provides seamless access to the NASA Astrophysics Data System (ADS) directly within Claude. Search papers, track citations, manage libraries, and export references—all through natural language conversation.

**Author:** Claude (Anthropic), with human collaboration from Paula Coelho  
**License:** MIT

## Features

This MCP server exposes 10 tools for interacting with NASA ADS:

### Search & Discovery
- **search_papers** - Search the ADS database with natural language queries
- **get_paper_details** - Get comprehensive metadata for specific papers
- **get_author_papers** - Find all publications by a specific author

### Metrics & Analytics
- **get_paper_metrics** - Track citations, reads, and impact for specific papers
- **get_author_metrics** - Calculate h-index, citation statistics, and research impact

### Reference Management
- **export_bibtex** - Export properly formatted BibTeX citations
- **list_libraries** - View your personal ADS paper collections
- **get_library_papers** - Access papers from specific libraries
- **create_library** - Organize papers by topic or project
- **add_to_library** - Build and maintain paper collections

## Why This Tool?

The NASA ADS is the primary literature database for astronomy and astrophysics research, containing millions of papers, preprints, and citations. This MCP server makes ADS accessible through conversational AI, enabling:

- **Literature reviews** without switching contexts
- **Citation tracking** for your publications
- **BibTeX generation** for LaTeX/Quarto manuscripts
- **Research organization** through libraries
- **Impact analysis** with comprehensive metrics

Perfect for astronomers, astrophysicists, and researchers who want their reference database integrated into their AI workflow.

## Installation

### Prerequisites

- **Claude Desktop** installed ([download here](https://claude.ai/download))
- **Python 3.10+** 
- **uv** package manager ([install here](https://github.com/astral-sh/uv))
- **NASA ADS API token** ([get yours here](https://ui.adsabs.harvard.edu/user/settings/token))

### Setup

1. **Clone this repository:**
```bash
git clone https://github.com/prtc/nasa-ads-mcp.git
cd nasa-ads-mcp
```

2. **Install dependencies:**
```bash
uv sync
```

3. **Configure your API token:**

Create a `.env` file in the project root:
```bash
cp .env.example .env
```

Edit `.env` and add your NASA ADS API token:
```
ADS_API_TOKEN=your_token_here
```

4. **Add to Claude Desktop configuration:**

Edit your Claude Desktop config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add this entry to the `mcpServers` section:
```json
{
  "mcpServers": {
    "nasa-ads": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/nasa-ads-mcp",
        "run",
        "python",
        "src/nasa_ads_mcp/server.py"
      ]
    }
  }
}
```

Replace `/absolute/path/to/nasa-ads-mcp` with the actual path to where you cloned the repository.

5. **Restart Claude Desktop**

Look for the 🔨 hammer icon in the input box to confirm the server is connected.

## Usage Examples

Once connected, you can interact with ADS through natural language in Claude:

### Search & Discovery
```
"Search for recent papers on stellar populations in elliptical galaxies"
"Find papers by Coelho, Paula R. T. from 2020-2025"
"What are the most cited papers on galaxy formation?"
```

### Metrics & Impact
```
"What's my current h-index and total citations?"
"Show me citation trends for bibcode 2005A&A...443..735C"
"Get metrics for my 2024 papers"
```

### Reference Management
```
"Export BibTeX for these 5 papers: [bibcodes]"
"Show me what's in my 'Stellar Spectral Libraries' collection"
"Create a new library called 'Review Paper References'"
"Add these papers to my reading list"
```

## API Coverage

This server implements:
- ✅ **Search API** - Full query capabilities with field-specific searches
- ✅ **Metrics API** - Author and paper-level metrics
- ✅ **Libraries API** - Complete CRUD operations for collections
- ✅ **Export API** - BibTeX citation generation
- ⏳ **Journals API** - Future enhancement

## Development

### Project Structure
```
nasa-ads-mcp/
├── src/
│   └── nasa_ads_mcp/
│       ├── __init__.py
│       └── server.py          # Main MCP server implementation
├── tests/
├── .env.example               # Template for API token
├── .gitignore
├── pyproject.toml            # Project configuration
├── README.md
└── LICENSE
```

### Testing

A simple connection test is included:
```bash
uv run python test_connection.py
```

### Contributing

Contributions are welcome! This project is particularly suited for:
- Adding more ADS API endpoints
- Improving error handling
- Enhancing citation formatting
- Adding more metrics visualizations

## Technical Details

Built with:
- **MCP SDK** for Claude Desktop integration
- **ads Python package** for ADS API access
- **requests** for direct API calls (Metrics & Libraries)
- **python-dotenv** for secure token management

The server uses:
- **stdio transport** for Claude Desktop communication
- **Direct API calls** for Metrics and Libraries (not fully supported in ads package)
- **Rate limiting** handled by NASA ADS API (monitor via response headers)

## Known Limitations

- **Rate limits:** NASA ADS enforces rate limits. Monitor your usage for large queries.
- **Reads metric:** Currently returns 0 (API limitation, not server issue)
- **BibTeX formatting:** Basic implementation; doesn't include all possible fields

## Troubleshooting

### Server won't start
1. Verify Python 3.10+ is installed: `python3 --version`
2. Check API token is in `.env` file
3. Ensure `uv sync` completed successfully
4. Check Claude Desktop logs in Settings > Developer

### API errors
1. Verify your ADS API token is valid
2. Check you haven't hit rate limits
3. Confirm bibcodes are correctly formatted

### Can't see tools in Claude
1. Fully quit and restart Claude Desktop
2. Check the 🔨 hammer icon appears in the input
3. Verify config path is absolute, not relative

## Acknowledgments

- **NASA Astrophysics Data System** for providing the API
- **Anthropic** for creating MCP and Claude
- **Astronomy community** for maintaining the world's best literature database

## Citation

If you use this tool in your research workflow, you can cite:
```bibtex
@software{nasa_ads_mcp,
  author = {Claude (Anthropic)},
  title = {NASA ADS MCP Server},
  year = {2025},
  url = {https://github.com/prtc/nasa-ads-mcp}
}
```

## License

MIT License - see LICENSE file for details.

---

**Questions or Issues?** Open an issue on GitHub or contact through the repository.

**Want to learn more about MCP?** Visit [modelcontextprotocol.io](https://modelcontextprotocol.io)

---

**A note from the human in the loop:** This MCP server is the result of an experiment on collaborating with Claude to augment my literature search workflow. It leverages the Skill `mcp-builder` provided by Anthropic. I asked Claude to identify itself as the 1st author because I did not feel comfortable claiming the authorship of a code I did not write. With the exception of this paragraph, all the files including this `README.md` have been written by Claude. The MCP server is working well for me, but it is far from an extensively tested solution. Feel free to fork and modify or suggest me things that need fixing or improvement.
