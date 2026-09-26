# Changelog

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

### Added
- Automated tests with simulated ADS responses (`uv run pytest`).
- README sections on data and privacy, and on related projects.

## 0.1.0 — 2025-11-02

- First release: 10 tools for searching ADS, metrics, BibTeX export, and libraries.
