from __future__ import annotations

import re
from typing import Optional, Tuple

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

    def login(self, username: str, password: str) -> bool:
        # 1. 打开首页，获取登录链接与 formhash
        r = self.http.get("/")
        r.raise_for_status()
        formhash = self.fetch_formhash(r.text)

        # 2. 尝试常见登录端点（不同站点路径不同，这里做兜底）
        candidates = [
            "/member.php?mod=logging&action=login&loginsubmit=yes&loginhash=xx",
            "/member.php?mod=logging&action=login&loginsubmit=yes",
            "/ucp.php?mod=login",
        ]

        payload_base = {
            "username": username,
            "password": password,
            "formhash": formhash or "",
            "referer": self.http.url("/"),
            "cookietime": 2592000,
        }

        for path in candidates:
            rr = self.http.post(path, data=payload_base)
            if rr.status_code in (200, 302):
                # 粗略判定：是否出现欢迎/退出链接/个人中心等字样
                text = rr.text
                if any(k in text for k in ["欢迎", "退出", "我的帖子", "控制面板", "登录失败" ]) is False:
                    # 有些站点登录成功会 302 到首页；再请求首页确认
                    home = self.http.get("/")
                    if self.is_logged_in(home.text):
                        return True
                else:
                    if self.is_logged_in(text):
                        return True
        return False

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
