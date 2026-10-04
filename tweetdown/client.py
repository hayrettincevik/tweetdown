from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from .models import AuthBundle, TweetRecord
from .query_ids import load_query_ids, refresh_query_ids
from .state import BASE_DIR, clear_state, load_state, save_state


API_BASE_URL = "https://x.com/i/api/graphql"
LEGACY_API_BASE_URL = "https://api.twitter.com/graphql"
PUBLIC_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16c"
    "HjhLTvJu4FA33AGWWjCpTnA"
)


class ExportStopped(RuntimeError):
    pass


class XRequestError(RuntimeError):
    pass


class MissingVariablesError(XRequestError):
    """X rejected the query because one or more GraphQL variables were missing.

    The missing variable names are parsed from X's validation error so the
    export loop can inject them and retry without any code change.
    """

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__("Eksik GraphQL değişkenleri: " + ", ".join(names))


def _missing_variables(errors: Any) -> list[str]:
    names: list[str] = []
    for error in errors or []:
        if not isinstance(error, dict):
            continue
        code = error.get("code") or (error.get("extensions") or {}).get("code")
        if code != "GRAPHQL_VALIDATION_FAILED":
            continue
        path = error.get("path") or []
        if len(path) >= 2 and path[0] == "variable" and isinstance(path[1], str):
            names.append(path[1])
    return list(dict.fromkeys(names))


ProgressCallback = Callable[[str], None]
StopCallback = Callable[[], bool]


def _encode_param(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _features() -> dict[str, bool]:
    return {
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "tweetypie_unmention_optimization_enabled": True,
        "vibe_api_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_media_download_video_enabled": False,
        "responsive_web_enhance_cards_enabled": False,
    }


def _field_toggles() -> dict[str, bool]:
    return {
        "withArticleRichContentState": True,
        "withArticlePlainText": False,
        "withGrokAnalyze": False,
    }


def build_likes_url(
    query_id: str,
    user_id: str,
    cursor: str | None,
    count: int,
    extra_variables: dict[str, Any] | None = None,
) -> str:
    variables: dict[str, Any] = {
        "userId": user_id,
        "count": count,
        "includePromotedContent": False,
        "withBirdwatchNotes": False,
        "withClientEventToken": False,
        "withVoice": True,
        "withV2Timeline": True,
        # X's current Likes query declares these as required; omitting any of
        # them returns HTTP 422 GRAPHQL_VALIDATION_FAILED ("must be defined").
        "withReactionsMetadata": False,
        "withReactionsPerspective": False,
        "withDownvotePerspective": False,
    }
    # Any further variables X demands at runtime are injected here (see the
    # self-healing retry in export_likes_async).
    if extra_variables:
        variables.update(extra_variables)
    if cursor:
        variables["cursor"] = cursor
    params = urlencode(
        {
            "variables": _encode_param(variables),
            "features": _encode_param(_features()),
            "fieldToggles": _encode_param(_field_toggles()),
        }
    )
    return f"{API_BASE_URL}/{query_id}/Likes?{params}"


def _headers(auth: AuthBundle) -> dict[str, str]:
    return {
        "authorization": f"Bearer {PUBLIC_BEARER_TOKEN}",
        "cookie": f"auth_token={auth.auth_token}; ct0={auth.ct0};",
        "x-csrf-token": auth.ct0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "accept": "*/*",
        "user-agent": "Mozilla/5.0",
        "referer": "https://x.com/",
        "origin": "https://x.com",
    }


def _unwrap_tweet_result(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    if result.get("__typename") in {"Tweet", "TweetWithVisibilityResults"}:
        if "tweet" in result:
            return _unwrap_tweet_result(result["tweet"])
        return result
    if "tweet" in result:
        return _unwrap_tweet_result(result["tweet"])
    return None


def _iter_entries(node: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if "entryId" in node and "content" in node:
            entries.append(node)
        for value in node.values():
            entries.extend(_iter_entries(value))
    elif isinstance(node, list):
        for item in node:
            entries.extend(_iter_entries(item))
    return entries


def _extract_tweet_results(content: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    item_content = content.get("itemContent")
    if isinstance(item_content, dict):
        result = _unwrap_tweet_result((item_content.get("tweet_results") or {}).get("result"))
        if result:
            results.append(result)
    items = ((content.get("items") or []) if isinstance(content.get("items"), list) else [])
    for item in items:
        nested = ((item.get("item") or {}).get("itemContent") or {})
        result = _unwrap_tweet_result((nested.get("tweet_results") or {}).get("result"))
        if result:
            results.append(result)
    return results


def _extract_cursor(entry: dict[str, Any]) -> str | None:
    entry_id = entry.get("entryId", "")
    content = entry.get("content") or {}
    if entry_id.startswith("cursor-bottom-"):
        return content.get("value")
    if content.get("cursorType") == "Bottom":
        return content.get("value")
    return None


def _author(result: dict[str, Any]) -> dict[str, Any]:
    user_result = (((result.get("core") or {}).get("user_results") or {}).get("result") or {})
    legacy = user_result.get("legacy") or {}
    # X moved screen_name/name under `core` and the avatar under `avatar`; older
    # responses still carry them in `legacy`.
    core = user_result.get("core") or {}
    avatar = user_result.get("avatar") or {}
    return {
        "id_str": user_result.get("rest_id") or legacy.get("id_str"),
        "screen_name": core.get("screen_name") or legacy.get("screen_name"),
        "name": core.get("name") or legacy.get("name"),
        "profile_image_url_https": avatar.get("image_url") or legacy.get("profile_image_url_https"),
    }


def _text(result: dict[str, Any]) -> str:
    note = (((result.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {})
    note_text = note.get("text")
    if note_text:
        return note_text
    return (result.get("legacy") or {}).get("full_text") or ""


def _media_urls(legacy: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    entities = legacy.get("extended_entities") or legacy.get("entities") or {}
    for media in entities.get("media", []) or []:
        if media.get("media_url_https"):
            urls.append(media["media_url_https"])
        video_info = media.get("video_info") or {}
        variants = video_info.get("variants") or []
        mp4s = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
        if mp4s:
            best = max(mp4s, key=lambda v: v.get("bitrate", 0))
            urls.append(best["url"])
    return list(dict.fromkeys(urls))


def _expanded_urls(legacy: dict[str, Any]) -> list[str]:
    urls = []
    for item in ((legacy.get("entities") or {}).get("urls") or []):
        expanded = item.get("expanded_url") or item.get("url")
        if expanded:
            urls.append(expanded)
    return list(dict.fromkeys(urls))


def _tweet_record(result: dict[str, Any]) -> TweetRecord | None:
    legacy = result.get("legacy") or {}
    tweet_id = result.get("rest_id") or legacy.get("id_str")
    if not tweet_id:
        return None
    author = _author(result)
    username = author.get("screen_name")
    return TweetRecord(
        tweet_id=str(tweet_id),
        url=f"https://x.com/{username or 'i'}/status/{tweet_id}",
        text=_text(result),
        created_at=legacy.get("created_at"),
        author_id=legacy.get("user_id_str") or author.get("id_str"),
        author_username=username,
        author_name=author.get("name"),
        author_avatar_url=author.get("profile_image_url_https"),
        media_urls=_media_urls(legacy),
        expanded_urls=_expanded_urls(legacy),
        reply_count=legacy.get("reply_count"),
        retweet_count=legacy.get("retweet_count"),
        favorite_count=legacy.get("favorite_count"),
        quote_count=legacy.get("quote_count"),
        raw_json=result,
    )


def parse_likes_page(payload: dict[str, Any]) -> tuple[list[TweetRecord], str | None]:
    tweets: list[TweetRecord] = []
    seen: set[str] = set()
    bottom_cursor: str | None = None
    for entry in _iter_entries(payload):
        bottom_cursor = bottom_cursor or _extract_cursor(entry)
        for result in _extract_tweet_results(entry.get("content") or {}):
            record = _tweet_record(result)
            if record and record.tweet_id not in seen:
                seen.add(record.tweet_id)
                tweets.append(record)
    return tweets, bottom_cursor


def _raise_for_missing_variables(response: Any) -> None:
    try:
        payload = response.json()
    except ValueError:
        return
    if isinstance(payload, dict):
        missing = _missing_variables(payload.get("errors"))
        if missing:
            raise MissingVariablesError(missing)


async def _fetch_page(
    client: Any,
    auth: AuthBundle,
    query_id: str,
    cursor: str | None,
    count: int,
    extra_variables: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any], list[TweetRecord], str | None]:
    url = build_likes_url(query_id, auth.user_id, cursor, count, extra_variables)
    response = await client.get(url, headers=_headers(auth))
    if response.status_code == 404:
        # Some X installations still answer under api.twitter.com.
        response = await client.get(url.replace(API_BASE_URL, LEGACY_API_BASE_URL), headers=_headers(auth))
    if response.status_code in (401, 403):
        raise XRequestError("X oturumu reddetti. Cookie/login bilgileri geçersiz veya süresi dolmuş.")
    if response.status_code == 429:
        reset = response.headers.get("x-rate-limit-reset")
        detail = f" Rate limit reset: {reset}" if reset else ""
        raise XRequestError("X rate limit verdi. Bir süre sonra kaldığınız yerden devam edin." + detail)
    if response.status_code == 404:
        raise XRequestError("Likes GraphQL query id eskimiş görünüyor.")
    if response.status_code == 422:
        # Missing/invalid GraphQL variable: let the caller inject it and retry.
        _raise_for_missing_variables(response)
    if response.status_code >= 400:
        raise XRequestError(f"X HTTP {response.status_code}: {response.text[:240]}")
    payload = response.json()
    if isinstance(payload, dict) and payload.get("errors") and not payload.get("data"):
        missing = _missing_variables(payload["errors"])
        if missing:
            raise MissingVariablesError(missing)
        message = "; ".join(error.get("message", "?") for error in payload["errors"])
        raise XRequestError(f"X GraphQL hatası: {message}")
    tweets, next_cursor = parse_likes_page(payload)
    return response, payload, tweets, next_cursor


async def export_likes_async(
    *,
    auth: AuthBundle,
    output_path: Path,
    include_raw: bool = False,
    resume: bool = True,
    max_pages: int | None = None,
    page_delay: float = 1.0,
    progress: ProgressCallback | None = None,
    should_stop: StopCallback | None = None,
) -> dict[str, Any]:
    try:
        import httpx
    except ImportError as exc:
        raise XRequestError("httpx kurulu değil. Önce `python -m pip install -r requirements.txt` çalıştırın.") from exc

    def log(message: str) -> None:
        if progress:
            progress(message)

    query_ids = load_query_ids()
    if "Likes" not in query_ids:
        log("X query id keşfediliyor...")
        query_ids.update(await refresh_query_ids(("Likes",)))
    query_id = query_ids["Likes"]

    state = load_state() if resume else {}
    cursor = state.get("next_cursor") if resume else None
    existing = state.get("tweets", []) if resume else []
    raw_pages = state.get("raw_pages", []) if resume and include_raw else []
    seen_ids = {item.get("tweet_id") for item in existing}
    pages_done = int(state.get("pages_done", 0)) if resume else 0
    pages_this_run = 0
    finished = False
    extra_vars: dict[str, Any] = {}
    log("Kaldığı yerden devam ediliyor..." if cursor else "Beğeniler baştan okunuyor...")

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        while True:
            if should_stop and should_stop():
                raise ExportStopped("İndirme durduruldu. Daha sonra devam edebilirsiniz.")
            if max_pages is not None and pages_this_run >= max_pages:
                break

            response = payload = None
            tweets = []
            next_cursor = None
            refreshed_qid = False
            for _attempt in range(10):
                try:
                    response, payload, tweets, next_cursor = await _fetch_page(
                        client, auth, query_id, cursor, 20, extra_vars
                    )
                    break
                except MissingVariablesError as exc:
                    added = [name for name in exc.names if name not in extra_vars]
                    for name in exc.names:
                        extra_vars[name] = False
                    if not added:
                        raise
                    log("X ek değişken istedi, ekleniyor: " + ", ".join(added))
                    continue
                except XRequestError as exc:
                    if "query id" in str(exc).lower() and not refreshed_qid:
                        refreshed_qid = True
                        log("Query id yenileniyor...")
                        query_id = (await refresh_query_ids(("Likes",)))["Likes"]
                        continue
                    raise
            else:
                raise XRequestError(
                    "İstek, otomatik düzeltmelere rağmen başarısız oldu. "
                    "X API'si beklenmedik bir yanıt veriyor olabilir."
                )

            fresh = [tweet for tweet in tweets if tweet.tweet_id not in seen_ids]
            for tweet in fresh:
                seen_ids.add(tweet.tweet_id)
                existing.append(tweet.to_json(include_raw=include_raw))
            if include_raw:
                raw_pages.append(
                    {
                        "cursor_in": cursor,
                        "cursor_out": next_cursor,
                        "http_status": response.status_code,
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "json": payload,
                    }
                )
            pages_done += 1
            pages_this_run += 1
            save_state(
                {
                    "user_id": auth.user_id,
                    "next_cursor": next_cursor,
                    "pages_done": pages_done,
                    "tweet_count": len(existing),
                    "tweets": existing,
                    "raw_pages": raw_pages if include_raw else [],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            log(f"Sayfa {pages_done}: {len(fresh)} yeni beğeni, toplam {len(existing)}")
            if not next_cursor or not tweets or not fresh:
                finished = True
                break
            cursor = next_cursor
            await asyncio.sleep(page_delay)

    payload = {
        "metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user_id": auth.user_id,
            "tweet_count": len(existing),
            "pages": pages_done,
            "complete": finished,
            "source": "x_graphql_likes",
        },
        "tweets": existing,
        "raw_pages": raw_pages if include_raw else [],
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if finished:
        clear_state()
    else:
        # Stopped by max_pages: keep the cursor so the next run can resume.
        log("Max sayfa sınırına ulaşıldı; ilerleme saklandı, kaldığı yerden devam edebilirsiniz.")
    log(f"JSON kaydedildi: {output_path}")
    return payload


def export_likes(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(export_likes_async(**kwargs))


def default_output_path() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return BASE_DIR.resolve() / f"x_likes_{stamp}.json"
