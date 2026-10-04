from __future__ import annotations

import json
import re
from typing import Any

from .state import QUERY_ID_PATH, load_json, save_json


DISCOVERY_PAGES = ("https://x.com/home", "https://x.com/i/bookmarks")
BUNDLE_RE = re.compile(r'https://abs\.twimg\.com/responsive-web/client-web/[^"]+?\.js')
QUERY_ID_PATTERNS = (
    re.compile(r'queryId:"([A-Za-z0-9_-]{20,})",operationName:"([^"]+)"'),
    re.compile(r'"queryId":"([A-Za-z0-9_-]{20,})","operationName":"([^"]+)"'),
    re.compile(r'operationName:"([^"]+)",queryId:"([A-Za-z0-9_-]{20,})"'),
)
CHUNK_RE = re.compile(r'"([^"]+)":"([a-f0-9]{7,8})"')
CLIENT_WEB_BASE = "https://abs.twimg.com/responsive-web/client-web"
FALLBACK_QUERY_IDS = {
    # These drift over time. They are only a last-resort bootstrap value.
    "Likes": "QK8AVO3RpcnbLPKXLAiVog",
}


class QueryIdError(RuntimeError):
    pass


def _extract_query_ids(script: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for pattern in QUERY_ID_PATTERNS:
        for match in pattern.finditer(script):
            if pattern.pattern.startswith("operationName"):
                operation, query_id = match.groups()
            else:
                query_id, operation = match.groups()
            found[operation] = query_id
    return found


def _extract_candidate_chunks(script: str, operation: str) -> set[str]:
    keywords = {operation}
    if "Like" in operation:
        keywords.add("Like")
    urls = set()
    for chunk_name, chunk_hash in CHUNK_RE.findall(script):
        if any(keyword in chunk_name for keyword in keywords):
            urls.add(f"{CLIENT_WEB_BASE}/{chunk_name}.{chunk_hash}a.js")
    return urls


async def refresh_query_ids(operations: tuple[str, ...] = ("Likes",)) -> dict[str, str]:
    try:
        import httpx
    except ImportError as exc:
        raise QueryIdError("httpx kurulu değil. Önce `python -m pip install -r requirements.txt` çalıştırın.") from exc

    found: dict[str, str] = {}
    queue: list[str] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        for page in DISCOVERY_PAGES:
            response = await client.get(page, headers={"user-agent": "Mozilla/5.0"})
            response.raise_for_status()
            queue.extend(sorted(set(BUNDLE_RE.findall(response.text))))

        while queue:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            response = await client.get(url, headers={"user-agent": "Mozilla/5.0"})
            if response.status_code != 200:
                continue
            text = response.text
            found.update(_extract_query_ids(text))
            for operation in operations:
                queue.extend(sorted(_extract_candidate_chunks(text, operation) - seen))
            if all(operation in found for operation in operations):
                break

    merged = {**FALLBACK_QUERY_IDS, **found}
    save_json(QUERY_ID_PATH, merged)
    missing = [operation for operation in operations if operation not in merged]
    if missing:
        raise QueryIdError(f"Query id bulunamadı: {', '.join(missing)}")
    return {operation: merged[operation] for operation in operations}


def load_query_ids() -> dict[str, str]:
    data: dict[str, Any] = load_json(QUERY_ID_PATH, {})
    return {**FALLBACK_QUERY_IDS, **{k: str(v) for k, v in data.items()}}
