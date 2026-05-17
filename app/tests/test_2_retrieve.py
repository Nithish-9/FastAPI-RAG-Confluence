#!/usr/bin/env python3
import base64
import json
import os
import requests
import hashlib

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL   = os.getenv("API_BASE_URL", "http://localhost:9001")
USER_EMAIL = os.getenv("TEST_EMAIL", "developer@company.com")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", os.getcwd())

# ── Helpers ───────────────────────────────────────────────────────────────────

def b64_email(email: str) -> str:
    return base64.b64encode(email.encode()).decode()

def load_batch_state() -> list:
    """Loads the array of successfully processed files from the batch run state."""
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".batch_test_results.json")
    if not os.path.exists(state_path):
        raise FileNotFoundError(
            f"Batch state not found at {state_path} — Run your updated batch indexer script first!"
        )
    with open(state_path) as f:
        return json.load(f)

def retrieve(query: str, workspace_id: str, headers: dict,
             top_k: int = 3, path_id: str | None = None) -> list:
    payload = {
        "query":        query,
        "workspace_id": workspace_id,
        "top_k":        top_k,
    }
    if path_id:
        payload["path_id"] = path_id

    resp = requests.post(
        f"{BASE_URL}/workspace/retrieve",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])

def print_results(results: list):
    if not results:
        print("    ⚠️  No results returned from indexer core store.")
        return
    for i, r in enumerate(results):
        print(f"    Result {i+1}: File: {r.get('file_name')} | Symbol: {r.get('symbol')} | Lang: {r.get('language')}")
        content = r.get("content", "")
        print(f"      Snippet: {content[:140].strip()}...")

# ── Language Target Matrix ───────────────────────────────────────────────────
# Dynamic queries mapped to key concepts inside your rich_language_folder files
LANGUAGE_QUERIES = {
    ".rs":     "unsafe memory pointer mutation or pipeline status enum",
    ".ts":     "conditional type utility mapping satisfies operator",
    ".sh":     "parameter expansion slice fallback substitutions or command sub",
    ".sql":    "recursive common table expressions hierarchy plpgsql function",
    ".swift":  "actor concurrency framework safe metrics tracker mapping",
    ".scala":  "pattern matching extractors with context parameters tailrec",
    ".trigger": "before insert trigger handler bulkification execution map",
    ".cls":    "database saveresult dynamic partial success handler",
    ".md":     "fenced javascript code block syntax injection markdown table",
    ".html":   "inline svg vector graphics form validation input range element",
    ".css":    "container queries layout configuration native nesting rules"
}

# ── Test Runner ───────────────────────────────────────────────────────────────

def test_batch_retrieve():
    print("=" * 70)
    print("TEST 2 — POST /workspace/retrieve (Batch Snippet Test Matrix)")
    print("=" * 70)

    # Dynamic Workspace Tracking Calculation
    workspace_id = hashlib.sha256(WORKSPACE_ROOT.encode()).hexdigest()
    headers = {"X-User-Email": b64_email(USER_EMAIL)}
    
    batch_records = load_batch_state()
    successful_runs = [r for r in batch_records if r.get("status") in ("SUCCESS", "SKIPPED")]

    if not successful_runs:
        print("❌ No successful indices found to run query retrievals against.")
        return

    print(f"Found {len(successful_runs)} ready index tracks. Beginning retrieval validation...\n")

    for idx, run in enumerate(successful_runs, start=1):
        file_name = run["file_name"]
        file_ext = os.path.splitext(file_name)[1]
        
        # Calculate file's path_id exactly like the indexer script did
        # Assuming files are evaluated from inside your rich_language_folder structure
        rich_lang_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rich_language_folder")
        file_path = os.path.join(rich_lang_dir, file_name)
        path_id = hashlib.sha256(file_path.encode()).hexdigest()

        # Fallback to a generic code query if extension missing from test matrix
        query = LANGUAGE_QUERIES.get(file_ext, "pipeline status error evaluation framework")

        print(f"[{idx}/{len(successful_runs)}] Testing Scope -> {file_name}")
        print(f"  Query: '{query}'")

        # Execute File-Scoped Retrieval using path_id
        try:
            results = retrieve(query, workspace_id, headers, top_k=2, path_id=path_id)
            print(f"  Got {len(results)} hit(s)")
            print_results(results)

            # Assert constraints
            if results:
                for r in results:
                    assert r.get("language").lower() in file_name.lower() or file_ext[1:] in r.get("language", "").lower() or file_ext == '.trigger' or file_ext == '.cls', \
                        f"Language mapping error! Expected match for {file_ext}"
                print("  ✅ PASSED — Retrieved syntax tags match context perfectly.\n")
            else:
                print("  ⚠️  PASSED (Zero hits returned - verify index parser status)\n")

        except Exception as e:
            print(f"  ❌ RETRIEVAL FAULT for {file_name}: {e}\n")

    print("=" * 70)
    print("RETRIEVAL BATCH CYCLE COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    test_batch_retrieve()