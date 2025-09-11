from __future__ import annotations

import sys
from typing import Optional

import click

from .config import load_config
from .runner import Runner


@click.group()
@click.option("--config", "config_path", type=click.Path(exists=False, dir_okay=False), default=None, help="配置文件路径，默认自动搜索 config.yaml/sehuatang.yaml")
@click.pass_context
def cli(ctx: click.Context, config_path: Optional[str]):
    """Sehuatang Discuz 自动签到与回帖工具"""
    cfg = load_config(config_path)
    ctx.ensure_object(dict)
    ctx.obj["cfg"] = cfg


@cli.command()
@click.pass_context
def login(ctx: click.Context):
    cfg = ctx.obj["cfg"]
    r = Runner(cfg)
    ok = r.login()
    click.echo(f"登录：{'成功' if ok else '失败'}")
    sys.exit(0 if ok else 1)


@cli.command()
@click.pass_context
def checkin(ctx: click.Context):
    cfg = ctx.obj["cfg"]
    r = Runner(cfg)
    if not r.login():
        click.echo("登录失败")
        sys.exit(1)
    ok, msg = r.daily_checkin()
    click.echo(f"签到：{'成功' if ok else '失败'} - {msg}")
    sys.exit(0 if ok else 2)


@cli.command("reply")
@click.option("--tid", type=int, required=True, help="主题ID")
@click.option("--context", type=str, required=True, help="用于生成回复的帖文上下文/摘要")
@click.pass_context
def reply_cmd(ctx: click.Context, tid: int, context: str):
    cfg = ctx.obj["cfg"]
    r = Runner(cfg)
    if not r.login():
        click.echo("登录失败")
        sys.exit(1)
    ok, msg = r.reply_topic(tid=tid, context=context)
    click.echo(f"回帖：{'成功' if ok else '失败'} - {msg}")
    sys.exit(0 if ok else 3)


@cli.command("run-all")
@click.pass_context
def run_all_cmd(ctx: click.Context):
    cfg = ctx.obj["cfg"]
    r = Runner(cfg)
    res = r.run_all()
    click.echo(f"登录：{'成功' if res['login'] else '失败'}")
    ok, msg = res.get("checkin", (False, "未执行"))
    click.echo(f"签到：{'成功' if ok else '失败'} - {msg}")
    # 非零表示存在失败
    sys.exit(0 if (res["login"] and ok) else 10)


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
