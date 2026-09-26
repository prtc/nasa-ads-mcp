"""Quick check that the server can reach ADS with your token (makes real, read-only API calls).

Run with: uv run python test_connection.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from nasa_ads_mcp import server  # noqa: E402  (loads .env)


async def check() -> None:
    token = os.getenv("ADS_API_TOKEN")
    if not token:
        sys.exit("❌ No ADS_API_TOKEN found (set it in .env)")
    print("✓ Found API token")

    checks = [
        ("search", server.search_papers("stellar populations", max_results=3)),
        ("metrics", server.get_paper_metrics(["2005A&A...443..735C"])),
        ("BibTeX export", server.export_bibtex(["2005A&A...443..735C"])),
        ("libraries", server.list_libraries()),
    ]
    for label, call in checks:
        try:
            result = await call
        except server.ADSError as e:
            sys.exit(f"\n❌ {label} failed: {e}")
        print(f"\n✓ {label} works:\n" + result[0].text[:600])

    print("\n✅ All checks passed! ADS API is working correctly.")


if __name__ == "__main__":
    asyncio.run(check())
