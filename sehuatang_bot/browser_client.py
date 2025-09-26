from __future__ import annotations

import re
from typing import Optional, Tuple, List, Dict
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from .core.parsing import (
    fetch_formhash as parse_fetch_formhash,
    is_logged_in as parse_is_logged_in,
    parse_forum_max_page_from_html,
    parse_threads_from_html,
    is_bad_thread_html,
)


class BrowserSession:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        proxy: Optional[str] = None,
        headless: bool = True,
        slow_mo: int = 0,
        timeout_ms: int = 20000,
        engine: str = "chromium",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.proxy = proxy
        self.headless = headless
        self.slow_mo = slow_mo
        self.timeout_ms = timeout_ms
        self.engine = (engine or "chromium").lower()

        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def _ensure_started(self) -> None:
        if self._pw is not None:
            return
        self._pw = sync_playwright().start()
        launch_kwargs = {
            "headless": self.headless,
            "slow_mo": self.slow_mo,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        }
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}
        # 选择浏览器内核
        if self.engine == "firefox":
            browser_type = self._pw.firefox
        elif self.engine == "webkit":
            browser_type = self._pw.webkit
        else:
            browser_type = self._pw.chromium
        self._browser = browser_type.launch(**launch_kwargs)
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
        )
        self._context.set_default_timeout(self.timeout_ms)
        self._page = self._context.new_page()

    def close(self) -> None:
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    # Utilities
    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    @property
    def page(self):
        self._ensure_started()
        return self._page

    @property
    def context(self):
        self._ensure_started()
        return self._context

    def set_cookies(self, cookies: Dict[str, str]) -> None:
        if not cookies:
            return
        self._ensure_started()
        # Derive domain from base_url
        from urllib.parse import urlparse
        parsed = urlparse(self.base_url)
        domain = parsed.hostname or ""
        items = []
        for k, v in cookies.items():
            try:
                items.append({"name": k, "value": v, "domain": domain, "path": "/"})
            except Exception:
                continue
        if items:
            try:
                self._context.add_cookies(items)
            except Exception:
                pass


class DiscuzBrowserClient:
    """
    基于 Playwright 的 Discuz 客户端实现：
    - login
    - try_checkin
    - reply
    - fetch_profile
    - forum_max_page / threads_on_page / validate_thread

    注意：不同站点可能模板有差异，以下写法尽量使用“多候选选择器 + 文本判定”来增加适配性。
    """

    def __init__(self, session: BrowserSession) -> None:
        self.sess = session

    # ---- Common helpers ----
    def fetch_formhash(self, html: str) -> Optional[str]:
        return parse_fetch_formhash(html)

    def is_logged_in(self, html: str) -> bool:
        return parse_is_logged_in(html)

    # ---- Auth & Profile ----
    def login(self, username: str, password: str) -> bool:
        p = self.sess.page
        try:
            p.goto(self.sess.url("/forum.php"), wait_until="domcontentloaded")
        except Exception:
            pass
        r = p.goto(self.sess.url("/member.php?mod=logging&action=login"), wait_until="load")
        # 尝试填充用户名/密码
        selectors_user = [
            "input[name=loginfield]",  # 某些站点有下拉选择
            "input[name=username]",
            "#ls_username",
            "input#username",
        ]
        selectors_pass = [
            "input[name=password]",
            "#ls_password",
            "input#password",
        ]
        filled = False
        for su in selectors_user:
            try:
                if p.query_selector(su):
                    # 有些站点使用 fastloginfield，需要确保为 username
                    try:
                        if su == "input[name=loginfield]":
                            p.fill(su, "username")
                        else:
                            p.fill(su, username)
                    except Exception:
                        continue
                    for sp in selectors_pass:
                        if p.query_selector(sp):
                            p.fill(sp, password)
                            filled = True
                            break
                    if filled:
                        break
            except Exception:
                continue
        # 提交按钮候选
        if filled:
            submit_candidates = [
                "input[name=loginsubmit]",
                "button[name=loginsubmit]",
                "button:has-text(登录)",
                "text=登录 >> xpath=..",  # 登录文本的父节点尝试点击
            ]
            submitted = False
            for sel in submit_candidates:
                try:
                    el = p.query_selector(sel)
                    if el:
                        el.click()
                        submitted = True
                        break
                except Exception:
                    continue
            if not submitted:
                # 兜底：回车提交密码框
                try:
                    p.keyboard.press("Enter")
                except Exception:
                    pass
        # 判定是否登录成功
        try:
            p.wait_for_load_state("networkidle", timeout=self.sess.timeout_ms)
        except Exception:
            pass
        try:
            html = p.content()
        except Exception:
            html = ""
        if self.is_logged_in(html):
            return True
        # 再次访问首页判定
        try:
            p.goto(self.sess.url("/"), wait_until="domcontentloaded")
            html2 = p.content()
            return self.is_logged_in(html2)
        except Exception:
            return False

    def check_logged_in(self) -> bool:
        """通过访问首页判断当前浏览器会话是否已登录（适配 Cookie 场景）。"""
        p = self.sess.page
        try:
            p.goto(self.sess.url("/"), wait_until="domcontentloaded")
            html = p.content()
            return self.is_logged_in(html)
        except Exception:
            return False

    def fetch_profile(self) -> Tuple[bool, dict | str]:
        p = self.sess.page
        r = p.goto(self.sess.url("/home.php?mod=space"), wait_until="load")
        if not r or r.status != 200:
            return False, f"请求失败：{(r.status if r else 'N/A')}"
        html = p.content()
        m_g = re.search(r"用户组[^<]*?<a[^>]*>([^<]+)</a>", html)
        user_group = m_g.group(1).strip() if m_g else None

        def grab(label: str) -> int | None:
            m = re.search(rf"<li><em>\s*{label}\s*</em>\s*([0-9]+)\s*</li>", html)
            return int(m.group(1)) if m else None

        data = {
            "user_group": user_group,
            "points": grab("积分"),
            "money": grab("金钱"),
            "secoin": grab("色币"),
            "score": grab("评分"),
        }
        return True, data

    # ---- Checkin & Reply ----
    def try_checkin(self) -> Tuple[bool, str]:
        p = self.sess.page
        endpoints = [
            "/plugin.php?id=k_misign:sign",
            "/plugin.php?id=dsu_paulsign:sign",
            "/plugin.php?id=dc_signin:sign",
            "/plugin.php?id=fx_checkin:checkin",
        ]
        for ep in endpoints:
            try:
                r = p.goto(self.sess.url(ep), wait_until="load")
                if not r or r.status != 200:
                    continue
                html = p.content()
                formhash = self.fetch_formhash(html) or ""
                payload = {
                    "formhash": formhash,
                    "qdmode": 3,
                    "todaysay": "",
                    "qdxq": "kx",
                }
                # 优先使用页面上下文内的 fetch，以共享 Cookie
                text = self._post_with_cookies(self.sess.url(ep), payload)
                if text and any(k in text for k in ["签到成功", "已签到", "累计签到", "恭喜"]):
                    return True, "签到成功"
            except Exception:
                continue
        return False, "未找到可用签到端点或失败"

    def reply(self, tid: int, message: str) -> Tuple[bool, str]:
        p = self.sess.page
        r = p.goto(self.sess.url(f"/thread-{tid}-1-1.html"), wait_until="load")
        if not r or r.status != 200:
            return False, f"获取帖子失败：{(r.status if r else 'N/A')}"
        html = p.content()
        formhash = self.fetch_formhash(html)
        if not formhash:
            return False, "未找到 formhash"
        payload = {
            "formhash": formhash,
            "message": message,
            "posttime": "",
            "usesig": 1,
            "subject": "",
            "replysubmit": "yes",
        }
        url = self.sess.url(f"/forum.php?mod=post&action=reply&fid=0&tid={tid}&extra=&replysubmit=yes&infloat=yes&handlekey=fastpost&inajax=1")
        try:
            text = self._post_with_cookies(url, payload)
            if text and any(x in text for x in ["发布成功", "回帖成功", "非常感谢", "查看自己的帖子"]):
                return True, "回帖成功"
        except Exception as e:
            return False, f"异常: {e}"
        return False, "回帖失败或触发限制"

    # ---- helpers: POST in page context with cookies ----
    def _post_with_cookies(self, url: str, form: Dict[str, str]) -> Optional[str]:
        p = self.sess.page
        try:
            js = """
            async (url, form) => {
                const fd = new FormData();
                for (const [k, v] of Object.entries(form)) {
                    fd.append(k, v);
                }
                const resp = await fetch(url, { method: 'POST', body: fd, credentials: 'include' });
                return await resp.text();
            }
            """
            return p.evaluate(js, url, form)
        except Exception:
            try:
                # 兜底使用 page.request（可能不会自动带cookie，成功率较低）
                resp = p.request.post(url, form=form)
                return resp.text() if (resp and resp.ok) else None
            except Exception:
                return None

    # ---- Forum scraping helpers ----
    def forum_max_page(self, fid: int) -> int:
        p = self.sess.page
        try:
            r = p.goto(self.sess.url(f"/forum.php?mod=forumdisplay&fid={fid}"), wait_until="domcontentloaded")
            if not r or r.status != 200:
                return 1
            html = p.content()
            return parse_forum_max_page_from_html(html)
        except Exception:
            return 1

    def threads_on_page(self, fid: int, page: int) -> List[Tuple[int, str]]:
        p = self.sess.page
        url = self.sess.url(f"/forum.php?mod=forumdisplay&fid={fid}&page={page}")
        try:
            r = p.goto(url, wait_until="domcontentloaded")
            if not r or r.status != 200:
                return []
            html = p.content()
            return parse_threads_from_html(html)
        except Exception:
            return []

    def validate_thread(self, tid: int, href: Optional[str] = None) -> Optional[str]:
        p = self.sess.page
        path = (href or f"/forum.php?mod=viewthread&tid={tid}").replace("&amp;", "&")
        try:
            r = p.goto(self.sess.url(path), wait_until="domcontentloaded")
            if not r or r.status != 200:
                return None
            html = p.content()
            if is_bad_thread_html(html):
                return None
            return p.url
        except Exception:
            return None

    # ---- URL helper to comply with the unified interface ----
    def absolute_url(self, path: str) -> str:
        return self.sess.url(path)
