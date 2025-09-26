from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from ..config import AppConfig
from ..state import StateStore
from ..storage import Storage


def get_router(cfg: AppConfig, state: StateStore, storage: Storage) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory="templates")

    @router.get("/tasks", response_class=HTMLResponse)
    def tasks_page(request: Request):
        tasks = state.task_list()
        accounts = storage.list_accounts()
        return templates.TemplateResponse("tasks.html", {"request": request, "tasks": tasks, "accounts": accounts})

    @router.get("/api/tasks")
    def tasks_api():
        return JSONResponse(state.to_dict())

    return router
