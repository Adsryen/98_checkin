from __future__ import annotations

import os
import re as _re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import AppConfig, save_config


def _verify_admin_dep(cfg: AppConfig):
    def _verify(request: Request) -> None:
        if cfg.admin_password:
            token = request.cookies.get("admin_authed")
            if token != "1":
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return _verify


def get_router(cfg: AppConfig) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory="templates")

    @router.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, _=Depends(_verify_admin_dep(cfg))):
        saved = True if (request.query_params.get("saved") == "1") else False
        env_overrides = {
            "base_url": os.getenv("SITE_BASE_URL"),
            "proxy": os.getenv("SITE_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY"),
            "ua": os.getenv("SITE_UA"),
        }
        return templates.TemplateResponse("settings.html", {"request": request, "cfg": cfg, "saved": saved, "env_overrides": env_overrides})

    @router.post("/settings", response_class=HTMLResponse)
    async def save_settings(request: Request, _=Depends(_verify_admin_dep(cfg))):
        form = await request.form()
        # 仅允许调整 bot 配置的部分字段
        signature = (form.get("signature") or cfg.bot.signature).strip()
        dry_run = True if (form.get("dry_run") == "on") else False
        daily_checkin_enabled = True if (form.get("daily_checkin_enabled") == "on") else False
        # random_forums: 逗号/空格分隔
        rf_text = (form.get("random_forums") or "").strip()
        # 更稳健：从文本中提取所有数字，支持中文逗号/顿号/空格等任意分隔
        rf_numbers = _re.findall(r"\d+", rf_text)
        rf_list = []
        seen = set()
        for n in rf_numbers:
            v = int(n)
            if v not in seen:
                rf_list.append(v)
                seen.add(v)
        # 站点配置（base_url / proxy / user_agent）
        site_base_url = (form.get("site_base_url") or cfg.site.base_url).strip()
        site_proxy = (form.get("site_proxy") or "").strip() or None
        site_user_agent = (form.get("site_user_agent") or cfg.site.user_agent).strip()

        cfg.bot.signature = signature
        cfg.bot.dry_run = dry_run
        cfg.bot.daily_checkin_enabled = daily_checkin_enabled
        cfg.bot.random_forums = rf_list
        cfg.site.base_url = site_base_url
        cfg.site.proxy = site_proxy
        cfg.site.user_agent = site_user_agent
        save_config(cfg)
        return RedirectResponse(url="/settings?saved=1", status_code=302)

    return router
