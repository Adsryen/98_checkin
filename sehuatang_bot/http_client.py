from __future__ import annotations

import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse


class HttpClient:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout: int = 20,
        retries: int = 3,
        backoff: float = 0.5,
        proxy: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=backoff,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        if proxy:
            self.set_proxy(proxy)

    def set_proxy(self, proxy: Optional[str]):
        if proxy:
            self.session.proxies.update({
                "http": proxy,
                "https": proxy,
            })
        else:
            self.session.proxies.clear()

    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def get(self, path: str, **kwargs):
        return self.session.get(self.url(path), timeout=self.timeout, **kwargs)

    def post(self, path: str, data=None, **kwargs):
        return self.session.post(self.url(path), data=data, timeout=self.timeout, **kwargs)

    def set_cookies(self, cookies: dict):
        # 带域名设置，确保请求会携带
        parsed = urlparse(self.base_url)
        domain = parsed.hostname or None
        for k, v in cookies.items():
            try:
                self.session.cookies.set(k, v, domain=domain, path="/")
            except Exception:
                # 回退到不指定域
                self.session.cookies.set(k, v)

    def get_cookies(self) -> dict:
        return self.session.cookies.get_dict()
