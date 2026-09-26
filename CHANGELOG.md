# Changelog

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
