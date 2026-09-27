# Roadmap

What's next for this project, what's known to be unfinished, and how releases work. Written so a future session, human or Claude, can pick up without anyone's memory. Last updated for version 0.4.1 (September 2026).

## Where things stand

- **Version 0.4.1** is released: a Claude Code plugin, a Claude Desktop bundle (`nasa-ads.mcpb`, attached to each release), automated tests, and student guides in English and Portuguese.
- **Pleiad Astronomy** (the Claude Team organization) syncs the plugin from the private repository `pleiad-astronomy/plugins`, with default access "Installed by default".
- **Checked against the live ADS API:** search, metrics (including reads), BibTeX export, and reading a 633-paper library in full.
- **Not yet checked in real use:** the `.mcpb` bundle in an actual Claude Desktop, and whether Claude Code asks for the ADS token when the plugin arrives through the Team sync (it loads as `nasa-ads@synced`). Confirm both with the first students.

## Next: modernize the server (Move 3)

1. **Move to MCP SDK 2.x.** `pyproject.toml` pins `mcp<2` because 2.x removed the low-level API this server uses (`Server.list_tools`). In 2.x, FastMCP is renamed `MCPServer` (`from mcp.server.mcpserver import MCPServer`); see the [migration guide](https://py.sdk.modelcontextprotocol.io/v2/migration/). Tool schemas and annotations then come from type hints and decorators instead of the hand-written `list_tools`. The tests in `tests/test_server.py` call the tool functions and the MCP layer, so they should carry over with small changes.
2. **Teach ADS search syntax in the tool descriptions:** `first_author:`, `property:refereed`, `abs:`, `year:`, and the operators `citations()`, `references()`, `similar()`, `trending()`. Cheap, and it lets Claude walk citation networks with the existing search tool.
3. **New tools**, roughly by value:
   - citations and references of a paper (dedicated tools, easier for Claude than the operators);
   - export in other ADS formats, especially AASTeX (for AAS journals) and RIS;
   - resolve a free-text reference string to a bibcode (to check a manuscript's bibliography);
   - remove papers from a library.
4. **Author disambiguation:** author metrics match names, not people. Consider an ORCID option (`orcid:` in ADS queries) for `get_author_metrics`.
5. **Default sort:** `search_papers` sorts by date; relevance may suit topical searches better. Try both on real questions before changing.

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
