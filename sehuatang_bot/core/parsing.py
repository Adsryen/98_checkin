from __future__ import annotations

import re
from typing import List, Optional, Tuple


def fetch_formhash(html: str) -> Optional[str]:
    """从 HTML 中提取常见 Discuz formhash。"""
    if not html:
        return None
    m = re.search(r'name="formhash"\s+value="([a-zA-Z0-9]{8})"', html)
    if m:
        return m.group(1)
    m2 = re.search(r'formhash=([a-zA-Z0-9]{8})', html)
    return m2.group(1) if m2 else None


def is_logged_in(html: str) -> bool:
    """粗略判断是否已登录（不同模板可扩展关键字）。"""
    if not html:
        return False
    return any(x in html for x in ["退出", "我的", "用户组", "控制面板"])  # 可按需扩展


def parse_forum_max_page_from_html(html: str) -> int:
    """解析论坛列表页的最大页码。失败时返回 1。"""
    if not html:
        return 1
    last = 1
    # 匹配链接中的 page=xxx（注意正确的正则转义）
    m = re.search(r"/forum\.php\?mod=forumdisplay&fid=\d+&amp;page=(\d+)", html)
    if m:
        try:
            last = int(m.group(1))
        except Exception:
            last = 1
    # 匹配分页尾部形如：<span class="last">... 12</span>
    m2 = re.search(r'class="last">\.\.\.\s*(\d+)<', html)
    if m2:
        try:
            last = max(last, int(m2.group(1)))
        except Exception:
            pass
    return last if last >= 1 else 1


def _normalize_thread_href(href: str) -> str:
    if not href:
        return href
    return href if href.startswith("/") else "/" + href


def parse_threads_from_html(html: str) -> List[Tuple[int, str]]:
    """从论坛列表页 HTML 中解析 (tid, href) 列表。
    href 可能包含相对路径与 &amp;，调用方可按需替换为 &。
    """
    if not html:
        return []
    threads: List[Tuple[int, str]] = []
    # 1) normalthread tbody
    for block in re.finditer(r'<tbody\s+id="normalthread_(\d+)">([\s\S]*?)</tbody>', html):
        tid_str, chunk = block.group(1), block.group(2)
        try:
            tid = int(tid_str)
        except Exception:
            continue
        m = re.search(r'href="((?:/)?forum\.php\?mod=viewthread(?:&|&amp;)tid=(\d+)[^"]*)"', chunk)
        if m:
            href = m.group(1).replace("&amp;", "&")
            threads.append((tid, href))
    # 2) xst 链接
    if not threads:
        for m in re.finditer(r'<a[^>]+class="[^"]*\bxst\b[^"]*"[^>]+href="((?:/)?forum\.php\?mod=viewthread(?:&|&amp;)tid=(\d+)[^"]*)"', html):
            href, tid_str = m.group(1).replace("&amp;", "&"), m.group(2)
            try:
                tid = int(tid_str)
            except Exception:
                continue
            threads.append((tid, href))
    # 3) 任意 viewthread 链接
    if not threads:
        for m in re.finditer(r'href="((?:/)?forum\.php\?mod=viewthread(?:&|&amp;)tid=(\d+)[^"]*)"', html):
            href, tid_str = m.group(1).replace("&amp;", "&"), m.group(2)
            try:
                tid = int(tid_str)
            except Exception:
                continue
            threads.append((tid, href))
    # 4) 伪静态 thread-<tid>-1-1.html
    if not threads:
        for m in re.finditer(r'href="(/thread-(\d+)-\d+-\d+\.html)"', html):
            href, tid_str = m.group(1), m.group(2)
            try:
                tid = int(tid_str)
            except Exception:
                continue
            threads.append((tid, href))
    # 去重 + 规范化
    seen = set()
    norm: List[Tuple[int, str]] = []
    for tid, href in threads:
        href = _normalize_thread_href(href)
        key = (tid, href)
        if key in seen:
            continue
        seen.add(key)
        norm.append((tid, href))
    return norm


def is_bad_thread_html(html: str) -> bool:
    if not html:
        return True
    bad = ["不存在", "无权", "删除", "错误", "小黑屋", "抱歉"]
    return any(b in html for b in bad)
