from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.brief_pipeline import evidence_index
from scripts.daily_brief_models import BriefDraft
from scripts.daily_brief_v2 import archive_edition, build_report, read_edition, request_editorial
from test_brief_pipeline import replies, sample


def draft_for(count=1):
    assessment = {"level": 2, "reason": "有具体可查的收入指标。"}
    return BriefDraft.model_validate({
        "lead_signal_key": "claim-1",
        "lead_insight": {"title": "核心观察", "explanation": "验证收入变化。", "item_ids": ["item-1"],
                         "related_sectors": [], "related_tickers": []},
        "candidates": [
            {"event_key": f"claim-{index}", "theme_key": "test", "title": f"测试 {index}",
             "what_happened": ["item-1"], "bull_case": ["item-1"], "bear_case": [],
             "why_it_matters": "验证对收入的影响。", "investment_implication": "跟踪收入。",
             "risks": "当前样本不足。", "next_research_action": "查最新财报。", "related_tickers": [],
             "related_sectors": [], "selection_reason": "与收入相关。",
             "criteria": dict.fromkeys(("investment_importance", "information_increment", "research_value",
                                        "verifiability"), assessment)}
            for index in range(1, count + 1)
        ],
        "research_themes": [], "other_updates": [], "limitations": [],
    })


class DailyBriefV2Tests(unittest.TestCase):
    def setUp(self):
        self.packet = sample(date(2026, 11, 20), "1000")
        self.extraction, _ = replies(self.packet)

    def test_replay_archive_preserves_provenance_and_caps_core_signals(self):
        draft = draft_for(4)
        with TemporaryDirectory() as directory:
            path = archive_edition(Path(directory), self.packet, self.extraction, draft, "replay", "local-test")
            _, packet, extraction, report = read_edition(path)
            self.assertEqual(path, archive_edition(Path(directory), self.packet, self.extraction, draft, "replay", "local-test"))
            self.assertEqual(packet, self.packet)
            self.assertEqual(extraction, self.extraction)
            self.assertEqual(report.generation_mode, "replay")
            self.assertEqual([item.priority for item in report.ranked_signals], ["core"] * 3 + ["secondary"])
            self.assertEqual(report.top_signals[0].source_post_ids, ["rec-1000"])
            self.assertEqual(report.top_signals[0].verification_status, "pending")
            markdown = (path / "brief.md").read_text(encoding="utf-8")
            self.assertIn("[item-1](#evidence-item-1)", markdown)
            self.assertIn('<a id="evidence-item-1"></a>', markdown)
            self.assertIn("本次样本未提供反方证据", markdown)

    def test_rejects_unknown_inferred_and_duplicate_event_evidence(self):
        now = datetime.now(timezone.utc)
        draft = draft_for(2)
        draft.candidates[1].event_key = "claim-1"
        with self.assertRaisesRegex(ValueError, "相同事件"):
            build_report(self.packet, self.extraction, draft, "replay", "test", now)
        draft = draft_for()
        draft.candidates[0].bull_case = ["forged-id"]
        with self.assertRaisesRegex(ValueError, "不存在的证据"):
            build_report(self.packet, self.extraction, draft, "replay", "test", now)
        self.extraction.posts[0].items[0].category = "inference"
        with self.assertRaisesRegex(ValueError, "不能使用模型推断"):
            build_report(self.packet, self.extraction, draft_for(), "replay", "test", now)

    def test_editorial_request_uses_day_evidence_allowlist_and_repairs_invalid_ids(self):
        class Provider:
            def __init__(self):
                self.calls = 0

            def request_structured(self, prompt, _name, data, model, _limit):
                self.calls += 1
                self_schema = prompt.schema["$defs"]["SignalCandidate"]["properties"]
                assert self_schema["bull_case"]["items"]["enum"] == ["item-1"]
                assert data["allowed_item_ids"] == ["item-1"]
                assert data["evidence"]["item-1"]["citations"][0]["record_id"] == "rec-1000"
                draft = draft_for()
                if self.calls == 1:
                    draft.candidates[0].bull_case = ["forged-id"]
                else:
                    assert "不存在的证据" in data["validation_error"]
                return model.model_validate(draft)

        provider = Provider()
        result = request_editorial(provider, self.packet, self.extraction)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(result.candidates[0].bull_case, list(evidence_index(self.packet, self.extraction)))

    def test_optional_editorial_fields_keep_legacy_payloads_unchanged(self):
        original = draft_for()
        payload = original.model_dump(mode="json")
        candidate = payload["candidates"][0]
        for field in ("thesis_status", "core_judgment", "company_scope"):
            self.assertNotIn(field, candidate)
        candidate.update(thesis_status="to_validate", core_judgment="需验证订单回升。",
                         company_scope={"direct": ["Phison"], "value_chain": ["SanDisk"]})
        updated = BriefDraft.model_validate(payload)
        self.assertEqual(updated.model_dump(mode="json"), payload)
        with TemporaryDirectory() as directory:
            path = archive_edition(Path(directory), self.packet, self.extraction, updated, "replay", "local-test")
            _, _, _, report = read_edition(path)
            self.assertEqual(report.top_signals[0].thesis_status, "to_validate")
            self.assertEqual(report.top_signals[0].company_scope.direct, ["Phison"])
