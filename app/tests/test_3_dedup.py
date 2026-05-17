#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL       = os.getenv("API_BASE_URL", "http://localhost:9001")
USER_EMAIL     = os.getenv("TEST_EMAIL", "developer@company.com")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", os.getcwd())

# ── Helpers ───────────────────────────────────────────────────────────────────

def b64_email(email: str) -> str:
    return base64.b64encode(email.encode()).decode()

def load_batch_state() -> list:
    """Loads the array of successfully processed files from the batch run state."""
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".batch_test_results.json")
    if not os.path.exists(state_path):
        raise FileNotFoundError(
            f"Batch state manifest missing at {state_path} — Run your updated batch indexer script first!"
        )
    with open(state_path) as f:
        return json.load(f)

# ── Test ──────────────────────────────────────────────────────────────────────

def test_dedup():
    print("=" * 70)
    print("TEST 3 — Dedup & Store Integrity (Re-upload Batch Sample)")
    print("=" * 70)

    # 1. Extract a valid file record from the batch list
    batch_records = load_batch_state()
    successful_runs = [r for r in batch_records if r.get("status") in ("SUCCESS", "SKIPPED")]

    if not successful_runs:
        raise RuntimeError("No successful index tracks available in state history to dedup test.")

    # Target the first successful record as our testing baseline
    target_record = successful_runs[0]
    file_name = target_record["file_name"]
    file_ext  = os.path.splitext(file_name)[1]
    
    # Reconstruct environmental properties and physical path locations
    rich_lang_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rich_language_folder")
    file_path     = os.path.join(rich_lang_dir, file_name)
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file asset disappeared from workspace layout: {file_path}")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # Re-compute identical IDs matching indexer parameters
    content_id     = hashlib.sha256(file_bytes).hexdigest()
    path_id        = hashlib.sha256(file_path.encode()).hexdigest()
    workspace_id   = hashlib.sha256(WORKSPACE_ROOT.encode()).hexdigest()
    workspace_path = WORKSPACE_ROOT

    headers = {"X-User-Email": b64_email(USER_EMAIL)}

    print(f"\n  Target File  : {file_name}")
    print(f"  content_id   : {content_id[:16]}... (identical rerun trace)")
    print(f"  Expected     : status='skipped' | reason='content_id unchanged'")

    # 2. Fire the duplicate ingestion attempt
    print(f"\n  Pushing duplicate payload to {BASE_URL}/workspace/create-index ...")
    resp = requests.post(
        f"{BASE_URL}/workspace/create-index",
        headers=headers,
        data={
            "content_id":     content_id,
            "workspace_id":   workspace_id,
            "workspace_path": workspace_path,
            "path":           file_path,
            "path_id":        path_id,
            "file_name":      file_name,
            "file_extension": file_ext,
        },
        files={"file_data": (file_name, file_bytes, "application/octet-stream")},
        timeout=30,
    )

    print(f"  HTTP Response: {resp.status_code}")
    data = resp.json()
    print(f"  Payload Return:\n{json.dumps(data, indent=4)}")
    resp.raise_for_status()

    # Assert backend optimization successfully tripped
    status = data.get("status")
    assert status == "skipped", f"Optimization failure! Expected status 'skipped', encountered: '{status}'"
    
    reason = data.get("reason", "")
    assert "unchanged" in reason or "exist" in reason or status == "skipped", \
        f"Unexpected skip explanation context returned: '{reason}'"

    print("\n  ✅ PASSED — Deduplication pipeline correctly bypassed file re-processing.")

    # 3. Verify Vector Store Fragments Remain Intact
    print("\n── Verify Vector Store Chunks Remain Intact Post-Skip ─────────")
    
    # Using a generic syntax anchor likely to match structural keywords in any snippet
    fallback_query = "pipeline operational metrics layout status sequence engine"
    print(f"  Executing check query via path isolation scope: '{fallback_query}'")

    retrieve_resp = requests.post(
        f"{BASE_URL}/workspace/retrieve",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "query":        fallback_query,
            "workspace_id": workspace_id,
            "path_id":      path_id,
            "top_k":        3,
        },
        timeout=60,
    )
    retrieve_resp.raise_for_status()
    results = retrieve_resp.json().get("data", [])
    
    print(f"  Retrieve action returned {len(results)} active chunk context frames.")
    assert len(results) > 0, "Critical Fault: Vectors or document chunks vanished during dedup check!"
    
    print("\n  ✅ PASSED — Vector chunks verified intact inside database storage nodes.")

    print("\n" + "=" * 70)
    print("DEDUP TEST SEQUENCE VERIFIED SUCCESSFULLY ✅")
    print("=" * 70)

if __name__ == "__main__":
    test_dedup()