#!/usr/bin/env python3
"""
删除定时任务
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


def save_tasks(tasks: list):
    """保存任务配置"""
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="删除定时任务")
    parser.add_argument("-i", "--id", required=True, help="要删除的任务ID")
    args = parser.parse_args()
    
    tasks = load_tasks()
    
    # 查找任务
    task_to_remove = None
    for i, task in enumerate(tasks):
        if task["id"] == args.id:
            task_to_remove = tasks.pop(i)
            break
    
    if not task_to_remove:
        print(f"错误: 找不到 ID 为 {args.id} 的任务")
        sys.exit(1)
    
    save_tasks(tasks)
    
    print(f"成功删除任务:")
    print(f"  ID: {task_to_remove['id']}")
    print(f"  名称: {task_to_remove['name']}")


if __name__ == "__main__":
    main()
