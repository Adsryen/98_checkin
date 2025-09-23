from __future__ import annotations

from typing import Optional, Dict, Tuple, List

from .config import AppConfig
from .http_client import HttpClient
from .discuz_client import DiscuzClient
from .browser_client import BrowserSession, DiscuzBrowserClient
from .ai import AIResponder
from .storage import Storage


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
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        # 根据配置选择浏览器模式或请求模式
        self.browser_session: Optional[BrowserSession] = None
        self.discuz_browser: Optional[DiscuzBrowserClient] = None
        if getattr(cfg, "browser", None) and cfg.browser.enabled:
            self.browser_session = BrowserSession(
                base_url=cfg.site.base_url,
                user_agent=cfg.site.user_agent,
                proxy=cfg.site.proxy,
                headless=cfg.browser.headless,
                slow_mo=cfg.browser.slow_mo_ms,
                timeout_ms=cfg.browser.timeout_ms,
                engine=cfg.browser.engine,
            )
            self.discuz_browser = DiscuzBrowserClient(self.browser_session)
            # 为与 web.py 的 runner.http.url(...) 兼容，提供一个仅含 url() 的辅助
            self.http = _UrlHelper(cfg.site.base_url)  # type: ignore
            self.discuz = None  # type: ignore
        else:
            self.http = HttpClient(
                base_url=cfg.site.base_url,
                user_agent=cfg.site.user_agent,
                proxy=cfg.site.proxy,
            )
            self.discuz = DiscuzClient(self.http)
        self.ai = AIResponder(cfg.ai)
        self.storage = Storage(cfg.db_path)

    def login(self) -> bool:
        if self.discuz_browser:
            return self.discuz_browser.login(self.cfg.site.username, self.cfg.site.password)
        return self.discuz.login(self.cfg.site.username, self.cfg.site.password)

    def daily_checkin(self) -> tuple[bool, str]:
        if self.discuz_browser:
            return self.discuz_browser.try_checkin()
        return self.discuz.try_checkin()

    def reply_topic(self, tid: int, context: str) -> tuple[bool, str]:
        # 生成回复
        message = self.ai.generate_reply(context=context, signature=self.cfg.bot.signature)
        if self.cfg.bot.dry_run:
            return True, f"[DRY-RUN] 将回复 tid={tid}: {message[:60]}..."
        if self.discuz_browser:
            return self.discuz_browser.reply(tid=tid, message=message)
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

    # ---- Random forum/thread selection with de-dup ----
    def pick_random_thread(self, fids: List[int], max_trials_per_forum: int = 10, max_pages_scan: int = 20) -> Optional[Tuple[int, int, str]]:
        import random
        if not fids:
            return None
        # 随机打散fid顺序
        candidates = fids[:]
        random.shuffle(candidates)
        for fid in candidates:
            if self.discuz_browser:
                max_page = self.discuz_browser.forum_max_page(fid)
            else:
                max_page = self.discuz.forum_max_page(fid)
            # 限制页码范围，避免过深
            max_page_use = max(1, min(max_page, max_pages_scan))
            sample_pages = set()
            tries = 0
            while len(sample_pages) < min(max(1, max_trials_per_forum), max_page_use) and tries < max_trials_per_forum * 3:
                sample_pages.add(random.randint(1, max_page_use))
                tries += 1
            for page in sample_pages:
                items = (self.discuz_browser.threads_on_page(fid, page) if self.discuz_browser else self.discuz.threads_on_page(fid, page))
                random.shuffle(items)
                for tid, href in items:
                    if self.storage.has_used_thread(fid, tid):
                        continue
                    final_url = (self.discuz_browser.validate_thread(tid, href) if self.discuz_browser else self.discuz.validate_thread(tid, href))
                    if final_url:
                        # 标记使用并返回（保存最终URL）
                        self.storage.mark_thread_used(fid, tid, final_url)
                        return fid, tid, final_url
            # 兜底顺序扫描（从第一页起），尽量找到一个
            for page in range(1, max_page_use + 1):
                items = (self.discuz_browser.threads_on_page(fid, page) if self.discuz_browser else self.discuz.threads_on_page(fid, page))
                for tid, href in items:
                    if self.storage.has_used_thread(fid, tid):
                        continue
                    final_url = (self.discuz_browser.validate_thread(tid, href) if self.discuz_browser else self.discuz.validate_thread(tid, href))
                    if final_url:
                        self.storage.mark_thread_used(fid, tid, final_url)
                        return fid, tid, final_url
        return None


class AccountRunner:
    """围绕账号（或Cookie）执行任务的Runner。"""

    def __init__(self, cfg: AppConfig, account: Optional[dict] = None) -> None:
        # account: dict from AccountConfig.model_dump()
        base_url = (account.get("base_url") if account else None) or cfg.site.base_url
        user_agent = (account.get("user_agent") if account else None) or cfg.site.user_agent
        proxy = cfg.site.proxy  # 允许全局代理
        # 根据配置选择浏览器模式或请求模式
        self.browser_session: Optional[BrowserSession] = None
        self.discuz_browser: Optional[DiscuzBrowserClient] = None
        if getattr(cfg, "browser", None) and cfg.browser.enabled:
            self.browser_session = BrowserSession(
                base_url=base_url,
                user_agent=user_agent,
                proxy=proxy,
                headless=cfg.browser.headless,
                slow_mo=cfg.browser.slow_mo_ms,
                timeout_ms=cfg.browser.timeout_ms,
                engine=cfg.browser.engine,
            )
            self.discuz_browser = DiscuzBrowserClient(self.browser_session)
            self.http = _UrlHelper(base_url)  # type: ignore
            self.discuz = None  # type: ignore
        else:
            self.http = HttpClient(base_url=base_url, user_agent=user_agent, proxy=proxy)
            self.discuz = DiscuzClient(self.http)

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
            if self.browser_session:
                self.browser_session.set_cookies(cookies)
            else:
                self.http.set_cookies(cookies)  # type: ignore

        self.cfg = cfg
        self.account = account or {}
        self.ai = AIResponder(cfg.ai)
        self.storage = Storage(cfg.db_path)

    def login(self) -> bool:
        # 优先cookie；若cookie已登录则True，否则尝试用户名密码
        username = self.account.get("username") or self.cfg.site.username
        password = self.account.get("password") or self.cfg.site.password
        if self.discuz_browser:
            # 访问首页判断是否已登录
            try:
                p = self.browser_session.page  # type: ignore
                p.goto(self.browser_session.base_url + "/", wait_until="domcontentloaded")  # type: ignore
                html = p.content()
                if self.discuz_browser.is_logged_in(html):
                    return True
            except Exception:
                pass
            if username and password:
                return self.discuz_browser.login(username, password)
            return False
        else:
            # 通过访问首页判断是否已登录
            home = self.http.get("/")  # type: ignore
            if home.status_code == 200 and self.discuz.is_logged_in(home.text):  # type: ignore
                return True
            if username and password:
                return self.discuz.login(username, password)  # type: ignore
            return False

    def daily_checkin(self) -> Tuple[bool, str]:
        if self.discuz_browser:
            return self.discuz_browser.try_checkin()
        return self.discuz.try_checkin()  # type: ignore

    # ---- Random forum/thread selection with de-dup (per account session)
    def pick_random_thread(self, fids: List[int], max_trials_per_forum: int = 10, max_pages_scan: int = 20) -> Optional[Tuple[int, int, str]]:
        import random
        if not fids:
            return None
        candidates = fids[:]
        random.shuffle(candidates)
        for fid in candidates:
            if self.discuz_browser:
                max_page = self.discuz_browser.forum_max_page(fid)
            else:
                max_page = self.discuz.forum_max_page(fid)  # type: ignore
            max_page_use = max(1, min(max_page, max_pages_scan))
            sample_pages = set()
            tries = 0
            while len(sample_pages) < min(max(1, max_trials_per_forum), max_page_use) and tries < max_trials_per_forum * 3:
                sample_pages.add(random.randint(1, max_page_use))
                tries += 1
            for page in sample_pages:
                items = (self.discuz_browser.threads_on_page(fid, page) if self.discuz_browser else self.discuz.threads_on_page(fid, page))  # type: ignore
                random.shuffle(items)
                for tid, href in items:
                    if self.storage.has_used_thread(fid, tid):
                        continue
                    final_url = (self.discuz_browser.validate_thread(tid, href) if self.discuz_browser else self.discuz.validate_thread(tid, href))  # type: ignore
                    if final_url:
                        self.storage.mark_thread_used(fid, tid, final_url)
                        return fid, tid, final_url
            for page in range(1, max_page_use + 1):
                items = (self.discuz_browser.threads_on_page(fid, page) if self.discuz_browser else self.discuz.threads_on_page(fid, page))  # type: ignore
                for tid, href in items:
                    if self.storage.has_used_thread(fid, tid):
                        continue
                    final_url = (self.discuz_browser.validate_thread(tid, href) if self.discuz_browser else self.discuz.validate_thread(tid, href))  # type: ignore
                    if final_url:
                        self.storage.mark_thread_used(fid, tid, final_url)
                        return fid, tid, final_url
        return None

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
        if self.discuz_browser:
            return self.discuz_browser.fetch_profile()
        return self.discuz.fetch_profile()  # type: ignore
