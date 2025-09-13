from __future__ import annotations

from typing import Optional, Dict, Tuple

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
            proxy=cfg.site.proxy,
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


class AccountRunner:
    """围绕账号（或Cookie）执行任务的Runner。"""

    def __init__(self, cfg: AppConfig, account: Optional[dict] = None) -> None:
        # account: dict from AccountConfig.model_dump()
        base_url = (account.get("base_url") if account else None) or cfg.site.base_url
        user_agent = (account.get("user_agent") if account else None) or cfg.site.user_agent
        proxy = cfg.site.proxy  # 允许全局代理
        self.http = HttpClient(base_url=base_url, user_agent=user_agent, proxy=proxy)
        # cookie 支持
        cookies: Dict[str, str] = {}
        if account:
            if account.get("cookie_string"):
                # 将 'k=v; a=b' 解析
                parts = [p.strip() for p in account["cookie_string"].split(";") if p.strip()]
                for p in parts:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        cookies[k.strip()] = v.strip()
            if account.get("cookies"):
                for item in account["cookies"]:
                    if "=" in item:
                        k, v = item.split("=", 1)
                        cookies[k.strip()] = v.strip()
        if cookies:
            self.http.set_cookies(cookies)

        self.discuz = DiscuzClient(self.http)
        self.cfg = cfg
        self.account = account or {}
        self.ai = AIResponder(cfg.ai)

    def login(self) -> bool:
        # 优先cookie；若cookie已登录则True，否则尝试用户名密码
        username = self.account.get("username") or self.cfg.site.username
        password = self.account.get("password") or self.cfg.site.password
        # 通过访问首页判断是否已登录
        home = self.http.get("/")
        if home.status_code == 200 and self.discuz.is_logged_in(home.text):
            return True
        if username and password:
            return self.discuz.login(username, password)
        return False

    def daily_checkin(self) -> Tuple[bool, str]:
        return self.discuz.try_checkin()

    def run_all(self) -> Dict[str, Tuple[bool, str]]:
        ok = self.login()
        res: Dict[str, Tuple[bool, str]] = {"login": (ok, "")}
        if not ok:
            res["checkin"] = (False, "登录失败")
            return res
        if self.cfg.bot.daily_checkin_enabled:
            res["checkin"] = self.daily_checkin()
        return res

    def fetch_profile(self) -> Tuple[bool, dict | str]:
        return self.discuz.fetch_profile()
