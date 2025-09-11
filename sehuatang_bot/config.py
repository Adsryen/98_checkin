from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field


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


class BotConfig(BaseModel):
    dry_run: bool = Field(default=True, description="是否为干跑模式，不执行真正的发帖/回帖")
    reply_enabled: bool = Field(default=False, description="是否启用自动回帖")
    reply_forums: List[int] = Field(default_factory=list, description="允许自动回帖的版块ID白名单，空为不限制")
    signature: str = Field(default="", description="附加在回复末尾的签名")
    daily_checkin_enabled: bool = Field(default=True)


class AppConfig(BaseModel):
    site: SiteConfig
    ai: OpenAIConfig
    bot: BotConfig = Field(default_factory=BotConfig)


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
    site.setdefault("base_url", os.getenv("SITE_BASE_URL"))
    site.setdefault("username", os.getenv("SITE_USERNAME"))
    site.setdefault("password", os.getenv("SITE_PASSWORD"))
    if os.getenv("SITE_MIRROR_URLS"):
        site["mirror_urls"] = [s.strip() for s in os.getenv("SITE_MIRROR_URLS").split(",") if s.strip()]
    if os.getenv("SITE_UA"):
        site["user_agent"] = os.getenv("SITE_UA")

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

    data["site"] = site
    data["ai"] = ai
    data.setdefault("bot", bot)

    cfg = AppConfig(**data)
    return cfg
