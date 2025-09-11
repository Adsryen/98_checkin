from __future__ import annotations

from typing import Optional

from openai import OpenAI

from .config import OpenAIConfig


class AIResponder:
    def __init__(self, cfg: OpenAIConfig) -> None:
        self.cfg = cfg
        # OpenAI SDK 1.x 允许自定义 base_url 以兼容 OpenAI 协议网关
        self.client = OpenAI(
            api_key=cfg.api_key or "",
            base_url=cfg.base_url or None,
        )

    def generate_reply(self, context: str, signature: str = "") -> str:
        prompt = (
            "请根据下述帖子内容，以自然、友好的语气生成一条简短中文回复。"
            "避免违禁词、避免重复、避免灌水口水话，最多100字。\n\n"
            f"帖子内容：\n{context}\n\n"
            "回复："
        )
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[
                {"role": "system", "content": "你是一个乐于助人的中文论坛用户。"},
                {"role": "user", "content": prompt},
            ],
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        if signature:
            text = f"{text}\n\n{signature}"
        return text
