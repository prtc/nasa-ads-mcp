# Changelog

## 0.6.0 — 2026-10-10

The server moves to version 2 of the MCP Python SDK. The tools work as before.

### Changed
- Built on MCP SDK 2.x (`MCPServer`). Each tool is now a typed Python function with a decorator, and its input schema comes from the type hints instead of a hand-written list. The tools keep the same names, parameters, types, limits, defaults and descriptions; the schemas now also give each parameter a `title`, which the SDK adds.
- Arguments outside a tool's schema (say, `max_results` above 50) are still refused before anything reaches ADS, now in the SDK's wording. Error messages begin with "Error executing tool <name>:".
- A failure the server didn't anticipate reaches Claude as "Error executing tool <name>", with the details kept in the server log. Errors from ADS (token, rate limit, not found) are still reported in full.
- When Claude connects, the server reports its own version (0.6.0); it used to report the SDK's.

### Verified against the live ADS API
- The same calls to the old and new server (searches, paper details, author papers and metrics, BibTeX, paper metrics, libraries) gave identical answers.

## 0.5.1 — 2026-10-08

Follow-ups from testing 0.5.0 in real use the same day.

### Added
- `position` for `get_author_papers` and `get_author_metrics`: papers where the author is first (`'1'`), second (`'2'`), or in a range (`'1-3'`), through ADS's `pos()` operator.
- `max_authors` and `refereed_only` for the same tools, so CV metrics can leave out large collaboration papers (ADS's `author_count`) and unrefereed ones. All filters are listed in the result, with how many papers they left out.
- `search_papers` warns when a field reaches only the first of several words: `title:Stellar populations: a review` searches only "Stellar" in titles and finds 1,087 loosely related papers; the note suggests `title:(Stellar populations a review)`, which finds 30.
- The `search_papers` description teaches `pos()` and `author_count:`.

### Note
- A Claude session that started before an update keeps the old tool definitions. After updating, start a new session.

## 0.5.0 — 2026-10-08

Fixes from a day of intensive real use.

### Fixed
- Papers asked for by an earlier bibcode (the arXiv preprint's, or MNRAS's temporary `.tmp.` one) were reported as "not found". `get_paper_details`, `export_bibtex`, `get_paper_metrics` and `get_library_papers` now look papers up through ADS's `identifier` field, which keeps those older bibcodes, and say when a paper's current bibcode differs.
- `export_bibtex` no longer reports a paper as missing when ADS exported it under its current bibcode.
- Titles, abstracts and keywords no longer show raw HTML: `H<SUB>2</SUB>` becomes `H$_{2}$`, `km s<SUP>-1</SUP>` becomes `km s$^{-1}$`, and entities like `&gt;` are decoded. BibTeX is left exactly as ADS writes it.

### Added
- `get_paper_details` takes up to 20 papers per call, by bibcode, DOI or arXiv ID, and says which ones ADS doesn't have and why that isn't a gap in the server. `export_bibtex` and `get_paper_metrics` also accept DOIs and arXiv IDs.
- Search and author results show journal, volume, page, DOI and arXiv ID, so a reference can be checked in one call.
- `offset` for `search_papers` and `get_author_papers`, and a line saying how to get the next page.
- A `collection` filter (`astronomy`, `physics`, `earthscience`, `general`, or `all`). It is off by default in `search_papers`, since atomic and molecular data papers can sit only in the physics collection. The author tools default to `astronomy`, because common surnames otherwise pull in biology and geoscience. Whenever a filter is on, the result says how many papers it left out.
- `orcid` and `affiliation` options for `get_author_papers` and `get_author_metrics`, to tell apart people who share a name.
- The `search_papers` description teaches ADS query syntax: every word must match, fielded searches, how far a field reaches, and the citation operators. A search that finds nothing explains why and what to try instead.

### Changed
- `get_paper_details` takes a list, `bibcodes`, instead of a single `bibcode`.
- Author metrics now default to the astronomy collection, so they can differ from ADS's web page; the result says so.

## 0.4.1 — 2026-09-27

### Added
- Claude Desktop bundle icons, in light- and dark-theme versions: the logo of the Pleiad Astronomy group, designed by Ingrid Beloto. The logo is not covered by the MIT license.

## 0.4.0 — 2026-09-26

### Added
- Claude Desktop bundle: `manifest.json` builds `nasa-ads.mcpb`, a one-click install that asks for the ADS token. Each GitHub release gets the bundle attached automatically.
- GitHub Actions: tests on Python 3.10 and 3.13 and a bundle build on every pull request and push to `main`.
- Student guides in English and Portuguese (`docs/`).
- README section on sharing the plugin with a research group through a Claude Team or Enterprise plan.

## 0.3.0 — 2026-09-26

### Added
- Claude Code plugin: install with `claude plugin marketplace add prtc/nasa-ads-mcp` and `claude plugin install nasa-ads@nasa-ads-mcp`. Claude Code asks for the ADS token and keeps it in the system's secure credential store.
- This repository is also a plugin marketplace, so organizations can list the plugin in their own marketplace and distribute it to members.
- The server also finds the token in `ADS_DEV_KEY` or `~/.ads/dev_key`, where the `ads` Python package keeps it.
- Paula Coelho's ORCID in `CITATION.cff`.

### Changed
- README installation guide: the plugin first, with a table of where the server works.
- Quieter logs: no line for every HTTP request.

### Verified against the live ADS API
- Read counts, ADS-formatted BibTeX, and reading a 633-paper library in full (ADS sends 20 papers per page; version 0.1 showed only the first 20).

## 0.2.0 — 2026-09-26

### Fixed
- The server no longer crashes at startup on any machine other than the author's: logs go to stderr by default, and `NASA_ADS_LOG_FILE` optionally adds a log file.
- Read counts in `get_paper_metrics` and `get_author_metrics` were always 0 because they were read from the wrong part of the ADS metrics response.
- `export_bibtex` now returns the BibTeX produced by the ADS export service (volume, pages, DOI, eprint, journal macros, correct entry types), instead of a hand-built entry.
- `get_library_papers` now reads every page of a library (large libraries could be cut short) and shows the library's name.
- `add_to_library` reports how many papers ADS actually added.
- Errors are reported to Claude as errors (not as normal results), with clear messages for a missing or invalid token and for rate limits.
- A missing `ADS_API_TOKEN` no longer stops the server from starting; tools explain how to set it.

### Changed
- Every tool now has a title and annotations saying whether it only reads or changes your ADS libraries.
- API calls are asynchronous (`httpx`), replacing the `ads` and `requests` packages.
- The MCP SDK is pinned below 2.0, whose server API is incompatible with this code.
- Authors are now Paula Coelho and Claude (Anthropic); Paula Coelho is the maintainer.

### Added
- Automated tests with simulated ADS responses (`uv run pytest`).
- README sections on data and privacy, related projects, and how this was made (authorship and CRediT contributions).
- `CITATION.cff`, so GitHub and Zenodo can cite the software with both authors.

## 0.1.0 — 2025-11-02

- First release: 10 tools for searching ADS, metrics, BibTeX export, and libraries.
