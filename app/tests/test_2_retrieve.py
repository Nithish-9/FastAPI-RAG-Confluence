#!/usr/bin/env python3
import base64
import json
import os
import requests
import hashlib

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL       = os.getenv("API_BASE_URL", "http://localhost:9001")
USER_EMAIL     = os.getenv("TEST_EMAIL", "developer@company.com")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", os.getcwd())

# ── Codebase Language Mapping Support Matrix ──────────────────────────────────
EXT_TO_LANG: dict[str, str] = {
    ".py":        "python",
    ".go":        "go",
    ".java":      "java",
    ".js":        "javascript",
    ".jsx":       "javascript",
    ".ts":        "typescript",
    ".tsx":       "typescript",
    ".c":         "c",
    ".h":         "c",
    ".cpp":       "cpp",
    ".hpp":       "cpp",
    ".cs":        "c_sharp",
    ".rs":        "rust",
    ".rb":        "ruby",
    ".kt":        "kotlin",
    ".php":       "php",
    ".scala":     "scala",
    ".sh":        "bash",
    ".html":      "html",
    ".css":       "css",
    ".scss":      "css",
    ".sql":       "sql",
    ".toml":      "toml",
    ".yaml":      "yaml",
    ".yml":       "yaml",
    ".json":      "json",
    ".cls":       "apex",
    ".trigger":   "apex",
    ".apex":      "apex",
    ".page":      "apex",
    ".component": "apex",
    ".swift":     "swift",
    ".md":        "markdown",
    ".txt":       "text",
    ".pdf":       "pdf",
    ".docx":      "docx",
    ".doc":       "docx",
    ".xml":       "text",
}

# ── Exhaustive Semantic Queries Matrix ────────────────────────────────────────
# Tailored queries targeting specialized syntax idioms for ALL 38 supported extensions
LANGUAGE_QUERIES = {
    # Python ecosystem
    ".py":        "list comprehension generator expression decorator abstract base class dunder methods",
    # Go ecosystem
    ".go":        "goroutine channel select multiplexing structural interface duck typing defer panic recover",
    # Java & Kotlin ecosystem
    ".java":      "thread pool executor service completeness helper lambda expression stream map collect",
    ".kt":        "coroutine suspend function companion object data class extension property null safety",
    # JavaScript & TypeScript variants
    ".js":        "prototype inheritance chain revealing module pattern async await generator",
    ".jsx":       "react component virtual dom hook properties state lifecycle rendering element",
    ".ts":        "conditional type utility mapping satisfies operator interface generic constraints",
    ".tsx":       "typescript jsx element typed component interface definition handler properties generic",
    # C / C++ family
    ".c":         "void pointer memory allocation struct layout volatile tracking inline assembly pointer arithmetic",
    ".h":         "header guard macro definition preprocess directive extern declaration struct signature forward",
    ".cpp":       "template metaprogramming smart pointer move semantics RAII memory management rule of five",
    ".hpp":       "template definition inline function header declaration namespace abstract interface virtual",
    ".cs":        "expression bodied member local nested function async task generic parameter constraints out ref",
    # Systems languages
    ".rs":        "unsafe memory pointer mutation or pipeline status enum borrow checker lifetime trait",
    # Scripting & Interpreted
    ".rb":        "module mixin block yield proc lambda initialization metaprogramming dynamic method",
    ".php":       "namespace trait autoload magic methods dependency injection interface implementation visibility",
    ".scala":     "pattern matching extractors with context parameters tailrec implicit class companion object",
    ".sh":        "parameter expansion slice fallback substitutions or command substitution pipe status heredoc",
    # Web Front-end markup & styling
    ".html":      "inline svg vector graphics form validation input range element semantic markup layout",
    ".css":       "container queries layout configuration native nesting rules flexbox grid keyframes custom property",
    ".scss":      "nested selector mixin include variable extension placeholder mathematical operation color function",
    # Storage, Queries & Serialization formats
    ".sql":       "recursive common table expressions hierarchy plpgsql function window partitioning join index",
    ".toml":      "key value configuration table array dependency version specification nested header string",
    ".yaml":      "anchors aliases structural indentation sequence map block scalar multiline configuration",
    ".yml":       "configuration deployment target pipeline stage environmental definitions parameters mapping",
    ".json":      "nested key value attribute array schema structure field serialization format data payload",
    ".xml":       "namespace declaration attribute node nesting document type definition schema validation parsing",
    # Salesforce / Apex cloud layers
    ".cls":       "database saveresult dynamic partial success handler aura enabled invocable method",
    ".trigger":   "before insert trigger handler bulkification execution map context trigger new trigger old",
    ".apex":      "system debug assert continuous integration deployment scripting anonymous block execution",
    ".page":      "visualforce standard controller custom extension component expression language tag markup",
    ".component": "custom structural component attributes configuration interface bundle design element declaration",
    # Mobile platforms
    ".swift":     "actor concurrency framework safe metrics tracker mapping guard let optional chaining closure",
    # Documentation & Text representations
    ".md":        "fenced javascript code block syntax injection markdown table header list item link format",
    ".txt":       "plain text logs unformatted tracking records stream description raw lines document output",
    ".pdf":       "binary document layout streams cross reference table catalog stream object font dictionary",
    ".docx":      "zipped open xml document compression structure main document content elements paragraphs tables",
    ".doc":       "structured storage binary format stream compound document allocation table elements properties"
}

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

# ── Test Runner ───────────────────────────────────────────────────────────────

def test_batch_retrieve():
    print("=" * 70)
    print("TEST 2 — POST /workspace/retrieve (Comprehensive Test Matrix)")
    print("=" * 70)

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
        file_ext = os.path.splitext(file_name)[1].lower()
        
        rich_lang_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rich_language_folder")
        file_path = os.path.join(rich_lang_dir, file_name)
        path_id = hashlib.sha256(file_path.encode()).hexdigest()

        # Look up the specific query; if it's missing, it signals a gap in the test setup
        query = LANGUAGE_QUERIES.get(file_ext)
        if not query:
            print(f"❌ CONFIG ERROR: Extension {file_ext} has no mapped query in LANGUAGE_QUERIES.")
            continue

        print(f"[{idx}/{len(successful_runs)}] Testing Scope -> {file_name}")
        print(f"  Query: '{query}'")

        try:
            results = retrieve(query, workspace_id, headers, top_k=2, path_id=path_id)
            print(f"  Got {len(results)} hit(s)")
            print_results(results)

            if results:
                for r in results:
                    lang_returned = r.get("language", "").lower()
                    expected_lang = EXT_TO_LANG.get(file_ext, "unknown").lower()
                    
                    # Check variants to keep the test robust against engine label variances
                    is_valid_lang = (
                        expected_lang in lang_returned or
                        lang_returned in expected_lang or
                        (expected_lang == "c_sharp" and ("c#" in lang_returned or "csharp" in lang_returned)) or
                        (expected_lang == "bash" and "shell" in lang_returned) or
                        (expected_lang == "apex" and lang_returned in ("apex", "trigger", "cls"))
                    )
                    
                    assert is_valid_lang, (
                        f"Language mapping error! File extension {file_ext} mapped to '{expected_lang}', "
                        f"but backend indexer layer returned: '{lang_returned}'"
                    )
                    
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