from __future__ import annotations

from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..config import AppConfig
from ..runner import Runner, AccountRunner
from ..state import StateStore
from ..storage import Storage


def _verify_admin_dep(cfg: AppConfig):
    def _verify(request: Request) -> None:
        if cfg.admin_password:
            token = request.cookies.get("admin_authed")
            if token != "1":
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return _verify


def get_router(cfg: AppConfig, state: StateStore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/run/checkin")
    async def run_checkin(_=Depends(_verify_admin_dep(cfg))):
        # 基本配置检查
        if not cfg.site.base_url or not cfg.site.username or not cfg.site.password:
            return JSONResponse({"ok": False, "message": "请先在配置中填写站点 base_url / username / password"}, status_code=400)
        r = Runner(cfg)
        ok = r.login()
        state.record_login(ok)
        if not ok:
            state.record_checkin(False, "登录失败")
            return JSONResponse({"ok": False, "message": "登录失败"}, status_code=400)
        ok2, msg = r.daily_checkin()
        state.record_checkin(ok2, msg)
        return JSONResponse({"ok": ok2, "message": msg})

    @router.post("/api/random-thread")
    async def api_random_thread(request: Request, _=Depends(_verify_admin_dep(cfg))):
        # 使用配置中的随机版块列表，或由请求体覆盖
        fids: List[int] = cfg.bot.random_forums[:] if cfg.bot.random_forums else []
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            if body.get("fid") is not None:
                try:
                    fids = [int(body.get("fid"))]
                except Exception:
                    pass
            elif body.get("fids") and isinstance(body.get("fids"), list):
                try:
                    fids = [int(x) for x in body.get("fids") if str(x).isdigit()]
                except Exception:
                    pass
        if not fids:
            return JSONResponse({"ok": False, "message": "请先在设置中填写随机抽帖的 fid 列表，或在请求体提供 fid/fids"}, status_code=400)
        mps = body.get("max_pages_scan") if isinstance(body, dict) else None
        mtp = body.get("max_trials_per_forum") if isinstance(body, dict) else None
        try:
            max_pages_scan = int(mps) if mps is not None else 30
        except Exception:
            max_pages_scan = 30
        try:
            max_trials_per_forum = int(mtp) if mtp is not None else 12
        except Exception:
            max_trials_per_forum = 12
        # 随机选择一个账户（若无账户，则回退到全局 Runner）
        storage = Storage(cfg.db_path)
        accounts = storage.list_accounts()
        import random as _random
        if accounts:
            acc = _random.choice(accounts)
            runner = AccountRunner(cfg, account=acc)
        else:
            runner = Runner(cfg)
        if not runner.login():
            return JSONResponse({"ok": False, "message": "登录失败"}, status_code=401)
        picked = runner.pick_random_thread(fids, max_trials_per_forum=max_trials_per_forum, max_pages_scan=max_pages_scan)
        if not picked:
            return JSONResponse({"ok": False, "message": "未找到可用的新帖子（可能都被使用或需要更大页范围）"}, status_code=404)
        fid, tid, url = picked
        full_url = runner.http.url(url)
        used_account = None
        try:
            if isinstance(runner, AccountRunner):
                used_account = {
                    "id": acc.get("id"),  # type: ignore[name-defined]
                    "username": acc.get("username"),  # type: ignore[name-defined]
                    "remark": acc.get("remark") or acc.get("name"),  # type: ignore[name-defined]
                    "base_url": acc.get("base_url") or cfg.site.base_url,  # type: ignore[name-defined]
                }
        except Exception:
            used_account = None
        return JSONResponse({"ok": True, "fid": fid, "tid": tid, "url": full_url, "account": used_account})

    return router
