"""
test_1_create_index.py
──────────────────────
Tests POST /workspace/create-index

Uploads LoanService.java (or any .py file in the current directory)
and polls until the Celery worker confirms indexing is complete.

Run:
    python test_1_create_index.py
"""

import base64
import hashlib
import json
import os
import time
import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL        = os.getenv("API_BASE_URL", "http://localhost:9001")
USER_EMAIL      = os.getenv("TEST_EMAIL", "developer@company.com")
WORKSPACE_ROOT  = os.getenv("WORKSPACE_ROOT", os.getcwd())   # current directory
POLL_INTERVAL   = 3    # seconds between status checks
POLL_TIMEOUT    = 300  # seconds before giving up

# ── Helpers ───────────────────────────────────────────────────────────────────

def b64_email(email: str) -> str:
    return base64.b64encode(email.encode()).decode()

def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_of_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def find_test_file() -> str:
    """
    Look for LoanService.java first, then any .java, then any .py
    in the current directory.
    """
    cwd = os.getcwd()

    # Prefer the sample file in the same directory as this script
    preferred = os.path.join(os.path.dirname(__file__), "LoanService.java")
    if os.path.exists(preferred):
        return preferred

    for fname in os.listdir(cwd):
        if fname.endswith(".java"):
            return os.path.join(cwd, fname)

    for fname in os.listdir(cwd):
        if fname.endswith(".py"):
            return os.path.join(cwd, fname)

    raise FileNotFoundError("No .java or .py file found in current directory")

def poll_status(task_id: str, headers: dict) -> dict:
    """Poll /workspace/index-status/{task_id} until terminal state."""
    url = f"{BASE_URL}/workspace/index-status/{task_id}"
    deadline = time.time() + POLL_TIMEOUT

    print(f"\n  Polling task {task_id}...")
    while time.time() < deadline:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "UNKNOWN")
        print(f"  Status: {status}")

        if status == "SUCCESS":
            return data
        if status == "FAILURE":
            raise RuntimeError(f"Task FAILED: {data.get('result')}")
        if status not in ("PENDING", "STARTED", "RETRY"):
            raise RuntimeError(f"Unexpected status: {status}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Task {task_id} did not complete within {POLL_TIMEOUT}s")

# ── Test ──────────────────────────────────────────────────────────────────────

def test_create_index():
    print("=" * 60)
    print("TEST 1 — POST /workspace/create-index")
    print("=" * 60)

    # Find file to upload
    file_path = find_test_file()
    file_name = os.path.basename(file_path)
    file_ext  = os.path.splitext(file_name)[1]
    print(f"\n  File        : {file_path}")
    print(f"  Name        : {file_name}")
    print(f"  Extension   : {file_ext}")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # Compute IDs
    content_id     = sha256_of_bytes(file_bytes)
    path_id        = sha256_of_str(file_path)
    workspace_id   = sha256_of_str(WORKSPACE_ROOT)
    workspace_path = WORKSPACE_ROOT

    print(f"\n  content_id     : {content_id[:16]}...")
    print(f"  path_id        : {path_id[:16]}...")
    print(f"  workspace_id   : {workspace_id[:16]}...")
    print(f"  workspace_path : {workspace_path}")

    headers = {"X-User-Email": b64_email(USER_EMAIL)}

    # Upload
    print(f"\n  Uploading to {BASE_URL}/workspace/create-index ...")
    with open(file_path, "rb") as f:
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
            files={"file_data": (file_name, f, "application/octet-stream")},
            timeout=30,
        )

    print(f"  HTTP {resp.status_code}")
    data = resp.json()
    print(f"  Response: {json.dumps(data, indent=2)}")
    resp.raise_for_status()

    status = data.get("status")

    if status == "skipped":
        print(f"\n  ✅ SKIPPED — {data.get('reason')} (dedup working correctly)")
        return data

    assert status == "queued", f"Expected 'queued', got '{status}'"
    task_id = data.get("task_id")
    assert task_id, "No task_id in response"

    # Poll
    result = poll_status(task_id, headers)
    print(f"\n  Task result: {json.dumps(result, indent=2)}")
    print(f"\n  ✅ PASSED — file indexed successfully")

    # Save task_id and ids for subsequent tests
    state = {
        "task_id":        task_id,
        "content_id":     content_id,
        "path_id":        path_id,
        "workspace_id":   workspace_id,
        "workspace_path": workspace_path,
        "file_path":      file_path,
        "file_name":      file_name,
        "file_extension": file_ext,
    }
    with open(".test_state.json", "w") as f:
        json.dump(state, f, indent=2)
    print("  State saved to .test_state.json for use by other tests")
    return state


if __name__ == "__main__":
    test_create_index()
