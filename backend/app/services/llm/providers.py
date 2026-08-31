from __future__ import annotations

import asyncio
import json
import re

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.llm.base import ChatMessage, ChatProvider

_http: httpx.AsyncClient | None = None


def http_client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=90)
    return _http


async def _post_with_retry(url: str, **kwargs) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = await http_client().post(url, **kwargs)
            if resp.status_code in {429, 500, 502, 503, 504}:
                await asyncio.sleep(0.4 * (attempt + 1))
                last_exc = httpx.HTTPStatusError(
                    f"retryable {resp.status_code}", request=resp.request, response=resp
                )
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            await asyncio.sleep(0.4 * (attempt + 1))
    assert last_exc is not None
    raise AppError("模型服务暂不可用，请稍后重试", code=503, status_code=503) from last_exc


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        name: str,
        temperature_delta: float = 0.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = name
        self.temperature_delta = temperature_delta

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.6,
        json_mode: bool = True,
        max_tokens: int = 2048,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            # DeepSeek rejects json_object unless the prompt contains the word "json"
            blob = "\n".join(m["content"] for m in payload["messages"])
            if "json" not in blob.lower():
                if payload["messages"] and payload["messages"][0]["role"] == "system":
                    payload["messages"][0]["content"] += "\n只输出合法 JSON。"
                else:
                    payload["messages"].insert(0, {"role": "system", "content": "只输出合法 JSON。"})
            # deepseek-v4 thinking can exhaust max_tokens and leave content empty
            if self.name == "deepseek":
                payload["thinking"] = {"type": "disabled"}

        async def _request(body: dict) -> str:
            resp = await _post_with_retry(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
            )
            data = resp.json()
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            return str(msg.get("content") or "")

        content = await _request(payload)
        if json_mode and not content.strip() and self.name == "deepseek":
            retry = dict(payload)
            retry["thinking"] = {"type": "disabled"}
            retry["max_tokens"] = max(max_tokens, 8192)
            content = await _request(retry)
        return content


class AnthropicProvider:
    name = "claude"

    def __init__(self, model: str | None = None, temperature_delta: float = 0.0):
        self.api_key = settings.anthropic_api_key
        self.model = model or settings.anthropic_model
        self.temperature_delta = temperature_delta

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.6,
        json_mode: bool = True,
        max_tokens: int = 2048,
    ) -> str:
        system = ""
        body_msgs = []
        for m in messages:
            if m.role == "system":
                system += m.content + "\n"
            else:
                body_msgs.append({"role": m.role, "content": m.content})
        if json_mode:
            system += "\n只输出合法 JSON。"
        resp = await _post_with_retry(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system.strip(),
                "messages": body_msgs,
            },
        )
        data = resp.json()
        return "".join(part.get("text", "") for part in data.get("content", []))


class MockProvider:
    name = "mock"
    model = "mock-local"
    temperature_delta = 0.0

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.6,
        json_mode: bool = True,
        max_tokens: int = 2048,
    ) -> str:
        blob = "\n".join(m.content for m in messages)
        return json.dumps(_mock_json(blob), ensure_ascii=False)


def _first_sentences(text: str, n: int = 6) -> list[str]:
    parts = re.split(r"[。！？\n]", text)
    out = [p.strip() for p in parts if 8 <= len(p.strip()) <= 80]
    return out[:n] or [text[:40] or "示例知识点"]


def _exam_text(blob: str) -> str:
    match = re.search(r"【待考查文本开始】\n(.*)\n【待考查文本结束】", blob, re.S)
    return match.group(1) if match else blob


def _mock_json(blob: str) -> dict:
    low = blob.lower()
    source = _exam_text(blob)
    sentences = _first_sentences(source)
    quote = sentences[0]
    answer = quote[-12:] if len(quote) > 12 else quote
    if "suggested_points" in low or ("unsuitable" in low and "suggested_types" in low):
        return {
            "unsuitable": len(quote) < 10,
            "reason": "" if len(quote) >= 10 else "信息过少",
            "suitable_skills": ["理解", "识记"],
            "suggested_types": ["single_choice", "true_false"],
            "suggested_points": sentences[:3],
            "summary": quote[:60],
        }
    if "判断科目" in blob or ("confidence" in low and "civics" in low):
        if any(k in source for k in ["Python", "代码", "算法", "函数", "API", "HTTP"]):
            sub = "it"
            tags = ["engineering", "it"]
        elif any(k in source for k in ["历史", "朝代", "革命"]):
            sub = "history"
            tags = ["humanities"]
        else:
            sub = "general"
            tags = []
        return {"subject": sub, "subject_tags": tags, "confidence": 0.7, "reason": "关键词匹配"}
    if "answer_type" in low or "预置答案锚点" in blob and "不要输出完整选择题" in blob:
        items = []
        for s in sentences[:3]:
            items.append(
                {
                    "quote": s,
                    "answer": s[-10:] if len(s) > 10 else s,
                    "answer_type": "claim",
                    "knowledge_tags": [s[:16]],
                    "suggested_micro_skill": "detail",
                }
            )
        return {"items": items or [{"quote": quote, "answer": answer, "answer_type": "claim", "knowledge_tags": [quote[:16]], "suggested_micro_skill": "gist"}]}
    if "学习者作答" in blob and "overall_feedback" in low:
        match = re.search(r"小问与量规：(\[.*?\])\n正解：", blob, re.S)
        try:
            subparts = json.loads(match.group(1)) if match else []
        except json.JSONDecodeError:
            subparts = []
        return {
            "status": "graded",
            "subparts": [
                {
                    "id": str(part.get("id") or "p1"),
                    "score": (part.get("rubric") or {}).get("max_score", 1),
                    "evidence": "作答满足量规要求。",
                    "feedback": "答案要点完整。",
                }
                for part in subparts
                if isinstance(part, dict)
            ],
            "overall_feedback": "已按量规完成辅助批改。",
        }
    if "量规可供人工审校" in blob and "rubrics" in low:
        match = re.search(r"小问：(\[.*?\])\n正解：", blob, re.S)
        try:
            subparts = json.loads(match.group(1)) if match else []
        except json.JSONDecodeError:
            subparts = []
        return {
            "valid": True,
            "rubrics": [
                {
                    "id": str(part.get("id") or "p1"),
                    "max_score": 5,
                    "criteria": [{"description": "回答正确要点", "points": 5}],
                }
                for part in subparts
                if isinstance(part, dict)
            ],
            "comment": "量规可供人工审校",
        }
    if "不要输出干扰项" in blob or "correct_text" in low:
        type_match = re.search(
            r"题型：(single_choice|true_false|fill_blank|application|proof|short_answer)",
            blob,
        )
        qtype = type_match.group(1) if type_match else "single_choice"
        payload = {
            "stem": f"根据材料，下列关于「{answer}」的说法正确的是？",
            "type": qtype,
            "answer": {"keys": ["A"], "texts": [answer]},
            "correct_text": answer,
            "explanation": f"原文指出：{quote}",
            "knowledge_tags": ["材料要点"],
            "micro_skill": "gist",
            "cognitive_level": "understand",
            "source_quote": quote,
        }
        if qtype == "true_false":
            payload["stem"] = f"材料表明：{quote}。"
            payload["answer"] = {"keys": ["对"], "texts": ["对"]}
            payload["correct_text"] = "对"
        if qtype == "fill_blank":
            payload["stem"] = quote.replace(answer, "______") if answer in quote else "材料中的关键结论是______。"
        if qtype in {"fill_blank", "application", "proof", "short_answer"}:
            prompt = "填写空缺内容" if qtype == "fill_blank" else "说明你的推导或结论"
            expected = {"id": "p1", "texts": [answer]}
            if qtype != "fill_blank":
                expected = {"id": "p1", "expected_points": [answer]}
            payload["stem"] = payload["stem"] if qtype == "fill_blank" else f"根据材料：{quote}"
            payload["subparts"] = [{"id": "p1", "prompt": prompt}]
            payload["answer"] = {"subparts": [expected]}
        if "【外部参考资料开始】" in blob:
            src_match = re.search(
                r"【外部参考资料开始】\n(.*)\n【外部参考资料结束】",
                blob,
                re.S,
            )
            if src_match:
                try:
                    sources = json.loads(src_match.group(1))
                except json.JSONDecodeError:
                    sources = []
                if isinstance(sources, list):
                    payload["external_source_ids"] = [
                        str(source.get("id"))
                        for source in sources
                        if isinstance(source, dict) and source.get("id")
                    ][:3]
        return payload
    if "equivalent_to_answer" in low and "verdict" in low:
        match = re.search(r"候选：(\[.*?\])\n【待考查文本开始】", blob, re.S)
        material = re.search(r"【待考查文本开始】\n(.*?)\n【待考查文本结束】", blob, re.S)
        try:
            candidates = json.loads(match.group(1)) if match else []
        except json.JSONDecodeError:
            candidates = []
        evidence = _first_sentences(material.group(1) if material else blob, 1)[0]
        return {
            "results": [
                {
                    "id": str(candidate.get("id")),
                    "verdict": "accepted",
                    "error_type": candidate.get("error_type") or "同维混淆",
                    "evidence_quote": evidence,
                    "reason": candidate.get("rationale") or "材料相关的错误选项",
                }
                for candidate in candidates
            ]
        }
    if "candidates" in low or "过生成" in blob or "干扰项候选" in blob:
        return {
            "candidates": [
                {"text": f"{answer}的前提条件", "error_type": "范围偏移", "rationale": "把必要条件说成充分条件"},
                {"text": f"与{answer}同类的其他概念", "error_type": "同维混淆", "rationale": "同一类别不同功能"},
                {"text": f"{quote[:8]}的次要结果", "error_type": "部分正确", "rationale": "前半正确后半偷换"},
                {"text": "材料中另一处真实概念但场景不同", "error_type": "张冠李戴", "rationale": "真实概念用错场景"},
                {"text": f"{answer}增加约25%", "error_type": "数值偏移", "rationale": "数值偏移约25%"},
                {"text": f"并非{answer}而是其对立面", "error_type": "同维混淆", "rationale": "对立概念"},
                {"text": f"{answer}仅在例外情况下成立", "error_type": "范围偏移", "rationale": "局部当全局"},
                {"text": sentences[1][-12:] if len(sentences) > 1 else "相关但错误的概括", "error_type": "张冠李戴", "rationale": "来自材料其他句"},
            ]
        }
    if "too_easy_keys" in low or "一眼就能排除" in blob:
        return {"too_easy_keys": [], "replacements": {}, "guessable": False, "notes": "选项均可保留"}
    if "usability" in low or "可用性检视" in blob:
        return {
            "fluency": 4,
            "accuracy": 4,
            "complexity": 3,
            "usability": 4,
            "answer_exists": True,
            "unique_correct": True,
            "leak": False,
            "controversial": False,
            "guessable": False,
            "all_distractors_valid": True,
            "invalid_distractor_keys": [],
            "review_reasons": [],
            "comment": "可用于练习",
        }
    return {"ok": True, "summary": quote}
