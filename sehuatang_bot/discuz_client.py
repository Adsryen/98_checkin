from __future__ import annotations

import re
from typing import Optional, Tuple, List

from .http_client import HttpClient


class DiscuzClient:
    """
    Discuz 论坛客户端（骨架）：
    - 登录：抓取登录页 -> 提交 formhash + 用户名/密码
    - 签到：尝试常见签到插件端点
    - 回帖：获取帖子 formhash -> 提交回复
    注意：不同站点的表单字段、路径、验证码、防刷策略可能不同；这里保留可扩展的骨架。
    """

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def fetch_formhash(self, html: str) -> Optional[str]:
        # 常见 formhash 提取
        m = re.search(r'name="formhash"\s+value="([a-zA-Z0-9]{8})"', html)
        if m:
            return m.group(1)
        # 备用：在 cookie 或脚本内可能出现
        m2 = re.search(r'formhash=([a-zA-Z0-9]{8})', html)
        return m2.group(1) if m2 else None

    def fetch_loginhash(self, html: str) -> Optional[str]:
        # Discuz 登录页通常包含 loginhash=xxxx
        m = re.search(r'loginhash=([a-z0-9]+)', html, re.I)
        return m.group(1) if m else None

    def login(self, username: str, password: str) -> bool:
        # 1. 打开首页，获取 formhash；再打开登录页，尽可能获取 loginhash
        r_home = self.http.get("/")
        formhash = self.fetch_formhash(r_home.text) if r_home.status_code == 200 else None

        r_login = self.http.get("/member.php?mod=logging&action=login")
        loginhash = self.fetch_loginhash(r_login.text) if r_login.status_code == 200 else None

        # 2. 构造 payload 与候选端点
        payload = {
            "fastloginfield": "username",
            "username": username,
            "cookietime": 2592000,
            "password": password,
            "formhash": formhash or "",
            "quickforward": "yes",
            "handlekey": "ls",
        }
        candidates = [
            "/member.php?mod=logging&action=login&loginsubmit=yes&infloat=yes&lssubmit=yes&inajax=1",
            "/member.php?mod=logging&action=login&loginsubmit=yes",
        ]
        if loginhash:
            candidates.insert(0, f"/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={loginhash}")

        # 3. 依次尝试端点
        headers = {
            "Referer": self.http.url("/forum.php"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        for path in candidates:
            rr = self.http.post(path, data=payload, headers=headers)
            if rr.status_code in (200, 302):
                # 成功判定：立即文本判定或回到首页检查
                text = rr.text
                if self.is_logged_in(text):
                    return True
                home = self.http.get("/")
                if self.is_logged_in(home.text):
                    return True
        return False

    def fetch_profile(self) -> Tuple[bool, dict | str]:
        """获取个人资料页并解析用户组、积分、金钱、色币、评分。"""
        r = self.http.get("/home.php?mod=space")
        if r.status_code != 200:
            return False, f"请求失败：{r.status_code}"
        html = r.text
        # 用户组
        m_g = re.search(r"用户组[^<]*?<a[^>]*>([^<]+)</a>", html)
        user_group = m_g.group(1).strip() if m_g else None
        # 积分/金钱/色币/评分（在统计信息区域）
        def grab(label: str) -> int | None:
            m = re.search(rf"<li><em>\s*{label}\s*</em>\s*([0-9]+)\s*</li>", html)
            return int(m.group(1)) if m else None

        points = grab("积分")
        money = grab("金钱")
        secoin = grab("色币")
        score = grab("评分")

        data = {
            "user_group": user_group,
            "points": points,
            "money": money,
            "secoin": secoin,
            "score": score,
        }
        return True, data

    def is_logged_in(self, html: str) -> bool:
        # 简单判定；实际可根据站点模板进行自定义
        if any(x in html for x in ["退出", "我的", "用户组", "控制面板"]):
            return True
        return False

    def try_checkin(self) -> Tuple[bool, str]:
        """尝试常见签到插件端点，返回 (成功与否, 信息)。"""
        endpoints = [
            "/plugin.php?id=k_misign:sign",  # 常见 MI 签到
            "/plugin.php?id=dsu_paulsign:sign",
            "/plugin.php?id=dc_signin:sign",
            "/plugin.php?id=fx_checkin:checkin",
        ]
        for ep in endpoints:
            r = self.http.get(ep)
            if r.status_code != 200:
                continue
            formhash = self.fetch_formhash(r.text)
            # 常见提交字段（不同插件不同，这里尝试通用）
            payload = {
                "formhash": formhash or "",
                "qdmode": 3,
                "todaysay": "",
                "qdxq": "kx",  # 心情 (可选)：kx 开心，ng 难过等
            }
            # 尝试提交
            rr = self.http.post(ep, data=payload)
            if rr.status_code in (200, 302):
                if any(k in rr.text for k in ["签到成功", "已签到", "累计签到", "恭喜"]):
                    return True, "签到成功"
        return False, "未找到可用签到端点或失败"

    def reply(self, tid: int, message: str) -> Tuple[bool, str]:
        # 1. 打开帖子页，取 formhash
        r = self.http.get(f"/thread-{tid}-1-1.html")
        if r.status_code != 200:
            return False, f"获取帖子失败：{r.status_code}"
        formhash = self.fetch_formhash(r.text)
        if not formhash:
            return False, "未找到 formhash"

        # 2. 提交回帖（不同站点路径可能不同，这里尝试通用 post 端点）
        payload = {
            "formhash": formhash,
            "message": message,
            "posttime": "",
            "usesig": 1,
            "subject": "",
            "replysubmit": "yes",
        }
        rr = self.http.post(f"/forum.php?mod=post&action=reply&fid=0&tid={tid}&extra=&replysubmit=yes&infloat=yes&handlekey=fastpost&inajax=1", data=payload)
        if rr.status_code in (200, 302):
            if any(x in rr.text for x in ["发布成功", "回帖成功", "非常感谢", "查看自己的帖子"]):
                return True, "回帖成功"
        return False, "回帖失败或触发限制"

    # ---- Forum scraping helpers ----
    def forum_max_page(self, fid: int) -> int:
        r = self.http.get(f"/forum.php?mod=forumdisplay&fid={fid}")
        if r.status_code != 200:
            return 1
        import re as _re
        m = _re.search(r"/forum\\.php\?mod=forumdisplay&fid=\d+&amp;page=(\d+)", r.text)
        last = 1
        if m:
            try:
                last = int(m.group(1))
            except Exception:
                last = 1
        # 进一步尝试 class="last">... N
        m2 = _re.search(r"class=\"last\">\\.\\.\\.\s*(\d+)<", r.text)
        if m2:
            try:
                last = max(last, int(m2.group(1)))
            except Exception:
                pass
        return last if last >= 1 else 1

    def threads_on_page(self, fid: int, page: int) -> List[Tuple[int, str]]:
        url = f"/forum.php?mod=forumdisplay&fid={fid}&page={page}"
        r = self.http.get(url)
        if r.status_code != 200:
            return []
        import re as _re
        html = r.text
        # 优先：仅解析普通主题 tbody：id="normalthread_XXXX"
        threads: List[Tuple[int, str]] = []
        for block in _re.finditer(r"<tbody\\s+id=\"normalthread_(\\d+)\">([\\s\\S]*?)</tbody>", html):
            tid_str, chunk = block.group(1), block.group(2)
            try:
                tid = int(tid_str)
            except Exception:
                continue
            m = _re.search(r"href=\"((?:/)?forum\\.php\?mod=viewthread(?:&|&amp;)tid=(\\d+)[^\"]*)\"", chunk)
            if m:
                href = m.group(1)
                threads.append((tid, href))
        # 兜底：解析 a.s.xst 标题链接（Discuz 通用）
        if not threads:
            for m in _re.finditer(r"<a[^>]+class=\"[^\"]*\\bxst\\b[^\"]*\"[^>]+href=\"((?:/)?forum\\.php\?mod=viewthread(?:&|&amp;)tid=(\\d+)[^\"]*)\"", html):
                href, tid_str = m.group(1), m.group(2)
                try:
                    tid = int(tid_str)
                except Exception:
                    continue
                threads.append((tid, href))
        # 再兜底：页面上任何 viewthread 链接
        if not threads:
            for m in _re.finditer(r"href=\"((?:/)?forum\\.php\?mod=viewthread(?:&|&amp;)tid=(\\d+)[^\"]*)\"", html):
                href, tid_str = m.group(1), m.group(2)
                try:
                    tid = int(tid_str)
                except Exception:
                    continue
                threads.append((tid, href))
        # 最后兜底：伪静态 thread-<tid>-1-1.html
        if not threads:
            for m in _re.finditer(r"href=\"(/thread-(\\d+)-\\d+-\\d+\\.html)\"", html):
                href, tid_str = m.group(1), m.group(2)
                try:
                    tid = int(tid_str)
                except Exception:
                    continue
                threads.append((tid, href))
        # 归一化：补全前导斜杠，去重
        seen = set()
        norm: List[Tuple[int, str]] = []
        for tid, href in threads:
            if not href.startswith("/"):
                href = "/" + href
            key = (tid, href)
            if key in seen:
                continue
            seen.add(key)
            norm.append((tid, href))
        return norm

    def validate_thread(self, tid: int, href: Optional[str] = None) -> Optional[str]:
        # href 可能是相对路径且带有 &amp;，需要还原
        path = (href or f"/forum.php?mod=viewthread&tid={tid}").replace("&amp;", "&")
        r = self.http.get(path)
        if r.status_code != 200:
            return None
        bad = ["不存在", "无权", "删除", "错误", "小黑屋", "抱歉"]
        if any(b in r.text for b in bad):
            return None
        # 返回最终URL（可能已跳转到伪静态 thread-xxxx-1-1.html）
        try:
            return str(r.url)
        except Exception:
            return f"/forum.php?mod=viewthread&tid={tid}"
