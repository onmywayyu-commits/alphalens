"""OpenRouter text analysis using strict Chat Completions outputs."""

import os
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import openai

from .brief_models import DailyBrief, Extraction, InputPacket
from .brief_pipeline import PROJECT, Prompt, encode, fingerprint, read_prompts, validate_brief_references
from .openai_brief import T, connection_hint, parse_model_reply, responses_schema
from .openrouter_evidence import AnchoredExtraction, attach_evidence, select_passages


API_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "z-ai/glm-5.2"


def read_openrouter_prompts() -> tuple[Prompt, Prompt]:
    name = "extract-anchored.v1.md"
    extraction = Prompt(name, (PROJECT / "prompts" / name).read_text(encoding="utf-8"),
                        AnchoredExtraction.model_json_schema())
    return extraction, read_prompts()[1]


class OpenRouterBriefProvider:
    name = "openrouter-chat-completions"

    def __init__(self, model: str, _preview_dir: Path, *, api_key: str | None = None):
        key = (api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")).strip()
        if not key.startswith("sk-or-"):
            raise ValueError("请用 --prompt-key 输入完整的 OpenRouter API Key，或配置 OPENROUTER_API_KEY。")
        self.model = model
        self.client = openai.OpenAI(
            api_key=key, base_url=API_BASE_URL, max_retries=0, timeout=240.0,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.client.close()

    def request_structured_with_metadata(
        self, prompt: Prompt, schema_name: str, data: dict, model: type[T], token_limit: int,
    ) -> tuple[T, str, str | None]:
        try:
            result = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt.text},
                    {"role": "user", "content": encode(data).decode("utf-8")},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name, "schema": responses_schema(prompt.schema), "strict": True,
                    },
                },
                max_completion_tokens=token_limit,
                extra_body={"provider": {"require_parameters": True}},
            )
        except openai.APITimeoutError as exc:
            raise ValueError(f"{prompt.name} 调用 OpenRouter 超时。") from exc
        except openai.APIConnectionError as exc:
            raise ValueError(f"{prompt.name} 连接 OpenRouter 失败。{connection_hint(exc, 'openrouter.ai')}") from exc
        except openai.APIStatusError as exc:
            tips = {
                400: "请检查模型是否支持所需的结构化输出。",
                401: "请检查 OpenRouter API Key 是否有效。",
                402: "请检查 OpenRouter 可用余额和这把密钥的额度。",
                403: "请确认账号允许调用所选模型。",
                404: "请确认所选模型有支持结构化输出的可用端点。",
                429: "请求触发 OpenRouter 或上游速率限制，请稍后重试。",
            }
            note = tips.get(exc.status_code, "请查看 OpenRouter 的可用状态。")
            raise ValueError(f"{prompt.name} 调用 OpenRouter 失败（HTTP {exc.status_code}）。{note}") from exc

        if not result.choices or result.choices[0].finish_reason != "stop":
            raise ValueError(f"{prompt.name} 未返回完整的结构化回复。")
        reply = result.choices[0].message.content
        if not reply:
            raise ValueError(f"{prompt.name} 未返回结构化正文。")
        return parse_model_reply(reply, prompt, model), result.model, result.id

    def _request(
        self, prompt: Prompt, schema_name: str, data: dict, model: type[T], token_limit: int,
    ) -> T:
        output, _, _ = self.request_structured_with_metadata(prompt, schema_name, data, model, token_limit)
        return output

    def request_structured(
        self, prompt: Prompt, schema_name: str, data: dict, model: type[T], token_limit: int,
    ) -> T:
        return self._request(prompt, schema_name, data, model, token_limit)

    def extract(self, packet: InputPacket, prompt: Prompt) -> Extraction:
        passages = select_passages(packet)
        digest = fingerprint(packet)
        if not passages:
            return attach_evidence(packet, AnchoredExtraction(items=[]), passages, digest)

        schema = deepcopy(prompt.schema)
        schema["$defs"]["AnchoredItem"]["properties"]["segment_ids"]["items"]["enum"] = list(passages)
        constrained = replace(prompt, schema=schema)
        data = {
            "records": [
                {"record_id": post.record_id, "author": post.author_display_name,
                 "quoted_author": post.quoted_author_handle}
                for post in packet.records
            ],
            "segments": [
                {"segment_id": segment_id, **passage.model_dump(mode="json")}
                for segment_id, passage in passages.items()
            ],
        }
        output = self._request(constrained, "alphalens_anchored_extraction", data, AnchoredExtraction, 24000)
        try:
            return attach_evidence(packet, output, passages, digest)
        except ValueError as exc:
            correction = {**data, "validation_error": str(exc)}
            retry = replace(
                constrained, text=constrained.text + "\n上次片段选择未通过校验，请按 validation_error 更正。",
            )
            output = self._request(retry, "alphalens_anchored_extraction", correction, AnchoredExtraction, 24000)
            return attach_evidence(packet, output, passages, digest)

    def summarize(self, prepared: dict, prompt: Prompt) -> DailyBrief:
        items = {item["item_id"] for row in prepared["extraction"]["posts"] for item in row["items"]}
        if not items:
            return DailyBrief(
                date=prepared["date"], input_sha256=prepared["input_sha256"],
                extraction_sha256=prepared["extraction_sha256"],
                summary=None, events=[], themes=[], hypotheses=[], questions=[], risks=[],
            )

        schema = deepcopy(prompt.schema)
        allowed = sorted(items)
        definitions = schema["$defs"]
        definitions["CitedPoint"]["properties"]["item_ids"]["items"]["enum"] = allowed
        for field in ("support_item_ids", "counter_item_ids"):
            definitions["Hypothesis"]["properties"][field]["items"]["enum"] = allowed

        constrained = replace(
            prompt, schema=schema,
            text=prompt.text + "\n证据数组只选择 allowed_item_ids 里的逐帖条目标识。"
            "不要使用帖子 ID 或 record_id 充当条目标识。每个数组中同一个标识只出现一次。"
            "证据不足时留空相应栏目。摘要可填 null。",
        )
        data = {**prepared, "allowed_item_ids": allowed}
        brief = self._request(constrained, "alphalens_brief", data, DailyBrief, 12000)
        try:
            return self._validate_summary(brief, items)
        except ValueError as exc:
            correction = {**data, "validation_error": str(exc)}
            retry = replace(
                constrained, text=constrained.text + "\n上一次日报未通过核验。按 validation_error 重新生成整份日报。",
            )
            brief = self._request(retry, "alphalens_brief", correction, DailyBrief, 12000)
            return self._validate_summary(brief, items)

    @staticmethod
    def _validate_summary(brief: DailyBrief, items: set[str]) -> DailyBrief:
        # Identical duplicates do not add evidence. Keep the first occurrence.
        points = brief.events + brief.themes + brief.questions + brief.risks
        if brief.summary:
            points = [brief.summary, *points]
        for point in points:
            point.item_ids = list(dict.fromkeys(point.item_ids))
        for hypothesis in brief.hypotheses:
            hypothesis.support_item_ids = list(dict.fromkeys(hypothesis.support_item_ids))
            hypothesis.counter_item_ids = list(dict.fromkeys(hypothesis.counter_item_ids))
        validate_brief_references(brief, items)
        return brief
