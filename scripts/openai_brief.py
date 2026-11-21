"""OpenAI Responses API provider for the local brief workflow."""

import os
import socket
import ssl
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlsplit

import httpx
import openai
from pydantic import BaseModel, ValidationError

from .brief_models import DailyBrief, Extraction, InputImage, InputPacket
from .brief_pipeline import Prompt, encode, fingerprint

API_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.4-mini-2026-03-17"
IMAGE_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
T = TypeVar("T", bound=BaseModel)

RATE_LIMIT_TIPS = {
    "credit_balance_exhausted": "API 余额已用完。请在密钥所属的组织查看 API 账单和可用余额。",
    "insufficient_quota": "当前 API 额度不足。请查看密钥所属组织的 API 余额、用量和支出上限。",
    "organization_usage_limit_exceeded": "当前组织已达到获批的 API 用量上限。请查看组织用量限制。",
    "organization_spend_limit_exceeded": "当前组织已达到 API 支出上限。请查看组织支出设置。",
    "project_spend_limit_exceeded": "当前项目已达到 API 支出上限。请查看项目支出设置。",
    "rate_limit_exceeded": "当前请求触发 API 请求或 Token 速率限制。请稍等后重试。",
    "rate_limit_error": "当前请求触发 API 速率限制。请稍等后重试。",
    "slow_down": "当前请求触发 API 速率限制。请稍等后重试。",
}


def connection_hint(error: BaseException, host: str = "api.openai.com") -> str:
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, ssl.SSLError):
            return "TLS 握手或证书校验失败。请检查系统时间以及当前网络或代理配置的可信证书。"
        if isinstance(cause, socket.gaierror):
            return "DNS 解析失败。请检查当前网络或代理是否能解析 API 地址。"
        if isinstance(cause, httpx.ProxyError):
            return "代理连接失败。请检查当前 PowerShell 使用的代理地址和端口。"
        if isinstance(cause, httpx.TimeoutException):
            return "连接或读取超时。请切换到能访问 API 的稳定网络后再试。"
        cause = cause.__cause__
    return f"未能收到 API 响应。请确认当前 PowerShell 能通过 HTTPS 访问 {host}。"


def check_connection(base_url: str = API_BASE_URL) -> str:
    host = urlsplit(base_url).hostname
    try:
        with httpx.Client(timeout=10.0, trust_env=True) as client:
            response = client.get(f"{base_url}/models")
    except (httpx.RequestError, OSError) as exc:
        raise ValueError(connection_hint(exc, host)) from exc

    if response.status_code == 401:
        return "已收到 API 的 HTTP 401 响应。连接可达，匿名请求返回 401 属于预期结果。"
    if response.status_code != 200:
        raise ValueError(
            f"收到 HTTP {response.status_code}。请检查当前网络或代理是否允许访问 {host}。"
        )
    return "API 的 HTTPS 连接可达（HTTP 200）。"


def responses_schema(schema: dict) -> dict:
    """Adapt the local Pydantic schema to the Responses strict-schema subset."""
    node = {name: value for name, value in schema.items() if name not in {"default", "discriminator", "title"}}
    for field in ("properties", "$defs"):
        if field in node:
            node[field] = {name: responses_schema(child) for name, child in node[field].items()}
    if node.get("type") == "object":
        node["required"] = list(node.get("properties", {}))
        node["additionalProperties"] = False
    if "oneOf" in node:
        node["anyOf"] = node.pop("oneOf")
    if "anyOf" in node:
        node["anyOf"] = [responses_schema(child) for child in node["anyOf"]]
    if "prefixItems" in node:
        prefix = node.pop("prefixItems")
        if not prefix or any(child != prefix[0] for child in prefix):
            raise ValueError("API 输出格式暂不支持异构元组。")
        node["items"] = prefix[0]
    if isinstance(node.get("items"), dict):
        node["items"] = responses_schema(node["items"])
    if "const" in node:
        node["enum"] = [node.pop("const")]
    return node


def parse_model_reply(reply: str, prompt: Prompt, model: type[T]) -> T:
    try:
        return model.model_validate_json(reply)
    except ValidationError as exc:
        first = exc.errors(include_input=False, include_context=False, include_url=False)[0]
        field = ".".join(map(str, first["loc"])) or "根对象"
        raise ValueError(f"{prompt.name} 的回复未通过校验（{field}，{first['type']}）。") from exc


class OpenAIBriefProvider:
    name = "openai-responses"

    def __init__(self, model: str, preview_dir: Path, *, api_key: str | None = None):
        key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            raise ValueError("请用 --prompt-key 隐藏输入密钥，或配置 OPENAI_API_KEY。")
        if not key.startswith("sk-") or key.startswith("sk-or-"):
            raise ValueError("OPENAI_API_KEY 需要填完整的 OpenAI Secret Key。")
        self.model = model
        self.preview_dir = preview_dir
        self.client = openai.OpenAI(
            api_key=key, base_url=API_BASE_URL, max_retries=0, timeout=240.0,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.client.close()

    def _image_part(self, image: InputImage) -> dict:
        root = (self.preview_dir.resolve() / "media").resolve()
        path = (self.preview_dir / image.local_path).resolve()
        mime = IMAGE_TYPES.get(path.suffix.lower())
        if not path.is_relative_to(root) or path.stem != image.sha256 or not mime:
            raise ValueError(f"图片 {image.media_id} 的预览路径无效。")
        blob = path.read_bytes()
        if sha256(blob).hexdigest() != image.sha256:
            raise ValueError(f"图片 {image.media_id} 的内容校验失败，请重新准备本机预览。")
        return {
            "type": "input_image", "image_url": f"data:{mime};base64,{b64encode(blob).decode('ascii')}",
            "detail": "high",
        }

    def _request(
        self, prompt: Prompt, schema_name: str, content: list[dict], model: type[T], token_limit: int,
    ) -> T:
        try:
            result = self.client.responses.create(
                model=self.model,
                instructions=prompt.text,
                input=[{"role": "user", "content": content}],
                text={"format": {
                    "type": "json_schema", "name": schema_name, "schema": responses_schema(prompt.schema), "strict": True,
                }},
                max_output_tokens=token_limit,
                store=False,
            )
        except openai.APITimeoutError as exc:
            raise ValueError(f"{prompt.name} 调用超时。") from exc
        except openai.APIConnectionError as exc:
            raise ValueError(f"{prompt.name} 连接 OpenAI 失败。{connection_hint(exc)}") from exc
        except openai.APIStatusError as exc:
            tips = {
                401: "请核对完整密钥是否有效。",
                403: "请确认 API 项目有模型调用权限。",
                404: "请检查该 API 项目可用的模型名称。",
                429: "请检查 API 余额、项目限额和请求频率。",
            }
            note = tips.get(exc.status_code, "请检查 API 项目设置或稍后重试。")
            reason = ""
            if exc.status_code == 429:
                for code in (exc.code, exc.type):
                    if isinstance(code, str) and code in RATE_LIMIT_TIPS:
                        note = RATE_LIMIT_TIPS[code]
                        reason = f"，{code}"
                        break
            request_id = f" 请求 ID {exc.request_id}。" if exc.request_id else ""
            raise ValueError(f"{prompt.name} 调用失败（HTTP {exc.status_code}{reason}）。{note}{request_id}") from exc

        if result.status != "completed" or not result.output_text:
            raise ValueError(f"{prompt.name} 未返回完整的结构化回复。")
        return parse_model_reply(result.output_text, prompt, model)

    def extract(self, packet: InputPacket, prompt: Prompt) -> Extraction:
        data = packet.model_dump(mode="json")
        data["input_sha256"] = fingerprint(packet)
        for entry in data["records"]:
            for asset in entry["media"]:
                asset.pop("local_path", None)
        for image in data["images"]:
            image.pop("local_path", None)

        content = [{"type": "input_text", "text": encode(data).decode("utf-8")}]
        for image in packet.images:
            content.append({"type": "input_text", "text": f"下一张图片的 media_id 是 {image.media_id}。"})
            content.append(self._image_part(image))
        return self._request(prompt, "alphalens_extraction", content, Extraction, 24000)

    def summarize(self, prepared: dict, prompt: Prompt) -> DailyBrief:
        content = [{"type": "input_text", "text": encode(prepared).decode("utf-8")}]
        return self._request(prompt, "alphalens_brief", content, DailyBrief, 12000)

