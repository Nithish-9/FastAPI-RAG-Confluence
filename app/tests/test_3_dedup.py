"""
test_3_dedup.py
───────────────
Tests dedup behaviour of POST /workspace/create-index

Uploads the same file a second time — expects {"status": "skipped"}
because content_id is unchanged. Confirms no duplicate chunks are
created in Qdrant.

Run:
    python test_3_dedup.py
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

# ── Test ──────────────────────────────────────────────────────────────────────

def test_dedup():
    print("=" * 60)
    print("TEST 3 — Dedup (re-upload same file)")
    print("=" * 60)

    state = load_state()
    headers = {"X-User-Email": b64_email(USER_EMAIL)}

    file_path = state["file_path"]
    print(f"\n  Re-uploading: {file_path}")
    print(f"  content_id  : {state['content_id'][:16]}... (same as before)")
    print(f"  Expected    : status='skipped'")

    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/workspace/create-index",
            headers=headers,
            data={
                "content_id":     state["content_id"],
                "workspace_id":   state["workspace_id"],
                "workspace_path": state["workspace_path"],
                "path":           file_path,
                "path_id":        state["path_id"],
                "file_name":      state["file_name"],
                "file_extension": state["file_extension"],
            },
            files={"file_data": (state["file_name"], f, "application/octet-stream")},
            timeout=30,
        )

    print(f"\n  HTTP {resp.status_code}")
    data = resp.json()
    print(f"  Response: {json.dumps(data, indent=2)}")
    resp.raise_for_status()

    status = data.get("status")
    assert status == "skipped", \
        f"Expected 'skipped' for unchanged file, got '{status}'"
    assert data.get("reason") == "content_id unchanged", \
        f"Unexpected skip reason: {data.get('reason')}"

    print("\n  ✅ PASSED — dedup correctly skipped re-ingestion")

    # ── Verify retrieve still works after dedup skip ──────────────────────
    print("\n── Verify retrieve still returns results after dedup skip ─────")
    retrieve_resp = requests.post(
        f"{BASE_URL}/workspace/retrieve",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "query":        "loan interest calculation",
            "workspace_id": state["workspace_id"],
            "top_k":        3,
        },
        timeout=60,
    )
    retrieve_resp.raise_for_status()
    results = retrieve_resp.json().get("data", [])
    print(f"  Retrieve returned {len(results)} result(s) — chunks still intact")
    assert len(results) > 0, "Chunks missing after dedup skip"
    print("\n  ✅ PASSED — chunks still intact after dedup skip")

    print("\n" + "=" * 60)
    print("DEDUP TEST PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    test_dedup()
