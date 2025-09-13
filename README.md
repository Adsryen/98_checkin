# 98_checkin
98自动化签到

## Quick Start

### PowerShell Script (Recommended)
```powershell
# Default start
.\start.ps1

# Public access
.\start.ps1 -Public

# Custom port
.\start.ps1 -Port 8080

# Show help
.\start.ps1 -Help
```

### Batch File (Compatibility)
```cmd
start.bat
```

### Manual Start
```bash
python -m sehuatang_bot serve --host 127.0.0.1 --port 9898
```

## Web 界面

- 后台管理：支持管理员密码（`admin_password`）。
- 任务页：`/tasks` 显示登录与每日签到状态。

### 多账号
- 配置 `accounts` 列表支持多个账号，可用用户名/密码或仅Cookie。
- Web 后台：`/accounts` 添加、删除账号；进入账号详情可手动执行签到并查看历史与日志。

### 数据存储（SQLite）
- 默认使用本地 SQLite 数据库 `./data.sqlite3` 存储账号、状态、历史与日志。
- 可在 `config.yaml` 设置：
```yaml
db_path: "./data.sqlite3"
```
- 首次启动若数据库为空，会自动从配置文件中的 `accounts` 导入至数据库。