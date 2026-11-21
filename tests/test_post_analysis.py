import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx
import openai

from pipeline.post_analysis import analyze_post, build_input, latest_analysis, read_prompt
from pipeline.post_analysis_models import PostAnalysisDraft
from scripts.brief_models import ImageReading
from scripts.openrouter_brief import OpenRouterBriefProvider
from scripts.prepare_archive_preview import prepare_preview
from scripts.x_archive_models import ImportResult, Media, Post


def fixture_post():
    return Post(
        record_id="archive-test", excel_row=2, monitored_account="@Monitor", author_display_name="测试作者",
        source_author_handle="@Test", posted_date="2026-11-20", posted_date_raw="26.11.20",
        content="测试作者转述了另一位发言人的看法。\n\n后续仍需验证 $NVDA 订单变化。",
        source_url="https://x.com/Test/status/123", source_url_status="status", source_verification="verified",
        quoted_content="引用作者表达不同看法。", quoted_url="https://x.com/Quoted/status/456",
        quoted_url_status="status", quoted_author_handle="@Quoted", quoted_text_origin_status="unknown_manual_entry",
        quoted_source_verification="pending", media=[Media(
            media_id="media-test", original_filename="x.png", availability="missing", exists=False,
            excel_row=2, position=1,
        )],
    )


def fixture_draft():
    point = {"text": "用于验证结构和证据的测试文本。", "evidence_ids": ["s-1"]}
    return PostAnalysisDraft.model_validate({
        "research_value": "actionable", "summary": point, "author_opinion": point, "why_it_matters": point,
        "investment_implication": point, "counterevidence": [],
        "risk_hypotheses": [point], "next_research_actions": [point], "related_sectors": ["测试行业"],
        "related_companies": ["测试公司"], "related_tickers": ["NVDA"],
        "claim_annotations": [{**point, "category": "fact", "attribution": "测试作者转述的发言人"}],
    })


class TestPostAnalysis(unittest.TestCase):
    def setUp(self):
        self.post = fixture_post()
        self.draft = fixture_draft()
        self.prompt = read_prompt()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def generate(self, prompt, payload):
        return self.draft, "returned/test-model", "http-test-request"

    def analyze(self, post=None, *, prompt=None, images=None, generate=None):
        return analyze_post(
            post or self.post, images or [], prompt or self.prompt, self.root,
            OpenRouterBriefProvider.name, "test-model", generate or self.generate,
        )

    def test_evidence_links_remain_distinct_and_media_requires_reading(self):
        payload, evidence = build_input(self.post, [])
        self.assertEqual(payload["body"]["text"], self.post.content)
        quote = next(item for item in evidence.values() if item.kind == "quote")
        self.assertEqual((quote.source_url, quote.attribution, quote.source_verification),
                         ("https://x.com/Quoted/status/456", "@Quoted", "pending"))
        self.assertNotIn("original_filename", payload["images"][0])
        self.assertFalse(any(item.kind == "image" for item in evidence.values()))
        image = ImageReading(media_id="media-test", status="readable", observation="经核对的测试图片观察。")
        _, visual_evidence = build_input(self.post, [image])
        self.assertTrue(any(item.kind == "image" and item.media_id == image.media_id
                            for item in visual_evidence.values()))

    def test_cache_preserves_versions_and_skips_model_on_hit(self):
        first, cached = self.analyze()
        self.assertFalse(cached)
        self.assertEqual((first.model_name, first.request_id, first.fact_verification, first.media_analysis_status),
                         ("returned/test-model", "http-test-request", "unverified", "not_analyzed"))

        def unexpected(*_):
            self.fail("缓存命中不应再次调用生成器。")

        self.assertEqual(self.analyze(generate=unexpected), (first, True))
        self.assertEqual(latest_analysis(self.root, self.post, [], self.prompt), first)
        updated = self.post.model_copy(update={"quoted_content": "更新测试引用。"})
        self.assertIsNone(latest_analysis(self.root, updated, [], self.prompt))
        self.assertFalse(self.analyze(updated)[1])
        self.assertFalse(self.analyze(prompt=replace(self.prompt, text=self.prompt.text + "\n测试修订"))[1])
        self.assertFalse(self.analyze(images=[ImageReading(
            media_id="media-test", status="readable", observation="已分析的测试图片。",
        )])[1])
        self.assertEqual(len(list(self.root.rglob("*.json"))), 4)

    def test_foreign_evidence_and_quote_only_author_claim_are_rejected(self):
        candidates = [
            ("summary", ["s-999"], "不属于该存档"),
            ("author_opinion", ["s-3"], "引用一项正文证据"),
            ("why_it_matters", ["s-1", "s-1"], "重复引用"),
        ]
        for attr, references, reason in candidates:
            with self.subTest(attr=attr):
                self.draft = fixture_draft()
                getattr(self.draft, attr).evidence_ids = references
                with self.assertRaisesRegex(ValueError, reason):
                    self.analyze()
                self.assertEqual(list(self.root.rglob("*.json")), [])

    def test_preview_exports_only_generated_result_for_current_input(self):
        analysis, _ = self.analyze()
        next_post = self.post.model_copy(update={"record_id": "archive-next", "excel_row": 3, "media": []})
        archive = ImportResult(
            source_file="test.xlsx", sheet="Sheet1", workbook_sha256="test", data_rows=2,
            embedded_media_files=0, posts=[self.post, next_post], relations=[], issues=[],
        )
        target = self.root / "preview"
        before = self.post.model_dump()
        prepare_preview(archive, self.root, {"accounts": []}, target, self.root / "manifest.json",
                        analysis_dir=self.root)
        posts = json.loads((target / "dashboard.json").read_bytes())["posts"]
        self.assertEqual(posts[0]["post_analysis"], analysis.model_dump(mode="json"))
        self.assertEqual(posts[0]["archive"]["analysis_status"], "analyzed")
        self.assertNotIn("post_analysis", posts[1])
        self.assertEqual(self.post.model_dump(), before)

    def test_existing_client_uses_strict_schema_and_returns_provider_metadata(self):
        def respond(request):
            body = json.loads(request.content)
            self.assertTrue(body["response_format"]["json_schema"]["strict"])
            self.assertEqual(body["model"], "test-model")
            self.assertEqual(json.loads(body["messages"][1]["content"])["record_id"], self.post.record_id)
            return httpx.Response(200, json={
                "id": "http-test-request", "model": "returned/test-model", "object": "chat.completion", "created": 0,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": self.draft.model_dump_json()}}],
            })

        provider = object.__new__(OpenRouterBriefProvider)
        provider.model = "test-model"
        provider.client = openai.OpenAI(api_key="test-transport-only", base_url="https://example.invalid",
                                        http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        with provider:
            result, _ = self.analyze(generate=lambda prompt, payload: provider.request_structured_with_metadata(
                prompt, "post_analysis_test", payload, PostAnalysisDraft, 8192,
            ))
        self.assertEqual(result.model_name, "returned/test-model")
        self.assertEqual(result.request_id, "http-test-request")


if __name__ == "__main__":
    unittest.main()
