# Roadmap

What's next for this project, what's known to be unfinished, and how releases work. Written so a future session, human or Claude, can pick up without anyone's memory. Last updated for version 0.5.1 (October 2026).

The guiding principle, from our first list of ideas (November 2025): *the goal isn't to implement everything at once, but to respond to actual user needs.* Now that the Pleiad students have the plugin, watch which questions they ask, which queries fail or feel awkward, and what they request.

## Where things stand

- **Version 0.4.1** is released: a Claude Code plugin, a Claude Desktop bundle (`nasa-ads.mcpb`, attached to each release), automated tests, and student guides in English and Portuguese.
- **Version 0.5.0** answers the first day of intensive real use (October 2026): lookups by any identifier (old bibcodes, DOIs, arXiv IDs), batch paper details, reference fields in results, LaTeX-style sub/superscripts, paging, a collection filter that always says what it removed, ORCID and affiliation for the author tools, and ADS query syntax in the search tool's description. **0.5.1**, the same day, added author position (`pos()`), `max_authors` and `refereed_only` for CV metrics, and a warning when a search field reaches only one word. See `CHANGELOG.md`.
- **Pleiad Astronomy** (the Claude Team organization) syncs the plugin from the private repository `pleiad-astronomy/plugins`, with default access "Installed by default".
- **Checked against the live ADS API:** search, metrics (including reads), BibTeX export, and reading a 633-paper library in full.
- **Not yet checked in real use:** the `.mcpb` bundle in an actual Claude Desktop, and whether Claude Code asks for the ADS token when the plugin arrives through the Team sync (it loads as `nasa-ads@synced`). Confirm both with the first students.

## Next: modernize the server (Move 3)

1. **Move to MCP SDK 2.x.** `pyproject.toml` pins `mcp<2` because 2.x removed the low-level API this server uses (`Server.list_tools`). In 2.x, FastMCP is renamed `MCPServer` (`from mcp.server.mcpserver import MCPServer`); see the [migration guide](https://py.sdk.modelcontextprotocol.io/v2/migration/). Tool schemas and annotations then come from type hints and decorators instead of the hand-written `list_tools`. The tests in `tests/test_server.py` call the tool functions and the MCP layer, so they should carry over with small changes.
2. **ADS search syntax in the tool descriptions:** done for `search_papers` in 0.5.0. Watch whether Claude still stumbles on queries, and adjust the wording from real failures.
3. **New tools**, roughly by value:
   - citations and references of a paper (dedicated tools, easier for Claude than the operators);
   - export in other ADS formats, especially AASTeX (for AAS journals) and RIS;
   - resolve a free-text reference string to a bibcode (to check a manuscript's bibliography);
   - remove papers from a library.
4. **Author disambiguation:** 0.5.0 and 0.5.1 added `orcid`, `affiliation`, `position`, `max_authors`, `refereed_only` and a default astronomy `collection` to the author tools. Still open: ORCID only finds papers where it was recorded, so older unclaimed papers drop out; `aff:` matches any author's affiliation, and tying it to one author would need `pos()` at the same position for both, which works only for a fixed position.
5. **Default sort:** `search_papers` sorts by date; relevance may suit topical searches better. Try both on real questions before changing.

## Ideas backlog

Good ideas not yet scheduled, most from the November 2025 list. Pick by what users actually ask for.

- **Search:** papers by affiliation or institution (`aff:`, `inst:`); the Journals API.
- **Metrics:** citation time series (the metrics API already returns histograms); comparing periods; exporting metrics to CSV.
- **Export:** more formats through the ADS export service, which also offers EndNote, RIS, and custom citation styles.
- **Libraries:** rename a library, update its description, export a whole library as BibTeX. Deleting a library is destructive: annotate the tool with `destructiveHint: true` and make the tool description ask Claude to confirm with the user first.
- **Errors and speed:** suggestions when a search finds nothing; retries for transient ADS failures; caching papers that are fetched often.
- **Documentation:** real-world workflow examples in the README (a literature review, tracking your own citations, building a manuscript's references), which may become skills (Move 4); a `CONTRIBUTING.md` and issue templates; badges.
- **Neighbours:** complementary servers for arXiv, SIMBAD, and NED, or links to existing ones (mcp-server-ads already resolves object names through SIMBAD/NED); connections to tools like TOPCAT or DS9.

## Then: skills for the group (Move 4)

Skills are written workflows that teach Claude how the group works, shipped in the plugin. Design them with Paula, from what students actually struggle with. Ideas so far:

- a literature review for a topic or a referee report;
- checking a manuscript's bibliography against ADS (every reference resolves, BibTeX from ADS);
- preparing for a referee report or journal club.

Group-specific skills could live in `pleiad-astronomy/plugins`, and general ones in this plugin.

## Later: reaching the community

- **ASCL** (Astrophysics Source Code Library): list the project there; it's where astronomers look for software.
- **Zenodo DOI:** connect the repository to Zenodo so each release gets a DOI. `CITATION.cff` is ready for it.
- **A short RNAAS note** on the tool and the human–AI collaboration behind it. Journal policy: AI can't be an author, so the collaboration goes in the AI-use disclosure.
- **Tell the ADS/SciX team** about the project, and keep the README's "Related Projects" list current.

## Known issues and open questions

- **Cowork doesn't start the plugin's server:** Cowork doesn't prompt for plugin settings, so a server that needs the token is skipped. Anthropic is merging chat and Cowork; revisit once that settles.
- **The dark-theme icon is faint at 32 px and below:** tracked in [pleiad-astronomy/visual-identity#2](https://github.com/pleiad-astronomy/visual-identity/issues/2).
- **The `.mcpb` bundle isn't signed,** so Claude Desktop may say so at install. Signing needs a certificate; fine to leave for now. Add a line to the student guides once the actual wording on screen is known.
- **Ingrid Beloto's credit:** her name only, until she says which link (if any) she'd like next to it, here and in `pleiad-astronomy/visual-identity`.
- **Anthropic's directory:** local servers can only be listed inside a plugin, and the directory policy requires owning the API a plugin connects to (section 3.F). ADS belongs to the ADS team, so a listing would need their involvement.

## How releases work

1. **Bump the version in five places:** `pyproject.toml`, `src/nasa_ads_mcp/__init__.py`, `.claude-plugin/plugin.json`, `manifest.json`, and `CITATION.cff` (`version` and `date-released`). Then run `uv lock`. The tests fail if any of them disagree, or if `date-released` differs from the newest `CHANGELOG.md` date.
2. **Add a `CHANGELOG.md` entry** dated the release day.
3. **Check locally:** `uv run pytest`, `claude plugin validate .`, and `npx @anthropic-ai/mcpb validate manifest.json`.
4. **Open a pull request.** GitHub runs the tests on Python 3.10 and 3.13 and builds the bundle.
5. **After merging, publish a GitHub release** with the tag `vX.Y.Z` (matching the version). A workflow builds `nasa-ads.mcpb` and attaches it; the release fails if the tag and `manifest.json` disagree.

Plugin users receive the new version because `plugin.json`'s version changed; the Team sync picks it up from `main` through `pleiad-astronomy/plugins`.

## Conventions

- **Authorship:** credit is shared and accountability is Paula's. Paula Coelho and Claude (Anthropic) are the authors; Paula is the maintainer and contact. Claude's commits carry a `Co-Authored-By` line. See "How This Was Made" in the README; don't change this without Paula.
- **The icon** is the Pleiad logo by Ingrid Beloto, made in `pleiad-astronomy/visual-identity` (`icons/make_icons.py`). It isn't covered by the MIT license.
- **Never commit a token.** `.env` is ignored by git and left out of the bundle by `.mcpbignore`; a test checks the latter.
