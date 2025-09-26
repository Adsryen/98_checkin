from __future__ import annotations

from typing import Optional, Dict, Tuple, List

from .config import AppConfig
from .ai import AIResponder
from .storage import Storage
from .http_client import HttpClient
from .services.factory import create_discuz_service


class _UrlHelper:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"


class Runner:
    def __init__(self, cfg: AppConfig, account: Optional[dict] = None) -> None:
        self.cfg = cfg
        self.account: Dict = account or {}
        # 统一服务（requests / browser 由工厂决定）
        self.service = create_discuz_service(cfg, self.account)
        # 兼容 web.py 的 runner.http：在 requests 模式提供 HttpClient，在浏览器模式提供仅含 url() 的辅助
        base_url = (self.account.get("base_url") if self.account else None) or cfg.site.base_url
        user_agent = (self.account.get("user_agent") if self.account else None) or cfg.site.user_agent
        # 无论是否启用浏览器模式，都提供一个用于诊断与URL补全的 HttpClient
        self.http = HttpClient(base_url=base_url, user_agent=user_agent, proxy=cfg.site.proxy)
        self.ai = AIResponder(cfg.ai)
        self.storage = Storage(cfg.db_path)

    def login(self) -> bool:
        # 优先检测当前会话是否已登录（支持 Cookie-only 账号）
        try:
            if getattr(self.service, "check_logged_in", None) and self.service.check_logged_in():
                return True
        except Exception:
            pass
        username = self.account.get("username") or self.cfg.site.username
        password = self.account.get("password") or self.cfg.site.password
        if username and password:
            return self.service.login(username, password)
        return False

    def daily_checkin(self) -> tuple[bool, str]:
        return self.service.try_checkin()

    def reply_topic(self, tid: int, context: str) -> tuple[bool, str]:
        # 生成回复
        message = self.ai.generate_reply(context=context, signature=self.cfg.bot.signature)
        if self.cfg.bot.dry_run:
            return True, f"[DRY-RUN] 将回复 tid={tid}: {message[:60]}..."
        return self.service.reply(tid=tid, message=message)

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

    def fetch_profile(self) -> Tuple[bool, dict | str]:
        return self.service.fetch_profile()

    # ---- Random forum/thread selection with de-dup ----
    def pick_random_thread(self, fids: List[int], max_trials_per_forum: int = 10, max_pages_scan: int = 20) -> Optional[Tuple[int, int, str]]:
        import random
        if not fids:
            return None
        # 随机打散fid顺序
        candidates = fids[:]
        random.shuffle(candidates)
        for fid in candidates:
            max_page = self.service.forum_max_page(fid)
            # 限制页码范围，避免过深
            max_page_use = max(1, min(max_page, max_pages_scan))
            sample_pages = set()
            tries = 0
            while len(sample_pages) < min(max(1, max_trials_per_forum), max_page_use) and tries < max_trials_per_forum * 3:
                sample_pages.add(random.randint(1, max_page_use))
                tries += 1
            for page in sample_pages:
                items = self.service.threads_on_page(fid, page)
                random.shuffle(items)
                for tid, href in items:
                    if self.storage.has_used_thread(fid, tid):
                        continue
                    final_url = self.service.validate_thread(tid, href)
                    if final_url:
                        # 标记使用并返回（保存最终URL）
                        self.storage.mark_thread_used(fid, tid, final_url)
                        return fid, tid, final_url
            # 兜底顺序扫描（从第一页起），尽量找到一个
            for page in range(1, max_page_use + 1):
                items = self.service.threads_on_page(fid, page)
                for tid, href in items:
                    if self.storage.has_used_thread(fid, tid):
                        continue
                    final_url = self.service.validate_thread(tid, href)
                    if final_url:
                        self.storage.mark_thread_used(fid, tid, final_url)
                        return fid, tid, final_url
        return None


class AccountRunner(Runner):
    """兼容旧接口的多账号 Runner：行为与 Runner 相同，仅在构造时传入 account。"""
    def __init__(self, cfg: AppConfig, account: Optional[dict] = None) -> None:
        super().__init__(cfg, account=account)
