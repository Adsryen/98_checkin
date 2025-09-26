from __future__ import annotations

import random

from sehuatang_bot.runner import Runner
from sehuatang_bot.config import AppConfig, SiteConfig, OpenAIConfig


class FakeService:
    def __init__(self) -> None:
        self._threads = {
            1: {1: "/thread-1-1-1.html", 2: "/thread-2-1-1.html"},
            2: {10: "/thread-10-1-1.html"},
        }

    def check_logged_in(self) -> bool:
        return True

    def login(self, username: str, password: str) -> bool:
        return True

    def try_checkin(self):
        return True, "OK"

    def reply(self, tid: int, message: str):
        return True, "OK"

    def fetch_profile(self):
        return True, {}

    def forum_max_page(self, fid: int) -> int:
        return 1

    def threads_on_page(self, fid: int, page: int):
        items = self._threads.get(fid, {})
        return [(tid, url) for tid, url in items.items()]

    def validate_thread(self, tid: int, href: str | None = None):
        return href or f"/thread-{tid}-1-1.html"

    def absolute_url(self, path: str) -> str:
        return "https://example.com" + (path if path.startswith("/") else "/" + path)


class DummyRunner(Runner):
    def __init__(self) -> None:
        cfg = AppConfig(
            site=SiteConfig(base_url="https://example.com", mirror_urls=[], username="", password="", user_agent="UA"),
            ai=OpenAIConfig(model="gpt-4o-mini"),
        )
        # 调用父构造后覆盖 service
        super().__init__(cfg)
        self.service = FakeService()
        # storage 用内存 stub：通过 monkeypatch 或简单替换为轻量对象
        class MemStore:
            def __init__(self):
                self.used = set()
            def has_used_thread(self, fid, tid):
                return (fid, tid) in self.used
            def mark_thread_used(self, fid, tid, url=None):
                self.used.add((fid, tid))
        self.storage = MemStore()


def test_pick_random_thread_basic():
    r = DummyRunner()
    picked = r.pick_random_thread([1, 2], max_trials_per_forum=5, max_pages_scan=2)
    assert picked is not None
    fid, tid, url = picked
    # 标记后再次选择，应该能选到不同帖子，直到耗尽
    r.storage.mark_thread_used(fid, tid, url)
    picked2 = r.pick_random_thread([1, 2], max_trials_per_forum=5, max_pages_scan=2)
    assert picked2 is not None
    if picked2:
        fid2, tid2, url2 = picked2
        assert (fid2, tid2) != (fid, tid)


def test_pick_random_thread_exhausted():
    r = DummyRunner()
    # 将所有帖子标记为已用
    for fid in [1, 2]:
        for tid, url in r.service.threads_on_page(fid, 1):
            r.storage.mark_thread_used(fid, tid, url)
    assert r.pick_random_thread([1, 2], max_trials_per_forum=3, max_pages_scan=1) is None
