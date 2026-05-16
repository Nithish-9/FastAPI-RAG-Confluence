"""
test_2_retrieve.py
──────────────────
Tests POST /workspace/retrieve

Runs three searches against the indexed file:
  1. Broad query — should return multiple chunks
  2. Symbol-specific query — should return the relevant method chunk
  3. Follow-up with path_id — narrow search to the exact file

Reads workspace_id and path_id from .test_state.json written by test_1.

Run:
    python test_2_retrieve.py
"""

import base64
import json
import os
import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL   = os.getenv("API_BASE_URL", "http://localhost:9001")
USER_EMAIL = os.getenv("TEST_EMAIL", "developer@company.com")

# ── Helpers ───────────────────────────────────────────────────────────────────

def b64_email(email: str) -> str:
    return base64.b64encode(email.encode()).decode()

def load_state() -> dict:
    if not os.path.exists(".test_state.json"):
        raise FileNotFoundError(
            ".test_state.json not found — run test_1_create_index.py first"
        )
    with open(".test_state.json") as f:
        return json.load(f)

def retrieve(query: str, workspace_id: str, headers: dict,
             top_k: int = 5, path_id: str | None = None,
             chunk_index: int | None = None) -> list:
    payload = {
        "query":        query,
        "workspace_id": workspace_id,
        "top_k":        top_k,
    }
    if path_id:
        payload["path_id"] = path_id
    if chunk_index is not None:
        payload["chunk_index"] = chunk_index

    resp = requests.post(
        f"{BASE_URL}/workspace/retrieve",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    print(f"  HTTP {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])

def print_results(results: list):
    if not results:
        print("  ⚠️  No results returned")
        return
    for i, r in enumerate(results):
        print(f"\n  Result {i+1}:")
        print(f"    file     : {r.get('file_name')}")
        print(f"    symbol   : {r.get('symbol')}")
        print(f"    language : {r.get('language')}")
        print(f"    rrf      : {r.get('rrf_score', 'n/a')}")
        print(f"    rerank   : {r.get('rerank_score', 'n/a')}")
        # Show first 200 chars of content
        content = r.get("content", "")
        print(f"    content  : {content[:200].strip()}...")

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_retrieve():
    print("=" * 60)
    print("TEST 2 — POST /workspace/retrieve")
    print("=" * 60)

    state    = load_state()
    ws_id    = state["workspace_id"]
    path_id  = state["path_id"]
    headers  = {"X-User-Email": b64_email(USER_EMAIL)}

    # ── Search 1: broad query ─────────────────────────────────────────────
    print("\n── Search 1: broad query ──────────────────────────────────────")
    query = "loan calculation interest rate"
    print(f"  Query: '{query}'")
    results = retrieve(query, ws_id, headers, top_k=5)
    print(f"  Got {len(results)} result(s)")
    print_results(results)
    assert len(results) > 0, "Expected at least 1 result for broad query"
    print("\n  ✅ PASSED")

    # ── Search 2: symbol-specific query ──────────────────────────────────
    print("\n── Search 2: symbol-specific query ────────────────────────────")
    query = "calculate monthly payment principal annual rate term"
    print(f"  Query: '{query}'")
    results = retrieve(query, ws_id, headers, top_k=3)
    print(f"  Got {len(results)} result(s)")
    print_results(results)
    assert len(results) > 0, "Expected results for symbol-specific query"
    print("\n  ✅ PASSED")

    # ── Search 3: narrow by path_id (file-scoped search) ─────────────────
    print("\n── Search 3: narrow search by path_id ─────────────────────────")
    query = "validation errors loan amount"
    print(f"  Query: '{query}' (scoped to path_id={path_id[:16]}...)")
    results = retrieve(query, ws_id, headers, top_k=3, path_id=path_id)
    print(f"  Got {len(results)} result(s)")
    print_results(results)
    # All results must be from the same file
    for r in results:
        assert r.get("path_id") == path_id, \
            f"Result path_id mismatch: {r.get('path_id')} != {path_id}"
    print("\n  ✅ PASSED — all results scoped to correct file")

    print("\n" + "=" * 60)
    print("ALL RETRIEVE TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    test_retrieve()
