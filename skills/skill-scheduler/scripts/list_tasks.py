#!/usr/bin/env python3
"""
列出所有定时任务
"""

import argparse
import json
import os
import sys

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


def format_trigger_info(task: dict) -> str:
    """格式化触发信息"""
    trigger_type = task["trigger_type"]
    config = task.get("trigger_config", {})
    
    if trigger_type == "interval":
        parts = []
        if config.get("hours"):
            parts.append(f"{config['hours']}小时")
        if config.get("minutes"):
            parts.append(f"{config['minutes']}分钟")
        if config.get("seconds"):
            parts.append(f"{config['seconds']}秒")
        return f"间隔: {' '.join(parts)}"
    
    elif trigger_type == "date":
        return f"定时: {config.get('run_date', '未设置')}"
    
    elif trigger_type == "daily":
        return f"每日: {config.get('time', '00:00:00')}"
    
    elif trigger_type == "cron":
        return f"Cron: {config.get('cron_expression', '*')}"
    
    return "未知"


def main():
    parser = argparse.ArgumentParser(description="列出所有定时任务")
    parser.add_argument("--all", action="store_true", help="显示所有任务（包括已禁用的）")
    args = parser.parse_args()
    
    tasks = load_tasks()
    
    if not tasks:
        print("当前没有任务")
        return
    
    # 过滤
    if not args.all:
        tasks = [t for t in tasks if t.get("enabled", True)]
    
    if not tasks:
        print("当前没有启用的任务（使用 --all 查看所有任务）")
        return
    
    print(f"\n{'=' * 70}")
    print(f"  {'ID':<36} {'名称':<15} {'状态':<6} {'触发信息'}")
    print(f"{'=' * 70}")
    
    for task in tasks:
        task_id = task["id"]
        name = task["name"][:14] + "…" if len(task["name"]) > 15 else task["name"]
        status = "启用" if task.get("enabled", True) else "禁用"
        trigger_info = format_trigger_info(task)
        
        print(f"  {task_id:<36} {name:<15} {status:<6} {trigger_info}")
        print(f"    提示词: {task['prompt'][:50]}{'...' if len(task['prompt']) > 50 else ''}")
    
    print(f"{'=' * 70}")
    print(f"共 {len(tasks)} 个任务")


if __name__ == "__main__":
    main()
