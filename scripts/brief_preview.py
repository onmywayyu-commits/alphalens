"""Local dashboard projection for archived brief runs."""

from collections import defaultdict
from pathlib import Path

from .brief_models import BRIEF_ARCHIVE_BUCKETS
from .brief_pipeline import coverage, evidence_index, load_run
from .daily_brief_v2 import preview_data, read_edition
from .x_archive_models import ImportResult


def preview_runs(root: Path, current: ImportResult, image_hashes: dict[str, str]) -> list[dict]:
    current_dates = defaultdict(list)
    for post in current.posts:
        current_dates[post.posted_date].append(post)
    latest: dict[str, dict] = {}
    for bucket in BRIEF_ARCHIVE_BUCKETS.values():
        for entry in sorted((root / bucket).glob("*/*/run.json")):
            run, packet, extraction, brief = load_run(entry.parent)
            if packet.records != current_dates.get(packet.date):
                continue
            if any(image_hashes.get(image.media_id) != image.sha256 for image in packet.images):
                continue
            day = packet.date.isoformat()
            previous = latest.get(day)
            # Prefer API results, then local replies, then rehearsals. Keep the latest per kind.
            if previous and (run.mode == previous["mode"] and previous["generated_at"] >= run.generated_at.isoformat()):
                continue
            latest[day] = {
                "date": day, "run_id": run.run_id, "mode": run.mode,
                "provider": run.provider, "model": run.model, "generated_at": run.generated_at.isoformat(),
                "input_sha256": run.input_sha256, "extraction_sha256": run.extraction_sha256,
                "extract_prompt": run.extract_prompt.name, "report_prompt": run.report_prompt.name,
                "coverage": coverage(packet),
                "records": [
                    {"record_id": post.record_id, "excel_row": post.excel_row,
                     "source_verification": post.source_verification}
                    for post in packet.records
                ],
                "image_states": {
                    status: sum(image.status == status for row in extraction.posts for image in row.images)
                    for status in ("not_read", "unreadable", "readable")
                },
                "brief": brief.model_dump(mode="json", exclude={
                    "schema_version", "date", "input_sha256", "extraction_sha256",
                }),
                "evidence": evidence_index(packet, extraction),
            }
    editions = {}
    for entry in sorted((root / "v2").glob("*/*/edition.json")):
        meta, packet, extraction, report = read_edition(entry.parent)
        if packet.records != current_dates.get(packet.date):
            continue
        if any(image_hashes.get(image.media_id) != image.sha256 for image in packet.images):
            continue
        day = packet.date.isoformat()
        previous = editions.get(day)
        if previous and (previous["mode"] == "api", previous["generated_at"]) >= (
            report.generation_mode == "api", report.generated_at.isoformat(),
        ):
            continue
        editions[day] = preview_data(meta, packet, extraction, report)

    groups: dict[str, str] = {}
    for relation in current.relations:
        if relation.kind in {"numbered_thread_candidate", "shared_post_id"}:
            group = relation.record_ids[0]
            groups.update((record_id, group) for record_id in relation.record_ids)
    previous = None
    for edition in (editions[day] for day in sorted(editions)):
        for theme in edition["daily_v2"]["research_themes"]:
            refs = [ref for key in theme["item_ids"] for ref in edition["evidence"][key]["citations"]]
            theme["source_count"] = len({groups.get(ref["record_id"], ref["source_post_id"] or ref["record_id"])
                                         for ref in refs})
            earlier = next((item for item in previous["daily_v2"]["research_themes"]
                            if item["theme_key"] == theme["theme_key"]), None) if previous else None
            if earlier:
                old_ids = source_post_ids(previous, earlier["item_ids"], groups)
                new_ids = source_post_ids(edition, theme["item_ids"], groups)
                if old_ids and new_ids:
                    theme["history"] = {"date": previous["date"], "new_source_count": len(new_ids - old_ids)}
        previous = edition
    latest.update(editions)
    return sorted(latest.values(), key=lambda item: item["date"], reverse=True)



def source_post_ids(edition: dict, item_ids: list[str], groups: dict[str, str]) -> set[str]:
    return {
        groups.get(ref["record_id"], ref["source_post_id"])
        for key in item_ids for ref in edition["evidence"][key]["citations"]
        if ref["source_post_id"]
    }
