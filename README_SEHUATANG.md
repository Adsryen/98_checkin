# 色花堂（Discuz）自动签到与回帖框架

本项目提供一个最小可运行的 Python 框架，用于在 Discuz 论坛（以 `https://www.sehuatang.net` 为例）进行自动登录、签到与回帖（可选 AI 生成回复，OpenAI 协议兼容）。

当前实现为通用骨架，针对不同 Discuz 站点模板与插件可能需做适配；已内置常见签到插件端点探测与通用回帖提交逻辑，支持干跑（不真正发帖）。

## 功能概览

- 登录会话与 UA/重试封装（`sehuatang_bot/http_client.py`）
- Discuz 客户端骨架（登录/签到/回帖）（`sehuatang_bot/discuz_client.py`）
- OpenAI 协议兼容的 AI 回复生成（`sehuatang_bot/ai.py`）
- Runner 与 CLI 命令（`sehuatang_bot/runner.py`, `sehuatang_bot/cli.py`）
- 可配置主站/镜像站（预留）、账号、AI 网关与模型（`sehuatang_bot/config.py`）
- Docker 镜像封装（`Dockerfile`）

## 安装

1. Python 环境安装依赖

```bash
pip install -r requirements.txt
```

2. 复制配置样例并填写账号信息

```bash
cp config.example.yaml config.yaml
# 或在 Windows PowerShell:
# Copy-Item config.example.yaml config.yaml
```

将 `config.yaml` 中的 `site.username/site.password` 修改为你的账号信息。

> 也支持通过环境变量覆盖，详见下文“环境变量”。

## 配置说明（`config.yaml`）

```yaml
site:
  base_url: "https://www.sehuatang.net"
  mirror_urls: []
  username: "your_username"
  password: "your_password"
  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"

ai:
  api_key: "${AI_API_KEY:-}"
  base_url: "${AI_BASE_URL:-}" # 可填写 OpenAI 兼容网关，如 https://api.openai.com/v1
  model: "gpt-4o-mini"
  temperature: 0.5
  max_tokens: 200

bot:
  dry_run: true                  # 干跑模式：只打印不真正回帖
  reply_enabled: false           # 是否启用自动回帖（后续扩展）
  reply_forums: []               # 允许回帖的版块 ID 白名单（后续扩展）
  signature: "—— 来自自动化小助手"
  daily_checkin_enabled: true
```

- 目前镜像站仅保存在配置中，后续可扩展为“从发布页抓取镜像”。

## 环境变量

- `CONFIG_PATH`：指定配置文件路径，缺省自动在项目根目录查找 `config.yaml`/`sehuatang.yaml`。
- `SITE_BASE_URL`、`SITE_USERNAME`、`SITE_PASSWORD`、`SITE_MIRROR_URLS`、`SITE_UA`
- `AI_API_KEY`、`AI_BASE_URL`、`AI_MODEL`、`AI_TEMPERATURE`、`AI_MAX_TOKENS`
- `BOT_DRY_RUN`、`BOT_REPLY_ENABLED`、`BOT_REPLY_FORUMS`、`BOT_SIGNATURE`、`BOT_DAILY_CHECKIN_ENABLED`

## 命令行使用

所有命令均通过模块方式运行：

```bash
python -m sehuatang_bot --config config.yaml <command>
```

可用命令：

- `login`：测试登录
- `checkin`：登录并执行每日签到（尝试常见签到插件端点）
- `reply --tid <主题ID> --context "上下文"`：生成回复并回帖（干跑模式仅输出将要回复的文本）
- `run-all`：登录 + 签到的一键流程

示例：

```bash
python -m sehuatang_bot --config config.yaml login
python -m sehuatang_bot --config config.yaml checkin
python -m sehuatang_bot --config config.yaml reply --tid 123456 --context "磁力信息/主题摘要..."
python -m sehuatang_bot --config config.yaml run-all
```

## Docker 使用

构建镜像：

```bash
docker build -t sehuatang-bot:latest .
```

以默认 `run-all` 启动（建议使用 `CONFIG_PATH` 或环境变量方式）：

```bash
docker run --rm \
  -e SITE_BASE_URL="https://www.sehuatang.net" \
  -e SITE_USERNAME="your_username" \
  -e SITE_PASSWORD="your_password" \
  -e AI_API_KEY="sk-..." \
  sehuatang-bot:latest
```

挂载自定义配置：

```bash
docker run --rm \
  -v $(pwd)/config.yaml:/app/config.yaml \
  sehuatang-bot:latest
```

执行子命令：

```bash
docker run --rm sehuatang-bot:latest login
```

## 适配与扩展建议

- 某些站点登录流程需要验证码或更复杂的 cookie/跳转，这时需在 `discuz_client.py` 中定制 `login()`。
- 签到插件可能不同，可在 `try_checkin()` 中补充或站点识别后选择对应端点/字段。
- 回帖接口路径、参数、CSRF 校验可能不同，必要时抓包后调整 `reply()` 的表单字段与提交 URL。
- 镜像站自动发现：可新增一个抓取“发布页”的模块，解析镜像列表并做可用性探测，随后对 `HttpClient.base_url` 动态切换。

## 目录结构

- `sehuatang_bot/`：核心代码
  - `config.py`：加载配置（支持 YAML 与环境变量覆盖）
  - `http_client.py`：Requests 会话封装
  - `discuz_client.py`：Discuz 客户端骨架（登录/签到/回帖）
  - `ai.py`：OpenAI 协议兼容的回复生成
  - `runner.py`：业务编排
  - `cli.py`、`__main__.py`：命令行入口
- `config.example.yaml`：配置样例
- `Dockerfile`：容器构建文件
- `requirements.txt`：依赖

## 浏览器模式（Playwright）

为应对部分站点的 JS 校验/重定向/反爬策略，项目支持 Playwright 浏览器自动化模式。开启后，登录、签到、回帖等动作通过浏览器完成，更稳定可靠。

### 本地使用

1. 安装依赖

```bash
pip install -r requirements.txt
python -m playwright install chromium  # 只需安装 Chromium
```

2. 启用浏览器模式

在 `config.yaml` 中添加（或修改）：

```yaml
browser:
  enabled: true
  headless: true        # 本地调试可改为 false
  slow_mo_ms: 0         # 调试时可设为 50-200 观察执行
  timeout_ms: 20000
  engine: chromium      # 建议使用 chromium
```

也可通过环境变量临时覆盖：

```bash
export BROWSER_ENABLED=true
export BROWSER_HEADLESS=false
export BROWSER_SLOW_MO_MS=150
```

3. 运行示例

```bash
python -m sehuatang_bot --config config.yaml login
python -m sehuatang_bot --config config.yaml checkin
python -m sehuatang_bot --config config.yaml run-all
python -m sehuatang_bot --config config.yaml serve  # 启动Web页面
```

### Docker 使用（浏览器模式）

`Dockerfile` 已内置 Playwright 与 Chromium 的安装：

```bash
docker build -t sehuatang-bot:latest .

# 建议增加共享内存，避免 /dev/shm 太小造成浏览器崩溃
docker run --rm \
  --shm-size=1g \
  -e BROWSER_ENABLED=true \
  -e SITE_BASE_URL="https://www.sehuatang.net" \
  -e SITE_USERNAME="your_username" \
  -e SITE_PASSWORD="your_password" \
  sehuatang-bot:latest
```

注意：
- 镜像默认仅安装 Chromium。如需 Firefox/WebKit，请修改 Dockerfile 中的安装命令为 `playwright install --with-deps firefox` 或安装多个内核。
- 如需中文渲染，镜像已安装 `fonts-noto-cjk`。
- 如需代理，设置 `SITE_PROXY`（或 `HTTP_PROXY/HTTPS_PROXY`）。

### 兼容性说明

- 浏览器模式与原有的 `requests` 直连模式可通过 `browser.enabled` 开关切换；逻辑与 CLI/Web 接口不变。
- 浏览器模式下我们在页面上下文内通过 `fetch` 提交表单，以确保 Cookie 自动携带，适配更多站点插件。

## 免责声明

- 请遵守目标站点的服务条款与法律法规，避免频繁请求与刷帖行为。
- AI 生成内容需自行审核，确保不包含违规信息。
