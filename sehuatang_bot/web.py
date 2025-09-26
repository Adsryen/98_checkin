from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

from .config import AppConfig, save_config
from .runner import Runner, AccountRunner
from .state import StateStore
from .storage import Storage
from .webapp.routes_api import get_router as get_api_router
from .webapp.routes_tasks import get_router as get_tasks_router
from .webapp.routes_settings import get_router as get_settings_router
from .webapp.routes_accounts import get_router as get_accounts_router


def create_app(cfg: AppConfig, state: StateStore) -> FastAPI:
    app = FastAPI(title="98 Checkin", version="0.1.0")

    templates = Jinja2Templates(directory="templates")
    # 提供本地静态资源（样式/图片等），用于CDN不可达时的回退
    app.mount("/static", StaticFiles(directory="static"), name="static")

    storage = Storage(cfg.db_path)
    # 首次导入旧配置中的 accounts（仅当DB为空）
    if storage.is_accounts_empty() and cfg.accounts:
        storage.import_accounts_from_config(cfg.accounts)

    def verify_admin(request: Request) -> None:
        # 简单会话：使用一个cookie存储已登录标记
        if cfg.admin_password:
            token = request.cookies.get("admin_authed")
            if token != "1":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        # 如果未设置密码，则允许直接访问（假设仅局域网/本地部署）

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return RedirectResponse(url="/tasks")

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        return templates.TemplateResponse("login.html", {"request": request, "has_password": bool(cfg.admin_password)})

    @app.post("/login")
    async def do_login(request: Request):
        if not cfg.admin_password:
            # 无密码直接视作登录成功
            resp = RedirectResponse(url="/settings", status_code=302)
            resp.set_cookie("admin_authed", "1", httponly=True)
            return resp
        form = await request.form()
        password = (form.get("password") or "").strip()
        if password != cfg.admin_password:
            return templates.TemplateResponse("login.html", {"request": request, "has_password": True, "error": "密码错误"}, status_code=401)
        resp = RedirectResponse(url="/settings", status_code=302)
        resp.set_cookie("admin_authed", "1", httponly=True)
        return resp

    @app.get("/logout")
    def logout():
        resp = RedirectResponse(url="/login", status_code=302)
        resp.delete_cookie("admin_authed")
        return resp

    # 注册任务与任务API路由
    app.include_router(get_tasks_router(cfg, state, storage))

    # 注册 Settings 路由
    app.include_router(get_settings_router(cfg))

    # 注册 API 路由（/api/*）
    app.include_router(get_api_router(cfg, state))


    @app.post("/run/checkin")
    async def run_checkin_form(_=Depends(verify_admin)):
        if not cfg.site.base_url or not cfg.site.username or not cfg.site.password:
            return RedirectResponse(url="/settings", status_code=302)
        r = Runner(cfg)
        ok = r.login()
        state.record_login(ok)
        if not ok:
            state.record_checkin(False, "登录失败")
            return RedirectResponse(url="/tasks", status_code=302)
        ok2, msg = r.daily_checkin()
        state.record_checkin(ok2, msg)
        return RedirectResponse(url="/tasks", status_code=302)

    # 注册 Accounts 路由
    app.include_router(get_accounts_router(cfg, storage))

    return app


