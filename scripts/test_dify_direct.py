"""Direct Dify API diagnostic script.

Loads environment variables and makes ONE real authenticated request
to the Dify API to diagnose the 404 issue.

Never prints credentials. Prints only safe diagnostic info.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv(".env")

API_KEY = os.environ.get("DIFY_API_KEY", "")
BASE_URL = os.environ.get("DIFY_BASE_URL", "")
DATASET_ID = os.environ.get("DIFY_DATASET_ID", "")

# Build test URL using the same pattern as the existing adapter
# The existing adapter uses: POST {base_url}/knowledge/retrieve
TEST_URL = f"{BASE_URL.rstrip('/')}/knowledge/retrieve"

# Prepare payload with dataset ID
payload = {}
if DATASET_ID:
    payload["knowledge_base_ids"] = [DATASET_ID]
payload["query"] = "test query"
payload["top_k"] = 1

# Print only safe diagnostic info (no credentials)
print(f"base URL hostname: {BASE_URL.rstrip('/').split('//')[-1]}")
print(f"endpoint PATH: /knowledge/retrieve")
print(f"HTTP method: POST")
print(f"API key present: {'YES' if API_KEY else 'NO'}")
print(f"dataset ID present: {'YES' if DATASET_ID else 'NO'}")

# Make exactly ONE real authenticated Dify API request
import requests
session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
})

try:
    resp = session.post(TEST_URL, json=payload, timeout=30)
    status = resp.status_code
    body = resp.text
except Exception as e:
    status = "EXCEPTION"
    body = str(e)

print(f"HTTP status: {status}")
print(f"safe response/error body: {body[:200] if body else 'N/A'}")

# Determine Dify status
if status == 200:
    try:
        data = resp.json()
        results_count = len(data.get("data", []))
        print(f"Retrieved results: {results_count}")
    except Exception:
        print(f"Retrieved results: 0 (parse error)")
    print("Dify: REAL")
elif status == 404:
    print(f"Knowledge Base accessible: NO (404 not found)")
    print(f"Dify: BLOCKED")
    # Root cause info
    print(f"Root cause: API key present but endpoint /knowledge/retrieve returns 404")
    print(f"  Possible causes: wrong base URL, key lacks knowledge scope,")
    print(f"  dataset ID format mismatch, or Dify instance region mismatch")
else:
    print(f"Retrieved results: 0")
    print(f"Dify: BLOCKED")
    print(f"Root cause: HTTP {status}")
PYEOF