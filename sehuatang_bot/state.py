from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class StateStore:
    """线程安全的运行状态存储。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.last_login_ok: Optional[bool] = None
        self.last_login_time: Optional[float] = None
        self.last_checkin_ok: Optional[bool] = None
        self.last_checkin_msg: str = "未执行"
        self.last_checkin_time: Optional[float] = None
        # 多账号状态：name -> 状态与历史
        self.accounts: Dict[str, Dict[str, Any]] = {}

    def _now(self) -> float:
        return time.time()

    def record_login(self, ok: bool) -> None:
        with self._lock:
            self.last_login_ok = ok
            self.last_login_time = self._now()

    def record_checkin(self, ok: bool, msg: str) -> None:
        with self._lock:
            self.last_checkin_ok = ok
            self.last_checkin_msg = msg
            self.last_checkin_time = self._now()

    # ---- 多账号 ----
    def _ensure_account(self, name: str) -> Dict[str, Any]:
        acc = self.accounts.get(name)
        if not acc:
            acc = {
                "last_login_ok": None,
                "last_login_time": None,
                "last_checkin_ok": None,
                "last_checkin_msg": "未执行",
                "last_checkin_time": None,
                "history": [],  # list[{time, action, ok, msg}]
                "logs": [],     # 简单文本日志
            }
            self.accounts[name] = acc
        return acc

    def acc_log(self, name: str, text: str) -> None:
        with self._lock:
            acc = self._ensure_account(name)
            acc["logs"].append({"time": self._fmt_time(self._now()), "text": text})

    def acc_record_login(self, name: str, ok: bool) -> None:
        with self._lock:
            acc = self._ensure_account(name)
            acc["last_login_ok"] = ok
            acc["last_login_time"] = self._now()
            acc["history"].append({"time": self._fmt_time(self._now()), "action": "login", "ok": ok, "msg": ""})

    def acc_record_checkin(self, name: str, ok: bool, msg: str) -> None:
        with self._lock:
            acc = self._ensure_account(name)
            acc["last_checkin_ok"] = ok
            acc["last_checkin_msg"] = msg
            acc["last_checkin_time"] = self._now()
            acc["history"].append({"time": self._fmt_time(self._now()), "action": "checkin", "ok": ok, "msg": msg})

    def _fmt_time(self, ts: Optional[float]) -> str:
        if not ts:
            return "—"
        lt = time.localtime(ts)
        return time.strftime("%Y-%m-%d %H:%M:%S", lt)

    def task_list(self) -> List[Dict[str, Any]]:
        with self._lock:
            tasks: List[Dict[str, Any]] = []
            # 登录任务
            tasks.append({
                "name": "登录",
                "status": self._status_text(self.last_login_ok),
                "message": "",
                "updated_at": self._fmt_time(self.last_login_time),
            })
            # 签到任务
            tasks.append({
                "name": "每日签到",
                "status": self._status_text(self.last_checkin_ok),
                "message": self.last_checkin_msg,
                "updated_at": self._fmt_time(self.last_checkin_time),
            })
            return tasks

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "last_login": {
                    "ok": self.last_login_ok,
                    "updated_at": self._fmt_time(self.last_login_time),
                },
                "last_checkin": {
                    "ok": self.last_checkin_ok,
                    "message": self.last_checkin_msg,
                    "updated_at": self._fmt_time(self.last_checkin_time),
                },
                "tasks": self.task_list(),
                "accounts": self.accounts,
            }

    def _status_text(self, ok: Optional[bool]) -> str:
        if ok is None:
            return "未执行"
        return "成功" if ok else "失败"


