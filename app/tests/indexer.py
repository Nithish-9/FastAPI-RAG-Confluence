#!/usr/bin/env python3

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path

import httpx


BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9001")
USER_EMAIL = os.getenv("TEST_EMAIL", "developer@company.com")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", os.getcwd())


SUPPORTED_EXTENSIONS = {
    ".py", ".go", ".java", ".js", ".jsx", ".ts", ".tsx",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".rs", ".rb", ".kt",
    ".php", ".scala", ".sh", ".html", ".css", ".scss",
    ".sql", ".toml", ".yaml", ".yml", ".json", ".xml",
    ".cls", ".trigger", ".apex", ".page", ".component",
    ".swift", ".md", ".txt", ".pdf", ".docx", ".doc"
}


# ---------------- helpers ----------------

def b64(email: str) -> str:
    return base64.b64encode(email.encode()).decode()


def sha256(val: str | bytes) -> str:
    if isinstance(val, str):
        val = val.encode()
    return hashlib.sha256(val).hexdigest()


def discover(path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    return [
        p for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


# ---------------- async core ----------------

async def create_index(client: httpx.AsyncClient, file_path: Path):
    file_bytes = file_path.read_bytes()

    resp = await client.post(
        f"{BASE_URL}/workspace/create-index",
        headers={"X-User-Email": b64(USER_EMAIL)},
        data={
            "content_id": sha256(file_bytes),
            "workspace_id": sha256(WORKSPACE_ROOT),
            "workspace_path": WORKSPACE_ROOT,
            "path": str(file_path),
            "path_id": sha256(str(file_path)),
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
        },
        files={"file_data": (file_path.name, file_bytes)},
        timeout=60,
    )

    resp.raise_for_status()
    return resp.json()


async def poll_status(client: httpx.AsyncClient, task_id: str, timeout: int):
    url = f"{BASE_URL}/workspace/index-status/{task_id}"
    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:

        resp = await client.get(url, timeout=20)
        resp.raise_for_status()

        status = resp.json().get("status")

        if status == "SUCCESS":
            return "SUCCESS"
        if status == "FAILURE":
            return "FAILURE"

        await asyncio.sleep(2)

    return "TIMEOUT"


# ---------------- worker ----------------

async def process_file(semaphore, client, file_path, args):
    async with semaphore:

        try:
            resp = await create_index(client, file_path)

            if resp.get("status") == "skipped":
                return {"file": str(file_path), "status": "SKIPPED"}

            task_id = resp.get("task_id")

            if not task_id:
                return {"file": str(file_path), "status": "FAILED"}

            status = await poll_status(client, task_id, args.timeout)

            return {
                "file": str(file_path),
                "status": status,
            }

        except Exception as e:
            return {
                "file": str(file_path),
                "status": "ERROR",
                "error": str(e),
            }


# ---------------- runner ----------------

async def run(files, args):

    semaphore = asyncio.Semaphore(args.concurrency)

    limits = httpx.Limits(
        max_connections=args.concurrency * 2,
        max_keepalive_connections=args.concurrency,
    )

    timeout = httpx.Timeout(60.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:

        tasks = [
            process_file(semaphore, client, f, args)
            for f in files
        ]

        results = []

        for coro in asyncio.as_completed(tasks):
            res = await coro
            results.append(res)

            print(f"{Path(res['file']).name} -> {res['status']}")

        return results


# ---------------- main ----------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("path")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=300)

    args = parser.parse_args()

    path = Path(args.path).resolve()

    print("=" * 60)
    print("FAST ASYNC INGESTION PIPELINE")
    print("=" * 60)
    print(f"Input        : {path}")
    print(f"Concurrency  : {args.concurrency}")
    print("=" * 60)

    files = discover(path)

    print(f"Discovered {len(files)} files")

    results = asyncio.run(run(files, args))

    out = Path(".batch_test_results.json")
    out.write_text(json.dumps(results, indent=2))

    print("\nDONE")
    print(f"Results: {out}")


if __name__ == "__main__":
    main()
