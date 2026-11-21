import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from scripts.brief_models import (
    CitedPoint, DailyBrief, Extraction, ExtractItem, Hypothesis, ImageReading, ImageReference,
    InputImage, InputPacket, PostExtraction, TextReference,
)
from scripts.brief_pipeline import (
    RehearsalProvider, ReplyProvider, archive_run, coverage, encode, evidence_index, fingerprint, load_run,
    prepare_input, validate_brief, validate_extraction,
)
from scripts.brief_preview import preview_runs
from scripts.run_brief import compare
from scripts.x_archive_models import ImportResult, Media, Post


def sample(day: date, source_id: str, with_image: bool = False) -> InputPacket:
    post = Post(
        record_id="rec-" + source_id, excel_row=2, post_id=source_id,
        monitored_account="@fixture", author_display_name="离线测试样例", source_author_handle="@fixture",
        posted_date=day, posted_date_raw=str(day), content="仅供测试的存档原句。",
        source_url="https://x.com/fixture/status/" + source_id, source_url_status="status",
        source_verification="pending", quoted_content=None, quoted_url=None, quoted_url_status="missing",
        quoted_author_handle=None, quoted_text_origin_status=None, quoted_source_verification="missing",
        media=[
            Media(media_id="image-fixture", original_filename="test.jpg", excel_row=2, position=1,
                  exists=True, availability="available", local_path="media/test.jpg"),
        ] if with_image else [],
    )
    return InputPacket(
        date=day, archive_sha256="a" * 64, workbook_sha256="c" * 64, records=[post],
        images=[InputImage(media_id="image-fixture", local_path="media/test.jpg", sha256="b" * 64)] if with_image else [],
    )


def replies(packet: InputPacket) -> tuple[Extraction, DailyBrief]:
    post = packet.records[0]
    item = ExtractItem(
        item_id="item-1", category="fact", text="仅供测试的陈述。",
        evidence=[TextReference(kind="body", record_id=post.record_id, excerpt=post.content)],
    )
    extraction = Extraction(
        input_sha256=fingerprint(packet),
        posts=[PostExtraction(
            record_id=post.record_id, items=[item],
            images=[ImageReading(media_id=i.media_id, status="not_read") for i in packet.images],
        )],
    )
    brief = DailyBrief(
        date=packet.date, input_sha256=extraction.input_sha256, extraction_sha256=fingerprint(extraction),
        summary=CitedPoint(text="测试摘要", item_ids=["item-1"]),
        events=[], themes=[], risks=[], questions=[],
        hypotheses=[Hypothesis(
            comparison_key="fixture-hypothesis", statement="测试假设", support_item_ids=["item-1"],
            counter_item_ids=[], questions=["有哪些反方材料？"],
        )],
    )
    return extraction, brief


class BriefValidationTests(unittest.TestCase):
    def setUp(self):
        self.packet = sample(date(2026, 11, 19), "1000", with_image=True)
        self.extraction, self.brief = replies(self.packet)

    def test_preserves_unverified_source_and_accepts_valid_citations(self):
        validate_extraction(self.packet, self.extraction)
        validate_brief(self.packet, self.extraction, self.brief)
        cite = evidence_index(self.packet, self.extraction)["item-1"]["citations"][0]
        self.assertEqual(cite["source_verification"], "pending")
        self.assertEqual(cite["excel_row"], 2)

    def test_rejects_missing_records_wrong_quote_and_other_post(self):
        incomplete = self.extraction.model_copy(update={"posts": []})
        with self.assertRaisesRegex(ValueError, "每条记录"):
            validate_extraction(self.packet, incomplete)
        self.extraction.posts[0].items[0].evidence[0].excerpt = "文中不存在的内容"
        with self.assertRaisesRegex(ValueError, "无法在存档中定位"):
            validate_extraction(self.packet, self.extraction)
        self.extraction.posts[0].items[0].evidence[0].record_id = "unrelated"
        with self.assertRaisesRegex(ValueError, "其他记录"):
            validate_extraction(self.packet, self.extraction)

    def test_requires_image_to_be_readable_and_associated(self):
        img = ImageReference(
            kind="image", record_id=self.packet.records[0].record_id, media_id="image-fixture",
            region=(0.0, 0.0, 0.5, 1.0),
        )
        self.extraction.posts[0].items[0].evidence = [img]
        with self.assertRaisesRegex(ValueError, "不可读"):
            validate_extraction(self.packet, self.extraction)
        self.extraction.posts[0].images[0] = ImageReading(
            media_id="image-fixture", status="readable", observation="图片测试区域。",
        )
        validate_extraction(self.packet, self.extraction)
        with self.assertRaises(ValidationError):
            ImageReading(media_id="image-fixture", status="unreadable", observation="臆测内容")
        with self.assertRaises(ValidationError):
            ImageReference(kind="image", record_id="id", media_id="id", region=(0.6, 0.0, 0.5, 1.0))

    def test_rejects_cross_day_or_unknown_report_evidence(self):
        self.brief.date = date(2026, 11, 20)
        with self.assertRaisesRegex(ValueError, "日期或输入快照"):
            validate_brief(self.packet, self.extraction, self.brief)
        self.brief.date = self.packet.date
        self.brief.summary.item_ids = ["unknown"]
        with self.assertRaisesRegex(ValueError, "不存在"):
            validate_brief(self.packet, self.extraction, self.brief)


class BriefArchiveTests(unittest.TestCase):
    def test_rehearsal_is_idempotent_and_does_not_add_claims(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            packet = sample(date(2026, 11, 19), "1000", with_image=True)
            path = archive_run(root, packet, RehearsalProvider(), "rehearsal")
            self.assertEqual(archive_run(root, packet, RehearsalProvider(), "rehearsal"), path)
            run, loaded, extraction, brief = load_run(path)
            self.assertEqual(run.mode, "rehearsal")
            self.assertEqual(coverage(loaded)["image_count"], 1)
            self.assertEqual(extraction.posts[0].items, [])
            self.assertIsNone(brief.summary)
            self.assertIn("离线流程演练", (path / "brief.md").read_text(encoding="utf-8"))
            added = sample(date(2026, 11, 21), "1001").records[0]
            current = ImportResult(
                source_file="fixture.xlsx", sheet="Sheet1", workbook_sha256="d" * 64, data_rows=2,
                embedded_media_files=0, posts=packet.records + [added], relations=[], issues=[],
            )
            self.assertEqual(preview_runs(root, current, {"image-fixture": "f" * 64}), [])
            shown = preview_runs(root, current, {"image-fixture": "b" * 64})
            self.assertEqual(shown[0]["image_states"]["not_read"], 1)
            self.assertEqual(shown[0]["date"], "2026-11-19")
            (path / run.extract_prompt.name).write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Prompt 或 Schema"):
                load_run(path)

    def test_replay_comparison_distinguishes_only_new_post_ids(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)

            def replay(packet: InputPacket, dir_name: str) -> Path:
                directory = root / dir_name
                directory.mkdir()
                extraction, brief = replies(packet)
                first, second = directory / "extract.json", directory / "daily.json"
                first.write_bytes(encode(extraction))
                second.write_bytes(encode(brief))
                return archive_run(root, packet, ReplyProvider(first, second, "synthetic-unit-test"), "replay")

            old = replay(sample(date(2026, 11, 19), "1000"), "older")
            same_id = replay(sample(date(2026, 11, 20), "1000"), "repeat")
            new_id = replay(sample(date(2026, 11, 20), "2000"), "new")
            self.assertEqual(compare(old, same_id)["status"], "暂无法判断变化")
            self.assertEqual(compare(old, new_id)["hypotheses"][0]["new_support_post_ids"], ["2000"])
            with self.assertRaisesRegex(ValueError, "较早、较晚"):
                compare(new_id, old)

    def test_real_workbook_scopes_dates_and_keeps_shared_link_rows(self):
        source = Path("data/processed/posts.json")
        if not source.is_file():
            self.skipTest("未配置本地 AlphaLens 存档")
        packet = prepare_input(source.read_bytes(), date(2026, 11, 20), Path("frontend/.local-archive"))
        self.assertTrue(all(record.posted_date == packet.date for record in packet.records))
        known = [record for record in packet.records if record.excel_row in (14, 15)]
        if len(known) == 2 and known[0].post_id == known[1].post_id:
            self.assertNotEqual(known[0].record_id, known[1].record_id)
        snapshot = json.loads(source.read_bytes())
        self.assertEqual(len(packet.records), sum(p["posted_date"] == str(packet.date) for p in snapshot["posts"]))


class OpenAIGenerationTests(unittest.TestCase):
    def test_responses_payload_archives_both_steps_and_image(self):
        import os
        from hashlib import sha256
        from unittest.mock import patch

        import httpx
        from openai import OpenAI
        from PIL import Image

        from scripts.openai_brief import DEFAULT_MODEL, OpenAIBriefProvider

        with TemporaryDirectory() as folder:
            root = Path(folder)
            media_dir = root / "preview/media"
            media_dir.mkdir(parents=True)
            sample_image = media_dir / "test.png"
            Image.new("RGB", (4, 4), "green").save(sample_image)
            digest = sha256(sample_image.read_bytes()).hexdigest()
            sample_image.rename(media_dir / (digest + ".png"))
            packet = sample(date(2026, 11, 19), "1000", with_image=True)
            packet.images = [InputImage(media_id="image-fixture", local_path=f"media/{digest}.png", sha256=digest)]
            extraction, brief = replies(packet)
            responses = [extraction, brief]
            requests = []

            def handle(request):
                payload = json.loads(request.content)
                self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
                self.assertEqual(payload["store"], False)
                self.assertEqual(payload["model"], DEFAULT_MODEL)
                bodies = payload["input"][0]["content"]
                schema = payload["text"]["format"]
                self.assertEqual(schema["strict"], True)
                for obj in [schema["schema"], *schema["schema"]["$defs"].values()]:
                    self.assertEqual(set(obj.get("required", [])), set(obj.get("properties", {})))
                    self.assertFalse(obj.get("additionalProperties", False))

                if not requests:
                    self.assertEqual([part["type"] for part in bodies], ["input_text", "input_text", "input_image"])
                    self.assertTrue(bodies[-1]["image_url"].startswith("data:image/png;base64,"))
                    self.assertNotIn("local_path", bodies[0]["text"])
                    self.assertEqual(json.loads(bodies[0]["text"])["input_sha256"], fingerprint(packet))
                    region = schema["schema"]["$defs"]["ImageReference"]["properties"]["region"]
                    self.assertEqual(region["maxItems"], 4)
                    self.assertEqual(region["items"]["type"], "number")
                    self.assertNotIn("prefixItems", region)
                else:
                    self.assertEqual([part["type"] for part in bodies], ["input_text"])
                    self.assertEqual(json.loads(bodies[0]["text"])["extraction_sha256"], fingerprint(extraction))
                output = responses[len(requests)]
                requests.append(payload)
                return httpx.Response(200, json={
                    "id": "resp_test", "object": "response", "created_at": 0, "model": DEFAULT_MODEL,
                    "status": "completed", "output": [{
                        "id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": output.model_dump_json(), "annotations": []}],
                    }],
                })

            local_client = OpenAI(
                api_key="sk-unit-test-only", base_url="https://api.openai.com/v1",
                http_client=httpx.Client(transport=httpx.MockTransport(handle)),
            )
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-unit-test-only"}), patch(
                "scripts.openai_brief.openai.OpenAI", return_value=local_client,
            ):
                with OpenAIBriefProvider(DEFAULT_MODEL, root / "preview") as provider:
                    destination = archive_run(root, packet, provider, "api")

            self.assertEqual(len(requests), 2)
            self.assertEqual(destination.parent.parent.name, "generated")
            self.assertEqual(load_run(destination)[0].mode, "api")
            self.assertIn("OpenAI 生成", (destination / "brief.md").read_text(encoding="utf-8"))
            self.assertNotIn("sk-unit-test-only", (destination / "run.json").read_text(encoding="utf-8"))

    def test_tracking_id_is_rejected_without_echoing_value(self):
        import os
        from unittest.mock import patch

        from scripts.openai_brief import DEFAULT_MODEL, OpenAIBriefProvider

        with patch.dict(os.environ, {"OPENAI_API_KEY": "key_test_only"}), patch(
            "scripts.openai_brief.openai.OpenAI",
        ) as client:
            with self.assertRaisesRegex(ValueError, "完整的 OpenAI Secret Key") as context:
                OpenAIBriefProvider(DEFAULT_MODEL, Path("."))
            client.assert_not_called()
            self.assertNotIn("key_test_only", str(context.exception))

    def test_prompt_rejects_terminal_without_hidden_input(self):
        import warnings
        from getpass import GetPassWarning
        from unittest.mock import patch

        from scripts.run_brief import prompt_for_api_key

        def prompt(_message):
            warnings.warn("Terminal does not support masked input", GetPassWarning, stacklevel=2)
            self.fail("Must stop before allowing input to echo")

        with patch("scripts.run_brief.getpass", side_effect=prompt):
            with self.assertRaisesRegex(ValueError, "当前终端无法隐藏输入"):
                prompt_for_api_key()

    def test_rate_limit_explains_returned_reason(self):
        from unittest.mock import patch

        import httpx
        from openai import OpenAI

        from scripts.brief_pipeline import read_prompts
        from scripts.openai_brief import DEFAULT_MODEL, OpenAIBriefProvider

        packet = sample(date(2026, 11, 19), "1000")
        prompt, _ = read_prompts()
        for error_code, error_type, expected in (
            ("credit_balance_exhausted", "insufficient_quota", "API 余额已用完"),
            ("project_spend_limit_exceeded", "insufficient_quota", "项目已达到 API 支出上限"),
            ("rate_limit_exceeded", "tokens", "Token 速率限制"),
            (None, "insufficient_quota", "当前 API 额度不足"),
            ("unknown_fixture", "unknown_fixture", "请检查 API 余额、项目限额和请求频率"),
        ):
            with self.subTest(code=error_code, type=error_type):
                def handle(_request):
                    return httpx.Response(429, headers={"x-request-id": "req_fixture"}, json={
                        "error": {"code": error_code, "type": error_type, "message": "raw-error-fixture"},
                    })

                client = OpenAI(
                    api_key="sk-unit-test-only", max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(handle)),
                )
                with patch("scripts.openai_brief.openai.OpenAI", return_value=client):
                    with OpenAIBriefProvider(DEFAULT_MODEL, Path("."), api_key="sk-unit-test-only") as provider:
                        with self.assertRaisesRegex(ValueError, expected) as caught:
                            provider.extract(packet, prompt)
                diagnostic = str(caught.exception)
                self.assertIn("req_fixture", diagnostic)
                self.assertNotIn("raw-error-fixture", diagnostic)
                if error_code is not None and error_code != "unknown_fixture":
                    self.assertIn(error_code, diagnostic)

    def test_connection_check_uses_no_authorization(self):
        from unittest.mock import patch

        import httpx

        from scripts.openai_brief import check_connection

        def handle(request):
            self.assertEqual(str(request.url), "https://api.openai.com/v1/models")
            self.assertEqual(request.method, "GET")
            self.assertNotIn("authorization", request.headers)
            self.assertEqual(request.content, b"")
            return httpx.Response(401)

        client = httpx.Client(transport=httpx.MockTransport(handle))
        with patch("scripts.openai_brief.httpx.Client", return_value=client):
            self.assertIn("连接可达", check_connection())

    def test_connection_check_explains_nested_transport_errors(self):
        import socket
        import ssl
        from unittest.mock import patch

        import httpx

        from scripts.openai_brief import check_connection

        for cause, expected in (
            (socket.gaierror("raw DNS failure"), "DNS 解析失败"),
            (ssl.SSLCertVerificationError("raw certificate failure"), "证书校验失败"),
            (httpx.ProxyError("raw proxy details"), "代理连接失败"),
        ):
            with self.subTest(expected=expected):
                def handle(_request):
                    raise httpx.ConnectError("raw connection error") from cause

                client = httpx.Client(transport=httpx.MockTransport(handle))
                with patch("scripts.openai_brief.httpx.Client", return_value=client):
                    with self.assertRaisesRegex(ValueError, expected) as caught:
                        check_connection()
                self.assertNotIn("raw", str(caught.exception))

    def test_openrouter_text_only_archives_results_and_marks_images_not_read(self):
        from unittest.mock import patch

        import httpx
        from openai import OpenAI

        from scripts.openrouter_brief import API_BASE_URL, DEFAULT_MODEL, OpenRouterBriefProvider, read_openrouter_prompts
        from scripts.openrouter_evidence import AnchoredExtraction, AnchoredItem

        with TemporaryDirectory() as folder:
            root = Path(folder)
            packet = sample(date(2026, 11, 19), "1000", with_image=True)
            extraction, brief = replies(packet)
            item_id = packet.records[0].record_id + "-1"
            extraction.posts[0].items[0].item_id = item_id
            brief.extraction_sha256 = fingerprint(extraction)
            brief.summary.item_ids = [item_id]
            brief.hypotheses[0].support_item_ids = [item_id]
            model_extraction = AnchoredExtraction(items=[
                AnchoredItem(category="fact", text=extraction.posts[0].items[0].text, segment_ids=["s-1"]),
            ])
            invalid = brief.model_copy(deep=True)
            invalid.summary.item_ids = ["invented-evidence-id"]
            repaired = brief.model_copy(deep=True)
            repaired.summary.item_ids += repaired.summary.item_ids
            outputs = iter([model_extraction, invalid, repaired])
            schema_names = []

            def handle(request):
                self.assertEqual(str(request.url), f"{API_BASE_URL}/chat/completions")
                self.assertEqual(request.headers["Authorization"], "Bearer sk-or-test-only")
                payload = json.loads(request.content)
                self.assertEqual(payload["model"], DEFAULT_MODEL)
                self.assertEqual(payload["provider"], {"require_parameters": True})
                self.assertTrue(payload["response_format"]["json_schema"]["strict"])
                schema_names.append(payload["response_format"]["json_schema"]["name"])
                received = json.loads(payload["messages"][1]["content"])
                if len(schema_names) == 1:
                    self.assertNotIn("images", received)
                    self.assertNotIn("media", received["records"][0])
                    self.assertNotIn("local_path", payload["messages"][1]["content"])
                    self.assertEqual(received["segments"][0]["excerpt"], packet.records[0].content)
                    defs = payload["response_format"]["json_schema"]["schema"]["$defs"]
                    self.assertEqual(defs["AnchoredItem"]["properties"]["segment_ids"]["items"]["enum"], ["s-1"])
                else:
                    self.assertEqual(received["extraction_sha256"], fingerprint(extraction))
                    self.assertEqual(received["extraction"]["posts"][0]["images"][0]["status"], "not_read")
                    self.assertEqual(received["allowed_item_ids"], [item_id])
                    defs = payload["response_format"]["json_schema"]["schema"]["$defs"]
                    self.assertEqual(defs["CitedPoint"]["properties"]["item_ids"]["items"]["enum"], [item_id])
                    for field in ("support_item_ids", "counter_item_ids"):
                        self.assertEqual(defs["Hypothesis"]["properties"][field]["items"]["enum"], [item_id])
                    if len(schema_names) == 3:
                        self.assertIn("summary.item_ids", received["validation_error"])
                    else:
                        self.assertNotIn("validation_error", received)
                return httpx.Response(200, json={
                    "id": "chat-test", "object": "chat.completion", "created": 0, "model": DEFAULT_MODEL,
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {
                        "role": "assistant", "content": next(outputs).model_dump_json(),
                    }}],
                })

            client = OpenAI(
                api_key="sk-or-test-only", base_url=API_BASE_URL,
                http_client=httpx.Client(transport=httpx.MockTransport(handle)),
            )
            with patch("scripts.openrouter_brief.openai.OpenAI", return_value=client):
                with OpenRouterBriefProvider(DEFAULT_MODEL, root, api_key="sk-or-test-only") as provider:
                    destination = archive_run(root, packet, provider, "api", prompts=read_openrouter_prompts())

            run, _, stored_extraction, stored_brief = load_run(destination)
            self.assertEqual(run.provider, "openrouter-chat-completions")
            self.assertEqual(schema_names, ["alphalens_anchored_extraction", "alphalens_brief", "alphalens_brief"])
            self.assertEqual(stored_extraction, extraction)
            self.assertEqual(stored_brief, brief)
            self.assertIn("OpenRouter 文字分析", (destination / "brief.md").read_text(encoding="utf-8"))

    def test_openrouter_empty_extraction_does_not_generate_unreferenced_claims(self):
        from unittest.mock import patch

        from scripts.brief_pipeline import read_prompts, report_input
        from scripts.openrouter_brief import DEFAULT_MODEL, OpenRouterBriefProvider

        packet = sample(date(2026, 11, 19), "1000")
        extraction = RehearsalProvider().extract(packet, read_prompts()[0])
        prepared = report_input(packet, extraction)
        with patch("scripts.openrouter_brief.openai.OpenAI"):
            with OpenRouterBriefProvider(DEFAULT_MODEL, Path("."), api_key="sk-or-test-only") as provider:
                with patch.object(provider, "_request") as request:
                    brief = provider.summarize(prepared, read_prompts()[1])
                    request.assert_not_called()
        validate_brief(packet, extraction, brief)
        self.assertIsNone(brief.summary)
        self.assertEqual(brief.hypotheses, [])

    def test_openrouter_uses_exact_passages_and_rejects_cross_post_references(self):
        from scripts.openrouter_evidence import AnchoredExtraction, AnchoredItem, attach_evidence, select_passages

        packet = sample(date(2026, 11, 19), "1000")
        packet.records[0].content = "消息称 20 亿美元。 这是作者观点。"
        packet.records[0].quoted_content = "引用的原句。"
        packet.records.append(sample(packet.date, "1001").records[0])
        passages = select_passages(packet)
        digest = fingerprint(packet)
        output = AnchoredExtraction(items=[
            AnchoredItem(category="fact", text="转述文字可以改写。", segment_ids=["s-1", "s-3", "s-3"]),
        ])
        extraction = attach_evidence(packet, output, passages, digest)
        validate_extraction(packet, extraction)
        refs = extraction.posts[0].items[0].evidence
        self.assertEqual([(ref.kind, ref.excerpt) for ref in refs],
                         [("body", "消息称 20 亿美元。"), ("quote", "引用的原句。")])
        self.assertEqual(extraction.posts[1].items, [])

        output.items[0].segment_ids = ["s-1", "s-4"]
        with self.assertRaisesRegex(ValueError, "不同帖子"):
            attach_evidence(packet, output, passages, digest)
        output.items[0].segment_ids = ["s-99"]
        with self.assertRaisesRegex(ValueError, "不存在"):
            attach_evidence(packet, output, passages, digest)
