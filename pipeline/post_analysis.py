"""Build, validate, cache and load single-record research analysis."""

from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
from typing import TypeAlias

from pydantic import TypeAdapter

from scripts.brief_models import ImageReading
from scripts.brief_pipeline import PROJECT, Prompt, encode, fingerprint
from scripts.import_x_posts import classify_url
from scripts.openrouter_evidence import MAX_EXCERPT_LENGTH, SENTENCE_BREAK
from scripts.x_archive_models import Post
from scripts.x_archive_output import atomic_write

from .post_analysis_models import EvidenceSource, PostAnalysis, PostAnalysisDraft


PROMPT_VERSION = "post_analysis_v1"
PROMPT_PATH = PROJECT / "pipeline" / "prompts" / f"{PROMPT_VERSION}.md"
ANALYSIS_DIR = PROJECT / "data" / "processed" / "post_analyses"
IMAGE_READINGS_NAME = "image_readings.json"
RECORD_ID = re.compile(r"[a-zA-Z0-9_-]{1,100}")
ModelCall: TypeAlias = Callable[[Prompt, dict], tuple[PostAnalysisDraft, str, str | None]]


def read_prompt() -> Prompt:
    return Prompt(PROMPT_PATH.name, PROMPT_PATH.read_text(encoding="utf-8"),
                  PostAnalysisDraft.model_json_schema())


def read_image_readings(path: Path) -> dict[str, list[ImageReading]]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return {}
    return TypeAdapter(dict[str, list[ImageReading]]).validate_json(payload)


def build_input(post: Post, images: list[ImageReading]) -> tuple[dict, dict[str, EvidenceSource]]:
    known_media = {media.media_id for media in post.media}
    if len({image.media_id for image in images}) != len(images) or any(
        image.media_id not in known_media for image in images
    ):
        raise ValueError("视觉分析结果必须关联该存档，且图片 ID 不得重复。")
    evidence: dict[str, EvidenceSource] = {}

    def add(kind, excerpt, url, verification, content_verification, attribution, media_id=None):
        evidence[f"s-{len(evidence) + 1}"] = EvidenceSource(
            record_id=post.record_id, kind=kind, excerpt=excerpt, source_url=url,
            source_verification=verification, content_verification=content_verification,
            attribution=attribution, media_id=media_id,
        )

    author = post.author_display_name or post.source_author_handle or post.monitored_account
    body_link = classify_url(post.source_url)
    quote_link = classify_url(post.quoted_url)
    sources = (
        ("body", post.content, body_link.url if body_link.kind == "status" else None,
         post.source_verification, post.content_verification, author),
        ("quote", post.quoted_content, quote_link.url if quote_link.kind == "status" else None,
         post.quoted_source_verification, "pending", post.quoted_author_handle),
    )
    for kind, text, url, verification, content_verification, attribution in sources:
        for sentence in SENTENCE_BREAK.split(text or ""):
            for start in range(0, len(sentence), MAX_EXCERPT_LENGTH):
                if excerpt := sentence[start:start + MAX_EXCERPT_LENGTH].strip():
                    add(kind, excerpt, url, verification, content_verification, attribution)

    readings = {image.media_id: image for image in images}
    image_inputs = []
    for media in post.media:
        image = readings.get(media.media_id)
        item = {"media_id": media.media_id, "status": image.status if image else "not_read"}
        if image and image.status == "readable":
            add("image", image.observation, sources[0][2], post.source_verification,
                "pending", author, media.media_id)
            item["reading"] = image.model_dump(mode="json")
            item["evidence_id"] = f"s-{len(evidence)}"
        image_inputs.append(item)

    payload = {
        "record_id": post.record_id,
        "monitored_account": post.monitored_account,
        "author": author,
        "source_author_handle": post.source_author_handle,
        "posted_date": post.posted_date.isoformat() if post.posted_date else None,
        "posted_at": post.posted_at.isoformat() if post.posted_at else None,
        "body": {
            "text": post.content, "url": sources[0][2], "url_status": post.source_url_status,
            "text_origin": post.text_origin_status, "source_verification": post.source_verification,
            "content_verification": post.content_verification,
        },
        "quote": {
            "text": post.quoted_content, "url": sources[1][2], "url_status": post.quoted_url_status,
            "author": post.quoted_author_handle, "text_origin": post.quoted_text_origin_status,
            "source_verification": post.quoted_source_verification,
        },
        "images": image_inputs,
        "evidence": {key: value.model_dump(mode="json") for key, value in evidence.items()},
    }
    return payload, evidence


def checked_evidence(
    draft: PostAnalysisDraft, evidence: dict[str, EvidenceSource], payload: dict,
) -> dict[str, EvidenceSource]:
    used = {}
    for point in draft.cited_points():
        if len(set(point.evidence_ids)) != len(point.evidence_ids):
            raise ValueError("同一分析条目重复引用了证据 ID。")
        for key in point.evidence_ids:
            source = evidence.get(key)
            if source is None or source.record_id != payload["record_id"]:
                raise ValueError("分析引用了不属于该存档的证据 ID。")
            used[key] = source
    if draft.author_opinion and not any(used[key].kind == "body" for key in draft.author_opinion.evidence_ids):
        raise ValueError("作者观点必须至少引用一项正文证据。")
    corpus = payload["body"]["text"] + "\n" + (payload["quote"]["text"] or "")
    for ticker in draft.related_tickers:
        if not re.search(rf"(?<![A-Za-z0-9_$])\$?{re.escape(ticker)}(?![A-Za-z0-9_])", corpus):
            raise ValueError("相关股票代码未在存档正文或引用中出现。")
    return used


def _record_folder(root: Path, record_id: str) -> Path:
    if not RECORD_ID.fullmatch(record_id):
        raise ValueError("存档记录 ID 格式无效。")
    return root / record_id


@contextmanager
def _lock(path: Path):
    # An OS lock is released when the process exits, including after interruption.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            from msvcrt import LK_NBLCK, locking
            acquire = lambda: locking(handle.fileno(), LK_NBLCK, 1)
        else:
            from fcntl import LOCK_EX, LOCK_NB, flock
            acquire = lambda: flock(handle.fileno(), LOCK_EX | LOCK_NB)
        try:
            acquire()
        except OSError as exc:
            raise ValueError("这条存档正在分析，请稍后重新执行。") from exc
        yield


def _read_current(
    path: Path, payload: dict, evidence: dict[str, EvidenceSource], input_hash: str,
) -> PostAnalysis:
    item = PostAnalysis.model_validate_json(path.read_bytes())
    record_id = payload["record_id"]
    if (item.record_id != record_id or item.source_record_ids != [record_id]
            or item.input_sha256 != input_hash or item.cache_key != path.stem
            or item.evidence != checked_evidence(item.analysis, evidence, payload)):
        raise ValueError("已保存分析与当前存档或证据不匹配。")
    return item


def analyze_post(
    post: Post, images: list[ImageReading], prompt: Prompt, root: Path,
    provider: str, model: str, generate: ModelCall,
) -> tuple[PostAnalysis, bool]:
    payload, evidence = build_input(post, images)
    input_hash = fingerprint(payload)
    prompt_hash = sha256(prompt.text.encode("utf-8")).hexdigest()
    key = fingerprint({
        "input": input_hash, "prompt": prompt_hash, "schema": fingerprint(prompt.schema),
        "provider": provider, "model": model, "version": PROMPT_VERSION,
    })
    target = _record_folder(root, post.record_id) / f"{key}.json"
    if target.is_file():
        return _read_current(target, payload, evidence, input_hash), True

    with _lock(target.with_suffix(".lock")):
        if target.is_file():
            return _read_current(target, payload, evidence, input_hash), True
        draft, actual_model, request_id = generate(prompt, payload)
        used = checked_evidence(draft, evidence, payload)
        readable = sum(image["status"] == "readable" for image in payload["images"])
        media_count = len(post.media)
        media_status = ("no_media" if media_count == 0 else "analyzed" if readable == media_count
                        else "partial" if readable else "not_analyzed")
        outcome = PostAnalysis(
            record_id=post.record_id, source_record_ids=[post.record_id],
            analysis=draft, evidence=used, media_analysis_status=media_status,
            prompt_version=PROMPT_VERSION, prompt_sha256=prompt_hash, input_sha256=input_hash,
            cache_key=key, provider=provider, requested_model=model, model_name=actual_model,
            request_id=request_id, generated_at=datetime.now(timezone.utc),
        )
        atomic_write(target, encode(outcome))
        return outcome, False


def latest_analysis(root: Path, post: Post, images: list[ImageReading], prompt: Prompt) -> PostAnalysis | None:
    folder = _record_folder(root, post.record_id)
    if not folder.is_dir():
        return None
    payload, evidence = build_input(post, images)
    input_hash = fingerprint(payload)
    prompt_hash = sha256(prompt.text.encode("utf-8")).hexdigest()
    results = []
    for path in folder.glob("*.json"):
        try:
            item = _read_current(path, payload, evidence, input_hash)
        except (ValueError, OSError):
            continue
        expected_key = fingerprint({
            "input": input_hash, "prompt": prompt_hash, "schema": fingerprint(prompt.schema),
            "provider": item.provider, "model": item.requested_model, "version": PROMPT_VERSION,
        })
        if item.prompt_version == PROMPT_VERSION and item.prompt_sha256 == prompt_hash and item.cache_key == expected_key:
            results.append(item)
    return max(results, key=lambda item: item.generated_at, default=None)
