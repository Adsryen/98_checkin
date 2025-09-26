from __future__ import annotations

from typing import Tuple, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import AppConfig
from ..runner import Runner, AccountRunner
from ..storage import Storage
from ..http_client import HttpClient


def _verify_admin_dep(cfg: AppConfig):
    def _verify(request: Request) -> None:
        if cfg.admin_password:
            token = request.cookies.get("admin_authed")
            if token != "1":
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return _verify


def get_router(cfg: AppConfig, storage: Storage) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory="templates")

    @router.get("/accounts", response_class=HTMLResponse)
    def accounts_page(request: Request, _=Depends(_verify_admin_dep(cfg))):
        accounts = storage.list_accounts_summary()
        return templates.TemplateResponse("accounts.html", {"request": request, "accounts": accounts, "site": cfg.site})

    @router.get("/accounts/{idx}", response_class=HTMLResponse)
    def account_detail(request: Request, idx: int, _=Depends(_verify_admin_dep(cfg))):
        acc = storage.get_account_by_index(idx)
        if not acc:
            return RedirectResponse(url="/accounts", status_code=302)
        acc_state = storage.get_account_state(acc["id"])
        acc_profile = storage.get_profile(acc["id"])
        return templates.TemplateResponse("account_detail.html", {"request": request, "idx": idx, "acc": acc, "acc_state": acc_state, "acc_profile": acc_profile})

    @router.post("/accounts/add")
    async def accounts_add(request: Request, _=Depends(_verify_admin_dep(cfg))):
        form = await request.form()
        acc = {
            "username": (form.get("username") or "").strip() or None,
            "password": (form.get("password") or "").strip() or None,
            "cookie_string": (form.get("cookie_string") or "").strip() or None,
            "base_url": (form.get("base_url") or "").strip() or None,
            "user_agent": (form.get("user_agent") or "").strip() or None,
            "remark": (form.get("remark") or "").strip() or None,
        }
        storage.add_account(acc)
        return RedirectResponse(url="/accounts", status_code=302)

    @router.post("/accounts/{idx}/delete")
    async def accounts_delete(idx: int, _=Depends(_verify_admin_dep(cfg))):
        acc = storage.get_account_by_index(idx)
        if acc:
            storage.delete_account(acc["id"])
        return RedirectResponse(url="/accounts", status_code=302)

    @router.post("/accounts/{idx}/edit")
    async def accounts_edit(idx: int, request: Request, _=Depends(_verify_admin_dep(cfg))):
        acc = storage.get_account_by_index(idx)
        if not acc:
            return RedirectResponse(url="/accounts", status_code=302)
        form = await request.form()
        updates = {
            "username": (form.get("username") or "").strip() or None,
            "password": (form.get("password") or "").strip() or None,
            "cookie_string": (form.get("cookie_string") or "").strip() or None,
            "base_url": (form.get("base_url") or "").strip() or None,
            "user_agent": (form.get("user_agent") or "").strip() or None,
            "remark": (form.get("remark") or "").strip() or None,
        }
        storage.update_account(acc["id"], updates)
        return RedirectResponse(url="/accounts", status_code=302)

    @router.post("/accounts/{idx}/run/checkin")
    async def account_run_checkin(idx: int, _=Depends(_verify_admin_dep(cfg))):
        acc = storage.get_account_by_index(idx)
        if not acc:
            return RedirectResponse(url="/accounts", status_code=302)
        runner = AccountRunner(cfg, account=acc)
        ok = runner.login()
        storage.record_account_login(acc["id"], ok)
        if not ok:
            storage.record_account_checkin(acc["id"], False, "登录失败")
            return RedirectResponse(url=f"/accounts/{idx}", status_code=302)
        ok2, msg = runner.daily_checkin()
        storage.record_account_checkin(acc["id"], ok2, msg)
        return RedirectResponse(url=f"/accounts/{idx}", status_code=302)

    # ---- JSON API: 逐步验证，不跳转 ----
    def _summarize_response(resp):
        try:
            text = resp.text or ""
        except Exception:
            text = ""
        headers = resp.headers or {}
        server = headers.get("Server") or headers.get("server") or ""
        cf_ray = headers.get("cf-ray") or headers.get("CF-RAY") or ""
        content_type = headers.get("Content-Type") or headers.get("content-type") or ""
        details = (
            f"URL: {resp.request.method} {resp.url}\n"
            f"Status: {resp.status_code} {getattr(resp, 'reason', '')}\n"
            f"Server: {server}\n"
            f"CF-RAY: {cf_ray}\n"
            f"Content-Type: {content_type}\n"
            f"Body snippet (first 400 chars):\n{text[:400]}"
        )
        return details

    def _verify_payload(idx: int):
        acc = storage.get_account_by_index(idx)
        if not acc:
            return None, JSONResponse({"ok": False, "message": "账号不存在"}, status_code=404)
        steps = []
        runner = AccountRunner(cfg, account=acc)

        # Step 0: 当前配置
        used_base = acc.get("base_url") or cfg.site.base_url
        used_proxy = cfg.site.proxy or "(未设置)"
        ua = cfg.site.user_agent
        steps.append({
            "name": "当前配置",
            "ok": True,
            "details": f"base_url={used_base}\nproxy={used_proxy}\nuser_agent={ua}"
        })

        # Step 1: 打开首页
        try:
            r = runner.http.get("/")
            step1_ok = (r.status_code == 200)
            steps.append({
                "name": "打开首页",
                "ok": step1_ok,
                "status": r.status_code,
                "details": _summarize_response(r),
            })
        except Exception as e:
            steps.append({"name": "打开首页", "ok": False, "details": f"异常: {e}"})
            return acc, JSONResponse({"ok": False, "steps": steps})

        # Step 1b: 论坛入口
        try:
            r2 = runner.http.get("/forum.php")
            steps.append({
                "name": "访问 /forum.php",
                "ok": (r2.status_code == 200),
                "status": r2.status_code,
                "details": _summarize_response(r2),
            })
        except Exception as e:
            steps.append({"name": "访问 /forum.php", "ok": False, "details": f"异常: {e}"})

        # Step 1c: robots.txt（便于判断基础拉取是否被WAF拦截）
        try:
            r3 = runner.http.get("/robots.txt")
            steps.append({
                "name": "访问 /robots.txt",
                "ok": (r3.status_code in (200, 301, 302, 403, 404)),
                "status": r3.status_code,
                "details": _summarize_response(r3),
            })
        except Exception as e:
            steps.append({"name": "访问 /robots.txt", "ok": False, "details": f"异常: {e}"})

        # Step 2: 登录/会话
        login_ok = False
        try:
            login_ok = runner.login()
            steps.append({"name": "登录/会话", "ok": login_ok, "details": "已登录" if login_ok else "未登录或失败（可能被403/WAF拦截）"})
            storage.record_account_login(acc["id"], login_ok)
        except Exception as e:
            steps.append({"name": "登录/会话", "ok": False, "details": f"异常: {e}"})

        # Step 3: 资料
        profile_ok = False
        profile_data = None
        if login_ok:
            try:
                ok2, data = runner.fetch_profile()
                profile_ok = ok2
                profile_data = data if ok2 else None
                if ok2 and isinstance(data, dict):
                    # 详细展示资料字段
                    det = (
                        "成功\n"
                        f"用户组: {data.get('user_group') or '—'}\n"
                        f"积分: {data.get('points') if data.get('points') is not None else '—'}\n"
                        f"金钱: {data.get('money') if data.get('money') is not None else '—'}\n"
                        f"色币: {data.get('secoin') if data.get('secoin') is not None else '—'}\n"
                        f"评分: {data.get('score') if data.get('score') is not None else '—'}"
                    )
                    steps.append({"name": "获取资料", "ok": True, "details": det})
                    storage.upsert_profile(
                        acc["id"],
                        user_group=data.get("user_group"),
                        points=data.get("points"),
                        money=data.get("money"),
                        secoin=data.get("secoin"),
                        score=data.get("score"),
                    )
                else:
                    steps.append({"name": "获取资料", "ok": False, "details": data if data else "未知错误"})
            except Exception as e:
                steps.append({"name": "获取资料", "ok": False, "details": f"异常: {e}"})

        # Step 4: 测试镜像（如配置了）
        mirror_reports = []
        mirrors = cfg.site.mirror_urls or []
        if mirrors:
            for m in mirrors[:3]:
                try:
                    tmp = HttpClient(base_url=m, user_agent=cfg.site.user_agent, proxy=cfg.site.proxy)
                    r = tmp.get("/")
                    mirror_reports.append(f"{m} -> {r.status_code}")
                except Exception as e:
                    mirror_reports.append(f"{m} -> EXCEPTION: {e}")
        if mirror_reports:
            steps.append({"name": "镜像连通性", "ok": True, "details": "\n".join(mirror_reports)})

        # 猜测与建议
        suggestions = []
        try:
            s1 = steps[1] if len(steps) > 1 else None
            if s1 and isinstance(s1.get("status"), int) and s1.get("status") == 403:
                suggestions.append("首页返回403：可能被WAF/反爬拦截或IP封禁/代理异常，建议：1) 更换可用镜像 base_url；2) 配置有效代理；3) 更换更真实的User-Agent；4) 稍后重试")
            used_proxy = cfg.site.proxy or "(未设置)"
            if used_proxy and used_proxy != "(未设置)":
                suggestions.append("已设置代理：确认端口/协议正确，且代理能访问外网与目标站点")
            mirrors_list = cfg.site.mirror_urls or []
            if not mirrors_list:
                suggestions.append("可在配置中设置 mirror_urls，验证时会同时测试镜像可用性")
        except Exception:
            pass
        if suggestions:
            steps.append({"name": "建议", "ok": True, "details": "\n- " + "\n- ".join(suggestions)})

        overall = all(s.get("ok") for s in steps if s.get("ok") is not None)
        return acc, JSONResponse({"ok": overall, "steps": steps, "profile": profile_data})

    @router.post("/api/accounts/{idx}/verify")
    async def api_account_verify(idx: int, _=Depends(_verify_admin_dep(cfg))):
        acc, resp = _verify_payload(idx)
        return resp

    @router.post("/accounts/{idx}/verify.json")
    async def api_account_verify_alias(idx: int, _=Depends(_verify_admin_dep(cfg))):
        acc, resp = _verify_payload(idx)
        return resp

    return router
