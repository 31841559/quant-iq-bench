"""OpenAI 兼容的推理客户端。

这个文件集中了踩过的四个坑，每个坑都对应一段代码：

1. 思考模式要显式开启。多数本地推理栈（mlx-serve / vLLM / llama.cpp 的
   chat template）默认关闭 thinking，模型会跳过推理直接猜答案，
   表现为「简单算术也算错」。开 `enable_thinking` 后思考进 reasoning_content，
   content 只剩干净答案。
2. `HTTP_PROXY` 会劫持内网请求。urllib 默认 trust_env=True，访问
   192.168.x.x 时被代理拦下返回 502，看起来像服务挂了。必须显式绕开。
3. 部分沙箱只放行特定进程的网络。Python socket 直连会被拦，
   而 curl 能通，所以保留 curl 子进程作为 fallback transport。
4. 长思考会被 max_tokens 砍断，content 返回空字符串。此时答案常常
   已经躺在 reasoning 里，需要兜底抽取，并且必须重试。

用法::

    from bench.client import Client
    c = Client()
    r = c.chat("只输出整数：13 的平方减 7 的立方加 100",
               thinking=True, max_tokens=8192)
    print(r.content, r.reasoning[:80], r.tokens, r.seconds)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_SYSTEM = "你是一个严谨的助手。先推理，最后一行严格输出：ANSWER: <你的最终答案>"

# 无代理 opener：避免 HTTP_PROXY 把内网请求劫持成 502
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass
class Reply:
    content: str = ""
    reasoning: str = ""
    tokens: int = 0
    seconds: float = 0.0
    finish_reason: str = ""
    flags: list[str] = field(default_factory=list)

    @property
    def answer(self) -> str:
        """取最终答案：优先 content，content 为空时回退 reasoning 末行。"""
        return extract_answer(self.content) or extract_answer(self.reasoning)


class TransientError(RuntimeError):
    """可重试的瞬时故障：连接重置、超时、空响应。"""


class Client:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: int = 900,
        transport: str = "auto",
        system: str | None = DEFAULT_SYSTEM,
    ) -> None:
        base = (base_url or os.environ.get("BENCH_BASE_URL") or "http://127.0.0.1:8080/v1").rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        self.url = base + "/chat/completions"
        self.model = model or os.environ.get("BENCH_MODEL") or ""
        if not self.model:
            raise SystemExit("缺少模型名：设置环境变量 BENCH_MODEL，或传 model=")
        self.api_key = api_key if api_key is not None else os.environ.get("BENCH_API_KEY", "")
        self.timeout = timeout
        self.transport = transport
        self.system = system

    # ---------------- 底层传输 ----------------

    def _http_post(self, payload: dict, use_curl: bool) -> str:
        body = json.dumps(payload, ensure_ascii=False)
        if use_curl:
            argv = ["curl", "-s", "-m", str(self.timeout), "--noproxy", "*",
                    "-X", "POST", self.url, "-H", "Content-Type: application/json"]
            if self.api_key:
                argv += ["-H", f"Authorization: Bearer {self.api_key}"]
            p = subprocess.run(argv + ["--data-binary", "@-"], input=body,
                               capture_output=True, text=True)
            if p.returncode != 0:
                raise TransientError(f"curl rc={p.returncode} {p.stderr[:120]}")
            return p.stdout

        data = body.encode("utf-8")
        req = urllib.request.Request(self.url, data=data,
                                     headers={"Content-Type": "application/json"})
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with _NO_PROXY_OPENER.open(req, timeout=self.timeout) as r:
                return r.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as e:
            raise TransientError(f"urllib: {e}") from e

    def _post(self, payload: dict) -> dict:
        attempts = 4
        last = ""
        use_curl = self.transport == "curl"
        for i in range(attempts):
            try:
                raw = self._http_post(payload, use_curl)
                if not raw.strip().startswith("{"):
                    raise TransientError(f"非 JSON 响应: {raw[:120]!r}")
                return json.loads(raw)
            except TransientError as e:
                last = str(e)
                # urllib 被沙箱拦时切 curl 再试
                if self.transport == "auto" and not use_curl:
                    use_curl = True
                time.sleep(1.5 * (i + 1))
        raise RuntimeError(f"连续 {attempts} 次失败：{last}")

    # ---------------- 对外接口 ----------------

    def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        thinking: bool = True,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        schema: dict | None = None,
        retries: int = 2,
    ) -> Reply:
        """发一次请求。schema 非空时走约束解码（此时不混用思考模式）。"""
        sys_prompt = self.system if system is None else system
        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 1,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "out", "strict": True, "schema": schema},
            }
        elif thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": True}

        reply = Reply()
        for attempt in range(retries + 1):
            t0 = time.time()
            d = self._post(payload)
            choice = (d.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            reply = Reply(
                content=(msg.get("content") or "").strip(),
                reasoning=(msg.get("reasoning_content") or msg.get("reasoning") or ""),
                tokens=(d.get("usage") or {}).get("completion_tokens", 0),
                seconds=round(time.time() - t0, 2),
                finish_reason=choice.get("finish_reason") or "",
            )
            if reply.content:
                return reply
            # content 空：先看 reasoning 里有救没救，再决定是否重试
            reply.flags.append("empty_content")
            if reply.answer:
                return reply
            if attempt < retries:
                reply.flags.append("retry")
        return reply

    def ask_json(self, prompt: str, schema: dict, **kw) -> dict:
        r = self.chat(prompt, schema=schema, thinking=False, **kw)
        text = re.sub(r"^```(?:json)?|```$", "", r.content.strip(), flags=re.M).strip()
        return json.loads(text)

    def close(self) -> None:  # 与连接池实现保持同一接口
        pass


# ---------------- 答案抽取 ----------------

_ANSWER_RE = re.compile(r"ANSWER\s*[:：]\s*(.+)", re.I)
_WRAP = "\"'`“”‘’*。 ，,：:"


def extract_answer(text: str) -> str:
    """从一段输出里抠出最终答案。

    顺序：最后一个 ANSWER: 行 → 最后一个被引号/反引号包裹的短片段 → 最后一行。
    """
    text = str(text or "")
    hits = _ANSWER_RE.findall(text)
    if hits:
        return hits[-1].strip().strip(_WRAP)
    quoted = re.findall(r"[“\"`]([^”\"`\n]{1,80})[”\"`]", text)
    if quoted:
        return quoted[-1].strip().strip(_WRAP)
    lines = [x.strip() for x in text.strip().splitlines() if x.strip()]
    return lines[-1].strip(_WRAP) if lines else ""
