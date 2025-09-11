from __future__ import annotations

from typing import Optional

from .config import AppConfig
from .http_client import HttpClient
from .discuz_client import DiscuzClient
from .ai import AIResponder


class Runner:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.http = HttpClient(
            base_url=cfg.site.base_url,
            user_agent=cfg.site.user_agent,
        )
        self.discuz = DiscuzClient(self.http)
        self.ai = AIResponder(cfg.ai)

    def login(self) -> bool:
        return self.discuz.login(self.cfg.site.username, self.cfg.site.password)

    def daily_checkin(self) -> tuple[bool, str]:
        return self.discuz.try_checkin()

    def reply_topic(self, tid: int, context: str) -> tuple[bool, str]:
        # 生成回复
        message = self.ai.generate_reply(context=context, signature=self.cfg.bot.signature)
        if self.cfg.bot.dry_run:
            return True, f"[DRY-RUN] 将回复 tid={tid}: {message[:60]}..."
        return self.discuz.reply(tid=tid, message=message)

    def run_all(self) -> dict:
        result: dict = {"login": False, "checkin": (False, "未执行")}
        ok = self.login()
        result["login"] = ok
        if not ok:
            result["checkin"] = (False, "登录失败")
            return result
        if self.cfg.bot.daily_checkin_enabled:
            result["checkin"] = self.daily_checkin()
        return result
