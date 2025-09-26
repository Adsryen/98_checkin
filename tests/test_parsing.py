from __future__ import annotations

import pytest

from sehuatang_bot.core import parsing as P


def test_fetch_formhash_from_input():
    html = '<input type="hidden" name="formhash" value="abc12345" />'
    assert P.fetch_formhash(html) == "abc12345"


def test_fetch_formhash_from_url():
    html = '<a href="/member.php?mod=logging&action=login&formhash=1a2b3c4d">Login</a>'
    assert P.fetch_formhash(html) == "1a2b3c4d"


def test_is_logged_in_true_false():
    assert P.is_logged_in("<div>退出</div>") is True
    assert P.is_logged_in("<div>欢迎游客</div>") is False


def test_parse_forum_max_page_from_html():
    html1 = '<a href="/forum.php?mod=forumdisplay&fid=64&amp;page=12">12</a>'
    assert P.parse_forum_max_page_from_html(html1) >= 12
    html2 = '<span class="last">... 8</span>'
    assert P.parse_forum_max_page_from_html(html2) >= 8


def test_parse_threads_from_html_normalthread():
    html = (
        '<tbody id="normalthread_123">'
        '  <tr><td>'
        '    <a class="xst" href="/forum.php?mod=viewthread&amp;tid=123&amp;extra=page%3D1">Title</a>'
        '  </td></tr>'
        '</tbody>'
    )
    items = P.parse_threads_from_html(html)
    assert (123, "/forum.php?mod=viewthread&tid=123&extra=page%3D1") in items


def test_parse_threads_from_html_static_thread():
    html = '<a href="/thread-456-1-1.html">Title</a>'
    items = P.parse_threads_from_html(html)
    assert (456, "/thread-456-1-1.html") in items


def test_is_bad_thread_html():
    assert P.is_bad_thread_html("抱歉，您无权访问") is True
    assert P.is_bad_thread_html("正常内容") is False
