"""
test_4_delete_index.py
──────────────────────
Tests POST /workspace/delete-index

Deletes the indexed file by path_id, then verifies that a retrieve
query returns zero results for that path_id — confirming chunks are
gone from Qdrant.

Run:
    python test_4_delete_index.py
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

def test_delete_index():
    print("=" * 60)
    print("TEST 4 — POST /workspace/delete-index")
    print("=" * 60)

    state    = load_state()
    path_id  = state["path_id"]
    ws_id    = state["workspace_id"]
    headers  = {"X-User-Email": b64_email(USER_EMAIL)}

    print(f"\n  Deleting path_id: {path_id[:16]}...")
    print(f"  File            : {state['file_name']}")

    # ── Delete ────────────────────────────────────────────────────────────
    resp = requests.post(
        f"{BASE_URL}/workspace/delete-index",
        headers={**headers, "Content-Type": "application/json"},
        json={"path_ids": [path_id]},
        timeout=30,
    )

    print(f"\n  HTTP {resp.status_code}")
    data = resp.json()
    print(f"  Response: {json.dumps(data, indent=2)}")
    resp.raise_for_status()

    assert data.get("status") == "success", \
        f"Expected status='success', got: {data}"
    assert data.get("deleted_path_ids") == 1, \
        f"Expected deleted_path_ids=1, got: {data.get('deleted_path_ids')}"

    print("\n  ✅ PASSED — delete API returned success")

    # ── Verify chunks are gone — retrieve should return 0 results ─────────
    print("\n── Verify chunks are gone from Qdrant ─────────────────────────")
    retrieve_resp = requests.post(
        f"{BASE_URL}/workspace/retrieve",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "query":        "loan interest calculation",
            "workspace_id": ws_id,
            "top_k":        5,
            "path_id":      path_id,   # scoped to the deleted file
        },
        timeout=60,
    )
    retrieve_resp.raise_for_status()
    results = retrieve_resp.json().get("data", [])
    print(f"  Retrieve (scoped to deleted path_id) returned {len(results)} result(s)")
    assert len(results) == 0, \
        f"Expected 0 results after delete, got {len(results)}"
    print("\n  ✅ PASSED — no chunks found after delete")

    # ── Verify re-upload works after delete ───────────────────────────────
    print("\n── Verify re-upload works after delete (should NOT be skipped) ─")
    file_path = state["file_path"]
    with open(file_path, "rb") as f:
        re_upload_resp = requests.post(
            f"{BASE_URL}/workspace/create-index",
            headers=headers,
            data={
                "content_id":     state["content_id"],
                "workspace_id":   ws_id,
                "workspace_path": state["workspace_path"],
                "path":           file_path,
                "path_id":        path_id,
                "file_name":      state["file_name"],
                "file_extension": state["file_extension"],
            },
            files={"file_data": (state["file_name"], f, "application/octet-stream")},
            timeout=30,
        )

    re_upload_resp.raise_for_status()
    re_upload_data = re_upload_resp.json()
    print(f"  Re-upload response: {json.dumps(re_upload_data, indent=2)}")

    re_status = re_upload_data.get("status")
    assert re_status == "queued", \
        f"Expected 'queued' after delete+re-upload, got '{re_status}'"

    print("\n  ✅ PASSED — re-upload queued correctly after delete")

    # Clean up state file
    if os.path.exists(".test_state.json"):
        os.remove(".test_state.json")
        print("\n  Cleaned up .test_state.json")

    print("\n" + "=" * 60)
    print("DELETE TEST PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    test_delete_index()
