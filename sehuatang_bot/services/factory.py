from __future__ import annotations

from typing import Optional, Dict

from ..config import AppConfig
from ..http_client import HttpClient
from ..discuz_client import DiscuzClient


def create_discuz_service(cfg: AppConfig, account: Optional[Dict] = None):
    """根据配置与可选的账号信息，创建统一的 Discuz 服务实例。

    返回的对象应实现以下方法：
    - login(username, password) -> bool
    - try_checkin() -> (bool, str)
    - reply(tid, message) -> (bool, str)
    - fetch_profile() -> (bool, dict|str)
    - forum_max_page(fid) -> int
    - threads_on_page(fid, page) -> list[(tid, href)]
    - validate_thread(tid, href=None) -> Optional[str]
    - absolute_url(path) -> str
    """
    base_url = (account.get("base_url") if account else None) or cfg.site.base_url
    user_agent = (account.get("user_agent") if account else None) or cfg.site.user_agent
    proxy = cfg.site.proxy

    # cookies from account
    cookies: Dict[str, str] = {}
    if account:
        if account.get("cookie_string"):
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

    if getattr(cfg, "browser", None) and cfg.browser.enabled:
        # Browser-based service (lazy import to avoid hard dependency when not used)
        from importlib import import_module
        browser_module = import_module("sehuatang_bot.browser_client")
        BrowserSession = getattr(browser_module, "BrowserSession")
        DiscuzBrowserClient = getattr(browser_module, "DiscuzBrowserClient")
        session = BrowserSession(
            base_url=base_url,
            user_agent=user_agent,
            proxy=proxy,
            headless=cfg.browser.headless,
            slow_mo=cfg.browser.slow_mo_ms,
            timeout_ms=cfg.browser.timeout_ms,
            engine=cfg.browser.engine,
        )
        if cookies:
            session.set_cookies(cookies)
        service = DiscuzBrowserClient(session)
        return service
    else:
        # Requests-based service
        http = HttpClient(base_url=base_url, user_agent=user_agent, proxy=proxy)
        if cookies:
            http.set_cookies(cookies)
        service = DiscuzClient(http)
        return service
