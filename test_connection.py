"""Quick test of ADS API connection."""

import os
from dotenv import load_dotenv
import ads

load_dotenv()

# Test API token
token = os.getenv("ADS_API_TOKEN")
if not token:
    print("❌ No ADS_API_TOKEN found in .env")
    exit(1)

print(f"✓ Found API token: {token[:10]}...")

# Configure ADS
ads.config.token = token

# Test a simple search
print("\nTesting ADS search...")
try:
    papers = ads.SearchQuery(
        q="stellar populations",
        fl=["bibcode", "title", "author", "year"],
        rows=3
    )
    
    print("✓ Search successful! Found papers:")
    for i, paper in enumerate(papers, 1):
        print(f"\n{i}. {paper.title[0] if paper.title else 'No title'}")
        print(f"   Year: {paper.year}")
        print(f"   Bibcode: {paper.bibcode}")
    
    print("\n✅ All tests passed! ADS API is working correctly.")

except Exception as e:
    print(f"\n❌ Error: {e}")
    exit(1)
