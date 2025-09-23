from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field
from typing import Any, Dict


class OpenAIConfig(BaseModel):
    api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    base_url: Optional[str] = Field(default=None, description="OpenAI compatible base url, e.g. https://api.openai.com/v1 or custom gateway")
    model: str = Field(default="gpt-4o-mini", description="Model name")
    temperature: float = Field(default=0.5)
    max_tokens: int = Field(default=200)


class SiteConfig(BaseModel):
    base_url: str = Field(description="主站或镜像站 URL，以 https:// 开头，末尾不要带 /")
    mirror_urls: List[str] = Field(default_factory=list, description="备选镜像站 URL 列表")
    username: str
    password: str
    user_agent: str = Field(default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36")
    proxy: Optional[str] = Field(default=None, description="可选：HTTP/HTTPS 代理，如 http://127.0.0.1:7890")


class BotConfig(BaseModel):
    dry_run: bool = Field(default=True, description="是否为干跑模式，不执行真正的发帖/回帖")
    reply_enabled: bool = Field(default=False, description="是否启用自动回帖")
    reply_forums: List[int] = Field(default_factory=list, description="允许自动回帖的版块ID白名单，空为不限制")
    signature: str = Field(default="", description="附加在回复末尾的签名")
    daily_checkin_enabled: bool = Field(default=True)
    random_forums: List[int] = Field(default_factory=list, description="用于随机抽取帖子的版块ID列表（fid），可设置多个")


class BrowserConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 Playwright 浏览器自动化")
    headless: bool = Field(default=True, description="是否无头运行")
    slow_mo_ms: int = Field(default=0, description="慢动作毫秒（调试用）")
    timeout_ms: int = Field(default=20000, description="页面/操作默认超时时间（毫秒）")
    engine: str = Field(default="chromium", description="浏览器内核：chromium/firefox/webkit")


class AccountConfig(BaseModel):
    # 兼容旧字段：name 已不再展示，使用 remark 作为备注
    name: Optional[str] = Field(default=None, description="(已废弃) 账号名称，保留兼容")
    username: Optional[str] = Field(default=None, description="账号用户名，可选：若使用cookie可为空")
    password: Optional[str] = Field(default=None, description="账号密码，可选：若使用cookie可为空")
    cookie_string: Optional[str] = Field(default=None, description="浏览器导出的cookie字符串，可选")
    cookies: List[str] = Field(default_factory=list, description="以 k=v 形式的cookie列表，可选")
    base_url: Optional[str] = Field(default=None, description="覆盖站点base_url")
    user_agent: Optional[str] = Field(default=None, description="覆盖UA")
    remark: Optional[str] = Field(default=None, description="备注")


class AppConfig(BaseModel):
    site: SiteConfig
    ai: OpenAIConfig
    bot: BotConfig = Field(default_factory=BotConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    server_port: int = Field(default=9898, description="Web服务端口，默认9898")
    admin_password: Optional[str] = Field(default=None, description="后台管理员密码；若为空则仅本地访问允许设置")
    accounts: List[AccountConfig] = Field(default_factory=list, description="多账号列表；为空时使用全局site.username/password")
    db_path: str = Field(default="./data.sqlite3", description="SQLite 数据库文件路径")


DEFAULT_CONFIG_PATHS = [
    "./config.yaml",
    "./config.yml",
    "./sehuatang.yaml",
]


def load_config(path: Optional[str] = None) -> AppConfig:
    # env override
    env_path = os.getenv("CONFIG_PATH")
    if path is None and env_path:
        path = env_path

    data = {}
    loaded = False

    paths = [path] if path else DEFAULT_CONFIG_PATHS
    for p in paths:
        if p and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                loaded = True
            break

    # allow env override
    # SITE_
    site = data.get("site", {})
    # 仅当环境变量存在时覆盖
    if os.getenv("SITE_BASE_URL"):
        site["base_url"] = os.getenv("SITE_BASE_URL")
    if os.getenv("SITE_USERNAME"):
        site["username"] = os.getenv("SITE_USERNAME")
    if os.getenv("SITE_PASSWORD"):
        site["password"] = os.getenv("SITE_PASSWORD")
    # 兜底默认：避免为 None 触发 Pydantic 校验错误
    site.setdefault("base_url", "https://www.sehuatang.net")
    site.setdefault("username", "")
    site.setdefault("password", "")
    if os.getenv("SITE_MIRROR_URLS"):
        site["mirror_urls"] = [s.strip() for s in os.getenv("SITE_MIRROR_URLS").split(",") if s.strip()]
    if os.getenv("SITE_UA"):
        site["user_agent"] = os.getenv("SITE_UA")
    # 代理：优先 SITE_PROXY，否则 HTTP_PROXY/HTTPS_PROXY
    proxy_env = os.getenv("SITE_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if proxy_env:
        site["proxy"] = proxy_env

    # AI_
    ai = data.get("ai", {})
    if os.getenv("AI_API_KEY"):
        ai["api_key"] = os.getenv("AI_API_KEY")
    if os.getenv("AI_BASE_URL"):
        ai["base_url"] = os.getenv("AI_BASE_URL")
    if os.getenv("AI_MODEL"):
        ai["model"] = os.getenv("AI_MODEL")
    if os.getenv("AI_TEMPERATURE"):
        ai["temperature"] = float(os.getenv("AI_TEMPERATURE"))
    if os.getenv("AI_MAX_TOKENS"):
        ai["max_tokens"] = int(os.getenv("AI_MAX_TOKENS"))

    # BOT_
    bot = data.get("bot", {})
    if os.getenv("BOT_DRY_RUN"):
        bot["dry_run"] = os.getenv("BOT_DRY_RUN").lower() in ("1", "true", "yes")
    if os.getenv("BOT_REPLY_ENABLED"):
        bot["reply_enabled"] = os.getenv("BOT_REPLY_ENABLED").lower() in ("1", "true", "yes")
    if os.getenv("BOT_REPLY_FORUMS"):
        bot["reply_forums"] = [int(x.strip()) for x in os.getenv("BOT_REPLY_FORUMS").split(",") if x.strip()]
    if os.getenv("BOT_SIGNATURE"):
        bot["signature"] = os.getenv("BOT_SIGNATURE")
    if os.getenv("BOT_DAILY_CHECKIN_ENABLED"):
        bot["daily_checkin_enabled"] = os.getenv("BOT_DAILY_CHECKIN_ENABLED").lower() in ("1", "true", "yes")

    # BROWSER_
    browser = data.get("browser", {})
    if os.getenv("BROWSER_ENABLED"):
        browser["enabled"] = os.getenv("BROWSER_ENABLED").lower() in ("1", "true", "yes")
    if os.getenv("BROWSER_HEADLESS"):
        browser["headless"] = os.getenv("BROWSER_HEADLESS").lower() in ("1", "true", "yes")
    if os.getenv("BROWSER_SLOW_MO_MS"):
        try:
            browser["slow_mo_ms"] = int(os.getenv("BROWSER_SLOW_MO_MS"))
        except Exception:
            pass
    if os.getenv("BROWSER_TIMEOUT_MS"):
        try:
            browser["timeout_ms"] = int(os.getenv("BROWSER_TIMEOUT_MS"))
        except Exception:
            pass
    if os.getenv("BROWSER_ENGINE"):
        browser["engine"] = os.getenv("BROWSER_ENGINE")

    data["site"] = site
    data["ai"] = ai
    data.setdefault("bot", bot)
    data.setdefault("browser", browser)
    # accounts 加载并兜底
    accounts = data.get("accounts") or []
    if isinstance(accounts, list) is False:
        accounts = []
    data["accounts"] = accounts

    # SERVER_
    if os.getenv("SERVER_PORT"):
        data["server_port"] = int(os.getenv("SERVER_PORT"))
    if os.getenv("ADMIN_PASSWORD"):
        data["admin_password"] = os.getenv("ADMIN_PASSWORD")
    if os.getenv("DB_PATH"):
        data["db_path"] = os.getenv("DB_PATH")

    cfg = AppConfig(**data)
    return cfg


def save_config(cfg: AppConfig, path: Optional[str] = None) -> str:
    """将当前配置保存为 YAML。
    如果未提供路径，则优先保存到已有的第一个默认路径；若都不存在，则写入 ./config.yaml。
    返回最终保存的文件路径。
    """
    # 选择保存路径
    target_path = path
    if not target_path:
        for p in DEFAULT_CONFIG_PATHS:
            if os.path.exists(p):
                target_path = p
                break
        if not target_path:
            target_path = "./config.yaml"

    # 生成可序列化的 dict
    data: Dict[str, Any] = cfg.model_dump(exclude_none=True)
    # 写入 YAML
    with open(target_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return target_path
