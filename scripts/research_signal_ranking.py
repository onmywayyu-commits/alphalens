"""Rank research priorities within the current archive sample."""
from .daily_brief_models import Assessment, RankedSignal, SignalCandidate

CORE_LIMIT = 3
MIN_CORE_SCORE = 7


def signal_items(candidate: SignalCandidate) -> list[str]:
    return list(dict.fromkeys(candidate.what_happened + candidate.bull_case + candidate.bear_case))


def rank_signals(candidates: list[SignalCandidate], index: dict) -> list[RankedSignal]:
    ranked = []
    for candidate in candidates:
        refs = [ref for key in candidate.what_happened + candidate.bull_case
                for ref in index[key]["citations"]]
        has_link = any(ref["source_post_id"] for ref in refs)
        has_verified_source = any(ref["source_verification"] == "verified" for ref in refs)
        evidence = Assessment(
            level=2 if has_verified_source else 1 if has_link else 0,
            reason=("支持材料中有已核验来源。" if has_verified_source else "支持材料可定位原帖，来源仍待核实。"
                    if has_link else "支持材料仅能定位本地存档。"),
        )
        refs_all = [ref for key in signal_items(candidate) for ref in index[key]["citations"]]
        assessment = [candidate.criteria.investment_importance, candidate.criteria.information_increment,
                      candidate.criteria.research_value, candidate.criteria.verifiability]
        score = evidence.level + sum(item.level for item in assessment)
        if not candidate.bull_case or score < 4:
            priority = "insufficient"
        elif score >= MIN_CORE_SCORE and evidence.level and all(item.level for item in assessment):
            priority = "core"
        elif score >= 5 and candidate.criteria.research_value.level:
            priority = "secondary"
        else:
            priority = "general"
        status_set = {ref["source_verification"] for ref in refs_all}
        status = ("records_verified" if status_set == {"verified"} else
                  "partially_verified" if "verified" in status_set else "pending")
        ranked.append(RankedSignal(
            **candidate.model_dump(), evidence_quality=evidence, score=score, priority=priority,
            source_post_ids=list(dict.fromkeys(ref["record_id"] for ref in refs_all)),
            verification_status=status,
        ))

    ordered = sorted(ranked, key=lambda item: (-item.score, -item.evidence_quality.level,
                                               -item.criteria.investment_importance.level, item.event_key))
    core = 0
    for candidate in ordered:
        if candidate.priority == "core":
            if core >= CORE_LIMIT:
                candidate.priority = "secondary"
            else:
                core += 1
    return ordered
