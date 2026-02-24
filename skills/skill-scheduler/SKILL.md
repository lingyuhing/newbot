---
name: scheduler
description: 此技能用于管理定时任务。支持添加、列出、删除、启用/禁用定时任务。任务类型包括间隔执行、指定时间执行、每日执行和cron表达式。当用户想要设置提醒、定时执行任务或管理计划任务时使用此技能。
---

# 定时任务技能

此技能为系统提供定时任务管理能力。通过 WebSocket 客户端与主服务器通信，实现任务的定时触发和执行。

## 使用场景

在以下情况下使用此技能：
- 用户想要设置定时提醒
- 用户想要定时执行某个任务
- 用户想要查看、管理已有的定时任务
- 用户想要启用或禁用某个定时任务

## 可用脚本

### 1. 添加定时任务

**脚本：** `scripts/add_task.py`

添加一个新的定时任务。

```bash
python scripts/add_task.py -n "<任务名称>" -p "<任务提示词>" -t <触发类型> [触发参数]
```

**参数说明：**
- `-n, --name`: 任务名称（必填）
- `-p, --prompt`: 任务执行时发送给 agent 的提示词（必填）
- `-t, --trigger`: 触发类型，可选值：`interval`、`date`、`daily`、`cron`（必填）

**触发类型参数：**

| 触发类型 | 必需参数 | 示例 |
|---------|---------|------|
| `interval` | `--seconds`/`--minutes`/`--hours` | `--minutes 30` 每30分钟执行 |
| `date` | `--run-date "YYYY-MM-DD HH:MM:SS"` | `--run-date "2024-12-25 08:00:00"` 指定时间执行一次 |
| `daily` | `--time "HH:MM:SS"` | `--time "09:00:00"` 每天9点执行 |
| `cron` | `--cron-expression "cron表达式"` | `--cron-expression "0 9 * * 1-5"` 工作日9点执行 |

### 2. 列出所有任务

**脚本：** `scripts/list_tasks.py`

列出所有已创建的定时任务及其状态。

```bash
python scripts/list_tasks.py [--all]
```

**参数说明：**
- `--all`: 显示所有任务（包括已禁用的），默认只显示启用的任务

### 3. 删除任务

**脚本：** `scripts/remove_task.py`

删除指定的定时任务。

```bash
python scripts/remove_task.py -i <任务ID>
```

**参数说明：**
- `-i, --id`: 要删除的任务ID（必填）

### 4. 启用/禁用任务

**脚本：** `scripts/toggle_task.py`

启用或禁用指定的定时任务。

```bash
python scripts/toggle_task.py -i <任务ID> [-e|--disable]
```

**参数说明：**
- `-i, --id`: 任务ID（必填）
- `-e, --enable`: 启用任务
- `-d, --disable`: 禁用任务

### 5. 启动调度守护进程

**脚本：** `scripts/start_daemon.py`

启动调度守护进程（如果未运行）。守护进程负责执行所有定时任务，需要持续运行。

```bash
python scripts/start_daemon.py
```

**参数说明：**
- `--status`: 检查守护进程运行状态

也可以直接运行守护进程（前台模式）：
```bash
python scripts/scheduler_daemon.py
```

## 任务触发类型详解

### interval（间隔执行）
按固定时间间隔重复执行任务。

```bash
# 每30分钟执行一次
python scripts/add_task.py -n "定时提醒" -p "提醒我休息一下" -t interval --minutes 30

# 每小时执行一次
python scripts/add_task.py -n "整点报时" -p "现在是什么时间" -t interval --hours 1
```

### date（指定时间执行一次）
在指定的日期时间执行一次任务。

```bash
# 在指定时间执行
python scripts/add_task.py -n "会议提醒" -p "会议将在10分钟后开始" -t date --run-date "2024-12-20 14:00:00"
```

### daily（每日执行）
每天在指定时间执行任务。

```bash
# 每天早上9点执行
python scripts/add_task.py -n "早间问候" -p "早上好，今天有什么安排？" -t daily --time "09:00:00"
```

### cron（Cron表达式）
使用标准 cron 表达式定义复杂的执行计划。

```bash
# 每个工作日（周一到周五）早上9点执行
python scripts/add_task.py -n "工作日提醒" -p "开始工作" -t cron --cron-expression "0 9 * * 1-5"

# 每月1号和15号的中午12点执行
python scripts/add_task.py -n "月中提醒" -p "今天是月中" -t cron --cron-expression "0 12 1,15 * *"
```

**Cron 表达式格式：** `秒 分 时 日 月 周`
- `*` 表示所有值
- `1-5` 表示范围
- `1,15` 表示列表
- `*/5` 表示间隔（每5单位）

## 工作流程

1. **首次使用：** 启动调度守护进程 `python scripts/scheduler_daemon.py`
2. **添加任务：** 使用 `add_task.py` 添加定时任务
3. **查看任务：** 使用 `list_tasks.py` 查看所有任务
4. **管理任务：** 使用 `toggle_task.py` 或 `remove_task.py` 管理任务

## 数据存储

- `data/tasks.json`: 存储所有定时任务配置
- `data/task_logs.json`: 存储任务执行日志

## 配置

此技能使用 `src/config.py` 中的以下配置：
- `HOST`: WebSocket 服务器主机地址（默认：127.0.0.1）
- `PORT`: WebSocket 服务器端口（默认：8000）
