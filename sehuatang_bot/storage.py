from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class Storage:
    def __init__(self, db_path: str = "./data.sqlite3") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  username TEXT,
                  password TEXT,
                  cookie_string TEXT,
                  base_url TEXT,
                  user_agent TEXT,
                  created_at REAL,
                  updated_at REAL
                );
                """
            )
            # 迁移：accounts 表新增 remark 列
            try:
                cur = self._conn.execute("PRAGMA table_info(accounts)")
                cols = {row[1] for row in cur.fetchall()}
                if "remark" not in cols:
                    self._conn.execute("ALTER TABLE accounts ADD COLUMN remark TEXT")
            except Exception:
                pass
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_state (
                  account_id INTEGER PRIMARY KEY,
                  last_login_ok INTEGER,
                  last_login_time REAL,
                  last_checkin_ok INTEGER,
                  last_checkin_msg TEXT,
                  last_checkin_time REAL,
                  FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_history (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  account_id INTEGER NOT NULL,
                  time REAL NOT NULL,
                  action TEXT NOT NULL,
                  ok INTEGER NOT NULL,
                  msg TEXT,
                  FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_logs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  account_id INTEGER NOT NULL,
                  time REAL NOT NULL,
                  text TEXT NOT NULL,
                  FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_profile (
                  account_id INTEGER PRIMARY KEY,
                  user_group TEXT,
                  points INTEGER,
                  money INTEGER,
                  secoin INTEGER,
                  score INTEGER,
                  updated_at REAL,
                  FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
                );
                """
            )
            # 已使用的帖子（避免二次使用）
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS used_threads (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  fid INTEGER NOT NULL,
                  tid INTEGER NOT NULL,
                  url TEXT,
                  used_at REAL NOT NULL,
                  UNIQUE(fid, tid)
                );
                """
            )

    # ---- Accounts ----
    def list_accounts(self) -> List[Dict[str, Any]]:
        cur = self._conn.execute("SELECT * FROM accounts ORDER BY id ASC")
        rows = [dict(r) for r in cur.fetchall()]
        return rows

    def list_accounts_summary(self) -> List[Dict[str, Any]]:
        sql = (
            "SELECT a.*, p.user_group, p.points, p.money, p.secoin, p.score, s.last_login_ok, s.last_checkin_ok "
            "FROM accounts a "
            "LEFT JOIN account_profile p ON p.account_id = a.id "
            "LEFT JOIN account_state s ON s.account_id = a.id "
            "ORDER BY a.id ASC"
        )
        cur = self._conn.execute(sql)
        return [dict(r) for r in cur.fetchall()]

    def is_accounts_empty(self) -> bool:
        cur = self._conn.execute("SELECT COUNT(1) FROM accounts")
        n = cur.fetchone()[0]
        return n == 0

    def add_account(self, acc: Dict[str, Any]) -> int:
        now = time.time()
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO accounts (name, username, password, cookie_string, base_url, user_agent, created_at, updated_at, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    # 为兼容旧结构，name 用 remark/username/时间戳
                    (acc.get("remark") or acc.get("name") or acc.get("username") or f"账号{int(now)}"),
                    acc.get("username"),
                    acc.get("password"),
                    acc.get("cookie_string"),
                    acc.get("base_url"),
                    acc.get("user_agent"),
                    now,
                    now,
                    acc.get("remark"),
                ),
            )
            return int(cur.lastrowid)

    def delete_account(self, account_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    def get_account_by_index(self, idx: int) -> Optional[Dict[str, Any]]:
        accs = self.list_accounts()
        if idx < 0 or idx >= len(accs):
            return None
        return accs[idx]

    def get_account_by_id(self, account_id: int) -> Optional[Dict[str, Any]]:
        cur = self._conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def update_account(self, account_id: int, updates: Dict[str, Any]) -> None:
        fields = []
        values: List[Any] = []
        for k in ["username", "password", "cookie_string", "base_url", "user_agent", "remark"]:
            if k in updates:
                fields.append(f"{k} = ?")
                values.append(updates[k])
        if not fields:
            return
        fields.append("updated_at = ?")
        import time as _t
        values.append(_t.time())
        values.append(account_id)
        with self._conn:
            self._conn.execute(f"UPDATE accounts SET {', '.join(fields)} WHERE id = ?", tuple(values))

    # ---- State & History ----
    def _upsert_state_login(self, account_id: int, ok: bool, ts: float) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO account_state (account_id, last_login_ok, last_login_time)
                VALUES (?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                  last_login_ok=excluded.last_login_ok,
                  last_login_time=excluded.last_login_time
                """,
                (account_id, 1 if ok else 0, ts),
            )

    def _upsert_state_checkin(self, account_id: int, ok: bool, msg: str, ts: float) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO account_state (account_id, last_checkin_ok, last_checkin_msg, last_checkin_time)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                  last_checkin_ok=excluded.last_checkin_ok,
                  last_checkin_msg=excluded.last_checkin_msg,
                  last_checkin_time=excluded.last_checkin_time
                """,
                (account_id, 1 if ok else 0, msg, ts),
            )

    def record_account_login(self, account_id: int, ok: bool) -> None:
        ts = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT INTO account_history (account_id, time, action, ok, msg) VALUES (?, ?, ?, ?, ?)",
                (account_id, ts, "login", 1 if ok else 0, ""),
            )
        self._upsert_state_login(account_id, ok, ts)

    def record_account_checkin(self, account_id: int, ok: bool, msg: str) -> None:
        ts = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT INTO account_history (account_id, time, action, ok, msg) VALUES (?, ?, ?, ?, ?)",
                (account_id, ts, "checkin", 1 if ok else 0, msg),
            )
        self._upsert_state_checkin(account_id, ok, msg, ts)

    def append_log(self, account_id: int, text: str) -> None:
        ts = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT INTO account_logs (account_id, time, text) VALUES (?, ?, ?)",
                (account_id, ts, text),
            )

    def get_account_state(self, account_id: int, history_limit: int = 100, logs_limit: int = 200) -> Dict[str, Any]:
        cur = self._conn.execute("SELECT * FROM account_state WHERE account_id = ?", (account_id,))
        st = cur.fetchone()
        state = {
            "last_login_ok": None,
            "last_login_time": None,
            "last_checkin_ok": None,
            "last_checkin_msg": "未执行",
            "last_checkin_time": None,
            "history": [],
            "logs": [],
        }
        def fmt(ts: Optional[float]) -> Optional[str]:
            if not ts:
                return None
            import time as _t
            return _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(ts))

        if st:
            state["last_login_ok"] = bool(st["last_login_ok"]) if st["last_login_ok"] is not None else None
            state["last_login_time"] = fmt(st["last_login_time"]) if st["last_login_time"] else None
            state["last_checkin_ok"] = bool(st["last_checkin_ok"]) if st["last_checkin_ok"] is not None else None
            state["last_checkin_msg"] = st["last_checkin_msg"] or "未执行"
            state["last_checkin_time"] = fmt(st["last_checkin_time"]) if st["last_checkin_time"] else None

        cur = self._conn.execute(
            "SELECT time, action, ok, msg FROM account_history WHERE account_id = ? ORDER BY time DESC LIMIT ?",
            (account_id, history_limit),
        )
        hist = []
        for r in cur.fetchall():
            hist.append({
                "time": fmt(r["time"]),
                "action": r["action"],
                "ok": bool(r["ok"]),
                "msg": r["msg"] or "",
            })
        state["history"] = hist

        cur = self._conn.execute(
            "SELECT time, text FROM account_logs WHERE account_id = ? ORDER BY time DESC LIMIT ?",
            (account_id, logs_limit),
        )
        logs = []
        for r in cur.fetchall():
            logs.append({
                "time": fmt(r["time"]),
                "text": r["text"],
            })
        state["logs"] = logs

        return state

    # ---- Profile ----
    def upsert_profile(self, account_id: int, user_group: Optional[str], points: Optional[int], money: Optional[int], secoin: Optional[int], score: Optional[int]) -> None:
        ts = time.time()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO account_profile (account_id, user_group, points, money, secoin, score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                  user_group=excluded.user_group,
                  points=excluded.points,
                  money=excluded.money,
                  secoin=excluded.secoin,
                  score=excluded.score,
                  updated_at=excluded.updated_at
                """,
                (account_id, user_group, points, money, secoin, score, ts),
            )

    def get_profile(self, account_id: int) -> Dict[str, Any]:
        cur = self._conn.execute("SELECT * FROM account_profile WHERE account_id = ?", (account_id,))
        row = cur.fetchone()
        if not row:
            return {"user_group": None, "points": None, "money": None, "secoin": None, "score": None, "updated_at": None}
        import time as _t
        def fmt(ts: Optional[float]) -> Optional[str]:
            if not ts:
                return None
            return _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(ts))
        return {
            "user_group": row["user_group"],
            "points": row["points"],
            "money": row["money"],
            "secoin": row["secoin"],
            "score": row["score"],
            "updated_at": fmt(row["updated_at"]),
        }

    # ---- Migration helpers ----
    def import_accounts_from_config(self, accounts: List[dict]) -> int:
        if not accounts:
            return 0
        cnt = 0
        for a in accounts:
            self.add_account(a)
            cnt += 1
        return cnt

    # ---- Used threads ----
    def has_used_thread(self, fid: int, tid: int) -> bool:
        cur = self._conn.execute("SELECT 1 FROM used_threads WHERE fid = ? AND tid = ?", (fid, tid))
        return cur.fetchone() is not None

    def mark_thread_used(self, fid: int, tid: int, url: Optional[str] = None) -> None:
        ts = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO used_threads (fid, tid, url, used_at) VALUES (?, ?, ?, ?)",
                (fid, tid, url, ts),
            )

    def list_recent_used_threads(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT fid, tid, url, used_at FROM used_threads ORDER BY used_at DESC LIMIT ?",
            (limit,),
        )
        rows = []
        for r in cur.fetchall():
            rows.append({
                "fid": r["fid"],
                "tid": r["tid"],
                "url": r["url"],
                "used_at": r["used_at"],
            })
        return rows


