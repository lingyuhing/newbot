#!/usr/bin/env python3
"""
启用/禁用定时任务
"""

import argparse
import json
import os
import sys
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


def main():
    parser = argparse.ArgumentParser(description="启用/禁用定时任务")
    parser.add_argument("-i", "--id", required=True, help="任务ID")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-e", "--enable", action="store_true", help="启用任务")
    group.add_argument("-d", "--disable", action="store_true", help="禁用任务")
    args = parser.parse_args()
    
    tasks = load_tasks()
    
    # 查找任务
    task = None
    for t in tasks:
        if t["id"] == args.id:
            task = t
            break
    
    if not task:
        print(f"错误: 找不到 ID 为 {args.id} 的任务")
        sys.exit(1)
    
    # 更新状态
    new_status = args.enable
    task["enabled"] = new_status
    task["updated_at"] = datetime.now().isoformat()
    
    save_tasks(tasks)
    
    status_text = "启用" if new_status else "禁用"
    print(f"成功{status_text}任务:")
    print(f"  ID: {task['id']}")
    print(f"  名称: {task['name']}")
    print(f"  状态: {status_text}")


if __name__ == "__main__":
    main()
