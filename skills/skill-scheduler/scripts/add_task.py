#!/usr/bin/env python3
"""
添加定时任务
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime

# 添加项目根目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, PROJECT_ROOT)

TASKS_FILE = os.path.join(SKILL_DIR, "data", "tasks.json")


def load_tasks() -> list:
    """加载任务配置"""
    if not os.path.exists(TASKS_FILE):
        return []
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_tasks(tasks: list):
    """保存任务配置"""
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def parse_interval_args(args) -> dict:
    """解析间隔触发参数"""
    config = {}
    if args.seconds:
        config["seconds"] = args.seconds
    if args.minutes:
        config["minutes"] = args.minutes
    if args.hours:
        config["hours"] = args.hours
    
    if not config:
        print("错误: interval 类型需要指定 --seconds, --minutes 或 --hours")
        sys.exit(1)
    return config


def parse_date_args(args) -> dict:
    """解析日期触发参数"""
    if not args.run_date:
        print("错误: date 类型需要指定 --run-date")
        sys.exit(1)
    
    try:
        datetime.fromisoformat(args.run_date)
    except ValueError:
        print("错误: 日期格式无效，应为 'YYYY-MM-DD HH:MM:SS'")
        sys.exit(1)
    
    return {"run_date": args.run_date}


def parse_daily_args(args) -> dict:
    """解析每日触发参数"""
    time_str = args.time or "00:00:00"
    try:
        parts = time_str.split(":")
        if len(parts) != 3:
            raise ValueError()
        hour, minute, second = int(parts[0]), int(parts[1]), int(parts[2])
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
            raise ValueError()
    except ValueError:
        print("错误: 时间格式无效，应为 'HH:MM:SS'")
        sys.exit(1)
    
    return {"time": time_str}


def parse_cron_args(args) -> dict:
    """解析 cron 触发参数"""
    if not args.cron_expression:
        print("错误: cron 类型需要指定 --cron-expression")
        sys.exit(1)
    
    return {"cron_expression": args.cron_expression}


def main():
    parser = argparse.ArgumentParser(description="添加定时任务")
    parser.add_argument("-n", "--name", required=True, help="任务名称")
    parser.add_argument("-p", "--prompt", required=True, help="任务执行时发送给 agent 的提示词")
    parser.add_argument("-t", "--trigger", required=True, 
                        choices=["interval", "date", "daily", "cron"],
                        help="触发类型")
    
    # interval 参数
    parser.add_argument("--seconds", type=int, help="间隔秒数")
    parser.add_argument("--minutes", type=int, help="间隔分钟数")
    parser.add_argument("--hours", type=int, help="间隔小时数")
    
    # date 参数
    parser.add_argument("--run-date", help="执行日期时间 (YYYY-MM-DD HH:MM:SS)")
    
    # daily 参数
    parser.add_argument("--time", help="每日执行时间 (HH:MM:SS)")
    
    # cron 参数
    parser.add_argument("--cron-expression", help="Cron 表达式")
    
    args = parser.parse_args()
    
    # 解析触发配置
    trigger_parsers = {
        "interval": parse_interval_args,
        "date": parse_date_args,
        "daily": parse_daily_args,
        "cron": parse_cron_args,
    }
    
    trigger_config = trigger_parsers[args.trigger](args)
    
    # 创建任务
    task = {
        "id": str(uuid.uuid4()),
        "name": args.name,
        "prompt": args.prompt,
        "trigger_type": args.trigger,
        "trigger_config": trigger_config,
        "enabled": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    # 保存任务
    tasks = load_tasks()
    tasks.append(task)
    save_tasks(tasks)
    
    print(f"成功添加任务:")
    print(f"  ID: {task['id']}")
    print(f"  名称: {task['name']}")
    print(f"  提示词: {task['prompt']}")
    print(f"  触发类型: {task['trigger_type']}")
    print(f"  触发配置: {json.dumps(trigger_config, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
