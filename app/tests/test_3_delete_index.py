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

def test_delete_index():
    print("=" * 70)
    print("TEST 4 — POST /workspace/delete-index (Batch Deletion Pipeline)")
    print("=" * 70)

    # 1. Parse active batch traces and gather path hashes
    batch_records = load_batch_state()
    successful_runs = [r for r in batch_records if r.get("status") in ("SUCCESS", "SKIPPED")]

    if not successful_runs:
        print("❌ No successful indices found to delete. Aborting.")
        return

    headers = {"X-User-Email": b64_email(USER_EMAIL)}
    workspace_id = hashlib.sha256(WORKSPACE_ROOT.encode()).hexdigest()
    rich_lang_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rich_language_folder")

    # Reconstruct exact paths and IDs to match what was indexed
    deletion_targets = []
    for run in successful_runs:
        file_path = os.path.join(rich_lang_dir, run["file_name"])
        path_id = hashlib.sha256(file_path.encode()).hexdigest()
        deletion_targets.append({
            "file_name": run["file_name"],
            "file_path": file_path,
            "path_id": path_id
        })

    path_ids_payload = [t["path_id"] for t in deletion_targets]

    print(f"Collected {len(path_ids_payload)} file path references for batch purge.")
    print(f"Targeting path_ids: {[p[:12] + '...' for p in path_ids_payload]}\n")

    # ── 2. Execute Batch Deletion ─────────────────────────────────────────────
    print(f"Sending deletion payload to {BASE_URL}/workspace/delete-index ...")
    resp = requests.post(
        f"{BASE_URL}/workspace/delete-index",
        headers={**headers, "Content-Type": "application/json"},
        json={"path_ids": path_ids_payload},
        timeout=30,
    )

    print(f"  HTTP Response: {resp.status_code}")
    data = resp.json()
    print(f"  Payload Return:\n{json.dumps(data, indent=4)}")
    resp.raise_for_status()

    assert data.get("status") == "success", f"Expected 'success', got: {data.get('status')}"
    
    # Track against total targeted keys deleted
    deleted_count = data.get("deleted_path_ids", 0)
    print(f"\n  Backend reports {deleted_count} record pathways cleared successfully.")
    assert deleted_count > 0, "No indices were removed from the vector database store."

    print("\n  ✅ PASSED — Delete API returned success status.")

    # ── 3. Verification Scoping Loop ──────────────────────────────────────────
    print("\n── Verifying Purge Completeness Across Storage Clusters ────────")
    
    for target in deletion_targets:
        print(f"  Checking target clearance -> {target['file_name']}")
        
        retrieve_resp = requests.post(
            f"{BASE_URL}/workspace/retrieve",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "query":        "pipeline operational status fallback definition",
                "workspace_id": workspace_id,
                "top_k":        3,
                "path_id":      target["path_id"],  # Scope tightly to deleted file path
            },
            timeout=60,
        )
        retrieve_resp.raise_for_status()
        results = retrieve_resp.json().get("data", [])
        
        print(f"    Retrieval returned {len(results)} hit segments.")
        assert len(results) == 0, f"Leaked vectors discovered! Chunks for {target['file_name']} still persist inside the store."

    print("\n  ✅ PASSED — Vector store chunks verified empty for all deleted records.")

    # ── 4. Verify Re-upload (Clean Slate Verification) ────────────────────────
    print("\n── Verifying Pipeline Re-ingestion Safety ──────────────────────")
    
    # Grab the first file variant to prove the pipeline now queues instead of skipping
    sample = deletion_targets[0]
    file_ext = os.path.splitext(sample["file_name"])[1]

    with open(sample["file_path"], "rb") as f:
        file_bytes = f.read()
        content_id = hashlib.sha256(file_bytes).hexdigest()

    print(f"  Re-uploading sample target to test bypass clearance: {sample['file_name']}")
    re_upload_resp = requests.post(
        f"{BASE_URL}/workspace/create-index",
        headers=headers,
        data={
            "content_id":     content_id,
            "workspace_id":   workspace_id,
            "workspace_path": WORKSPACE_ROOT,
            "path":           sample["file_path"],
            "path_id":        sample["path_id"],
            "file_name":      sample["file_name"],
            "file_extension": file_ext,
        },
        files={"file_data": (sample["file_name"], file_bytes, "application/octet-stream")},
        timeout=30,
    )

    re_upload_resp.raise_for_status()
    re_upload_data = re_upload_resp.json()
    re_status = re_upload_data.get("status")
    
    print(f"  Re-upload Status: {re_status}")
    assert re_status == "queued", f"Expected system to queue clean ingestion, but got: '{re_status}'"

    print("\n  ✅ PASSED — Dedup cache cleared properly; re-upload queued correctly.")

    # Clean up local file manifest artifacts
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".batch_test_results.json")
    if os.path.exists(state_path):
        os.remove(state_path)
        print("\n  Cleaned up tracking artifact: .batch_test_results.json")

    print("\n" + "=" * 70)
    print("ALL WORKSPACE BATCH CLEANUP TESTS PASSED SUCCESSFULLY ✅")
    print("=" * 70)

if __name__ == "__main__":
    test_delete_index()