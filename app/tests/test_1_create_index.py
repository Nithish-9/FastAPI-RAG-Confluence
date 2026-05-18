#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import time
import requests

BASE_URL        = os.getenv("API_BASE_URL", "http://localhost:9001")
USER_EMAIL      = os.getenv("TEST_EMAIL", "developer@company.com")
WORKSPACE_ROOT  = os.getenv("WORKSPACE_ROOT", os.getcwd())   # current directory
POLL_INTERVAL   = 3    # seconds between status checks
POLL_TIMEOUT    = 300  # seconds before giving up

# Compute explicit path to the rich language snippets folder inside /tests
RICH_LANG_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rich_language_folder")

def b64_email(email: str) -> str:
    return base64.b64encode(email.encode()).decode()

def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_of_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def scan_all_test_files() -> list:
    """
    Scans the rich_language_folder for all valid tree-sitter stress test files
    based on a comprehensive list of support extensions.
    """
    if not os.path.exists(RICH_LANG_DIR):
        raise FileNotFoundError(
            f"Could not find code snippets directory at: {RICH_LANG_DIR}\n"
            "Please ensure 'rich_language_folder' exists inside your 'tests' folder."
        )

    valid_extensions = (
        '.php', '.py', '.rb', '.rs', '.scala', 
        '.sh', '.sql', '.swift', '.trigger', '.cls', 
        '.ts', '.md', '.css', '.html', '.json', 
        '.toml', '.xml', '.yaml', '.txt'
    )
    
    discovered_files = [
        os.path.join(RICH_LANG_DIR, f) 
        for f in os.listdir(RICH_LANG_DIR) 
        if f.endswith(valid_extensions) and os.path.isfile(os.path.join(RICH_LANG_DIR, f))
    ]

    if not discovered_files:
        raise FileNotFoundError(
            f"No valid stress-test syntax files found inside {RICH_LANG_DIR}."
        )
        
    return sorted(discovered_files)

def poll_status(task_id: str, headers: dict) -> dict:
    """Poll /workspace/index-status/{task_id} until terminal state."""
    url = f"{BASE_URL}/workspace/index-status/{task_id}"
    deadline = time.time() + POLL_TIMEOUT

    print(f"    Polling task {task_id}...")
    while time.time() < deadline:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "UNKNOWN")
        print(f"    Status: {status}")

        if status == "SUCCESS":
            return data
        if status == "FAILURE":
            raise RuntimeError(f"Task FAILED: {data.get('result')}")
        if status not in ("PENDING", "STARTED", "RETRY"):
            raise RuntimeError(f"Unexpected status: {status}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Task {task_id} did not complete within {POLL_TIMEOUT}s")


def test_create_index(file_path: str) -> dict:
    """Accepts an isolated file path and uploads it to the indexing API."""
    file_name = os.path.basename(file_path)
    file_ext  = os.path.splitext(file_name)[1]
    
    print("-" * 60)
    print(f"  Target File : {file_name}")
    print(f"  Extension   : {file_ext}")
    print("-" * 60)

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # Compute operational hashing fingerprints
    content_id     = sha256_of_bytes(file_bytes)
    path_id        = sha256_of_str(file_path)
    workspace_id   = sha256_of_str(WORKSPACE_ROOT)
    workspace_path = WORKSPACE_ROOT

    print(f"    content_id     : {content_id[:16]}...")
    print(f"    path_id        : {path_id[:16]}...")

    headers = {"X-User-Email": b64_email(USER_EMAIL)}

    # Post upload request multipart-bound payload representation
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

    print(f"    HTTP Response Status: {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()

    status = data.get("status")

    if status == "skipped":
        print(f"    ✅ SKIPPED — {data.get('reason')} (Deduplication Working)\n")
        return {
            "file_name": file_name,
            "status": "SKIPPED",
            "reason": data.get("reason")
        }

    assert status == "queued", f"Expected status 'queued', but encountered '{status}'"
    task_id = data.get("task_id")
    assert task_id, "Missing explicit 'task_id' context block in JSON payload response"

    # Block processing and poll async progress loop
    result = poll_status(task_id, headers)
    print(f"    ✅ PASSED — Node map indexing complete.\n")
    
    return {
        "task_id": task_id,
        "file_name": file_name,
        "status": "SUCCESS"
    }


def main():
    print("=" * 70)
    print(" BATCH RUN PIPELINE — TESTING ALL LANGUAGE KITCHEN SINK SNIPPETS")
    print("=" * 70)
    print(f"  Target Snippets Location: {RICH_LANG_DIR}")
    print(f"  Target Core Router API  : {BASE_URL}")
    print(f"  User Workspace Identity : {WORKSPACE_ROOT}\n")

    try:
        test_files = scan_all_test_files()
        print(f"Discovered {len(test_files)} structural syntax test targets.\n")
    except Exception as err:
        print(f"❌ Initialization Failed: {err}")
        return

    execution_manifest = []
    
    # Process sequentially to carefully monitor tree-sitter queuing behaviors
    for idx, file_path in enumerate(test_files, start=1):
        print(f"[{idx}/{len(test_files)}] Processing file tracking framework...")
        try:
            run_summary = test_create_index(file_path)
            execution_manifest.append(run_summary)
        except Exception as file_exception:
            print(f"    ❌ FAILED processing engine line context: {file_exception}\n")
            execution_manifest.append({
                "file_name": os.path.basename(file_path),
                "status": "FAILED",
                "error": str(file_exception)
            })

    results_out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".batch_test_results.json")
    with open(results_out_path, "w") as out_f:
        json.dump(execution_manifest, out_f, indent=2)
        
    print("=" * 70)
    print(" BATCH RUN SEQUENCE COMPLETE")
    print(f" Comprehensive operational logs stored in: {results_out_path}")
    print("=" * 70)

if __name__ == "__main__":
    main()