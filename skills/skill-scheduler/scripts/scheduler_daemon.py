#!/usr/bin/env python3
"""
调度守护进程 - 作为 WebSocket 客户端连接到主服务器
负责管理和执行所有定时任务
"""

import asyncio
import json
import os
import sys
import signal
import uuid
from datetime import datetime
from typing import Optional

try:
    import websockets
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.cron import CronTrigger
except ImportError as e:
    print(f"缺少依赖: {e}")
    print("请运行: pip install websockets apscheduler")
    sys.exit(1)

# 添加项目根目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, PROJECT_ROOT)

from src.config import HOST, PORT

# 常量
SCHEDULER_CLIENT_ID = "scheduler_daemon"
TASKS_FILE = os.path.join(SKILL_DIR, "data", "tasks.json")
LOGS_FILE = os.path.join(SKILL_DIR, "data", "task_logs.json")

class SchedulerDaemon:
    """调度守护进程 - WebSocket 客户端"""
    
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.scheduler = AsyncIOScheduler()
        self.running = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        
    def load_tasks(self) -> list:
        """加载任务配置"""
        if not os.path.exists(TASKS_FILE):
            return []
        try:
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[错误] 加载任务失败: {e}")
            return []
    
    def save_tasks(self, tasks: list):
        """保存任务配置"""
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    def log_execution(self, task_id: str, task_name: str, prompt: str, 
                      status: str, response: str = ""):
        """记录任务执行日志"""
        os.makedirs(os.path.dirname(LOGS_FILE), exist_ok=True)
        
        logs = []
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except (json.JSONDecodeError, IOError):
                logs = []
        
        logs.append({
            "id": str(uuid.uuid4()),
            "task_id": task_id,
            "task_name": task_name,
            "prompt": prompt,
            "status": status,
            "response": response[:500] if response else "",  # 限制响应长度
            "executed_at": datetime.now().isoformat()
        })
        
        # 只保留最近1000条日志
        logs = logs[-1000:]
        
        with open(LOGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    
    async def connect(self) -> bool:
        """连接到 WebSocket 服务器"""
        try:
            ws_url = f"ws://{HOST}:{PORT}/ws/{SCHEDULER_CLIENT_ID}"
            print(f"[信息] 正在连接: {ws_url}")
            self.ws = await websockets.connect(ws_url)
            print(f"[信息] 已连接到服务器")
            self.reconnect_delay = 5  # 重置重连延迟
            return True
        except Exception as e:
            print(f"[错误] 连接失败: {e}")
            return False
    
    async def execute_task(self, task: dict):
        """执行单个任务"""
        task_id = task["id"]
        task_name = task["name"]
        prompt = task["prompt"]
        
        print(f"\n[执行] 任务: {task_name} (ID: {task_id})")
        print(f"[执行] 提示词: {prompt}")
        
        if not self.ws or self.ws.closed:
            print("[警告] WebSocket 未连接，尝试重连...")
            if not await self.connect():
                self.log_execution(task_id, task_name, prompt, "failed", "WebSocket连接失败")
                return
        
        try:
            # 发送消息到 agent
            message = {
                "multimodal": [{"type": "text", "text": prompt}]
            }
            await self.ws.send(json.dumps(message))
            
            # 收集响应
            response_parts = []
            try:
                async for message in self.ws:
                    response_parts.append(message)
                    # 检查是否是完整的响应（可根据实际协议调整）
                    # 这里假设每个 token 都是完整消息
                    if len(response_parts) > 1000:  # 防止无限循环
                        break
                        
            except websockets.exceptions.ConnectionClosed:
                pass
            
            full_response = "".join(response_parts)
            print(f"[完成] 任务 {task_name} 执行完成")
            
            self.log_execution(task_id, task_name, prompt, "success", full_response)
            
        except Exception as e:
            error_msg = str(e)
            print(f"[错误] 任务执行失败: {error_msg}")
            self.log_execution(task_id, task_name, prompt, "failed", error_msg)
    
    def add_job(self, task: dict):
        """添加任务到调度器"""
        task_id = task["id"]
        trigger_type = task["trigger_type"]
        trigger_config = task.get("trigger_config", {})
        
        try:
            if trigger_type == "interval":
                trigger = IntervalTrigger(
                    seconds=trigger_config.get("seconds", 0),
                    minutes=trigger_config.get("minutes", 0),
                    hours=trigger_config.get("hours", 0)
                )
            elif trigger_type == "date":
                run_date = trigger_config.get("run_date")
                if run_date:
                    trigger = DateTrigger(run_date=datetime.fromisoformat(run_date))
                else:
                    print(f"[警告] 任务 {task_id} 缺少 run_date")
                    return
            elif trigger_type == "daily":
                time_str = trigger_config.get("time", "00:00:00")
                hour, minute, second = map(int, time_str.split(":"))
                trigger = CronTrigger(hour=hour, minute=minute, second=second)
            elif trigger_type == "cron":
                cron_expr = trigger_config.get("cron_expression", "* * * * *")
                trigger = CronTrigger.from_crontab(cron_expr)
            else:
                print(f"[警告] 未知的触发类型: {trigger_type}")
                return
            
            self.scheduler.add_job(
                self.execute_task,
                trigger=trigger,
                args=[task],
                id=task_id,
                name=task["name"],
                replace_existing=True
            )
            print(f"[调度] 已添加任务: {task['name']} (ID: {task_id})")
            
        except Exception as e:
            print(f"[错误] 添加任务失败: {e}")
    
    def load_jobs(self):
        """加载所有启用的任务到调度器"""
        tasks = self.load_tasks()
        for task in tasks:
            if task.get("enabled", True):
                self.add_job(task)
        print(f"[信息] 已加载 {len(self.scheduler.get_jobs())} 个任务")
    
    async def watch_tasks_file(self):
        """监控任务文件变化"""
        last_mtime = 0
        while self.running:
            try:
                if os.path.exists(TASKS_FILE):
                    current_mtime = os.path.getmtime(TASKS_FILE)
                    if current_mtime > last_mtime:
                        last_mtime = current_mtime
                        # 重新加载任务
                        print("[信息] 检测到任务变化，重新加载...")
                        self.scheduler.remove_all_jobs()
                        self.load_jobs()
            except Exception as e:
                print(f"[错误] 监控任务文件失败: {e}")
            
            await asyncio.sleep(5)
    
    async def run(self):
        """运行守护进程"""
        self.running = True
        
        # 设置信号处理
        def signal_handler(sig, frame):
            print("\n[信息] 正在关闭守护进程...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 加载任务
        self.load_jobs()
        
        # 启动调度器
        self.scheduler.start()
        print("[信息] 调度器已启动")
        
        # 连接 WebSocket
        await self.connect()
        
        # 启动文件监控
        watch_task = asyncio.create_task(self.watch_tasks_file())
        
        # 保持运行
        while self.running:
            try:
                # 检查 WebSocket 连接
                if not self.ws or self.ws.closed:
                    print(f"[警告] 连接断开，{self.reconnect_delay}秒后重连...")
                    await asyncio.sleep(self.reconnect_delay)
                    await self.connect()
                    # 指数退避
                    self.reconnect_delay = min(
                        self.reconnect_delay * 2, 
                        self.max_reconnect_delay
                    )
                else:
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"[错误] 运行异常: {e}")
                await asyncio.sleep(5)
        
        # 清理
        watch_task.cancel()
        self.scheduler.shutdown()
        if self.ws:
            await self.ws.close()
        print("[信息] 守护进程已停止")


async def main():
    daemon = SchedulerDaemon()
    await daemon.run()


if __name__ == "__main__":
    print("=" * 50)
    print("  调度守护进程 - 定时任务执行器")
    print("=" * 50)
    asyncio.run(main())
