from __future__ import annotations

from typing import Protocol, Optional, Tuple, List


class DiscuzServiceProtocol(Protocol):
    """统一的 Discuz 服务接口，便于切换 requests 与浏览器两种实现。"""

    def login(self, username: str, password: str) -> bool:
        ...

    def check_logged_in(self) -> bool:
        """检测当前会话（可能基于 Cookie）是否已登录。"""
        ...

    def try_checkin(self) -> Tuple[bool, str]:
        ...

    def reply(self, tid: int, message: str) -> Tuple[bool, str]:
        ...

    def fetch_profile(self) -> Tuple[bool, dict | str]:
        ...

    def forum_max_page(self, fid: int) -> int:
        ...

    def threads_on_page(self, fid: int, page: int) -> List[Tuple[int, str]]:
        ...

    def validate_thread(self, tid: int, href: Optional[str] = None) -> Optional[str]:
        ...

    def absolute_url(self, path: str) -> str:
        ...
