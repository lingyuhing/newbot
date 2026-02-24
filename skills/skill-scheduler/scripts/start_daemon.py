#!/usr/bin/env python3
"""
启动调度守护进程（如果未运行）
"""

import subprocess
import os
import sys
import socket

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DAEMON_SCRIPT = os.path.join(SCRIPT_DIR, "scheduler_daemon.py")

def is_daemon_running() -> bool:
    """检查守护进程是否在运行"""
    try:
        # 尝试连接到 WebSocket 端点检查 scheduler_daemon 是否存在
        import urllib.request
        url = "http://127.0.0.1:8000/get_channel_id"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                import json
                clients = json.loads(response.read().decode())
                return "scheduler_daemon" in clients
        except:
            return False
    except:
        return False


def start_daemon() -> bool:
    """启动守护进程"""
    if is_daemon_running():
        print("守护进程已在运行")
        return True
    
    try:
        # 使用 nohup 在后台启动
        subprocess.Popen(
            [sys.executable, DAEMON_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        print("守护进程已启动")
        return True
    except Exception as e:
        print(f"启动失败: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="启动调度守护进程")
    parser.add_argument("--status", action="store_true", help="检查状态")
    args = parser.parse_args()
    
    if args.status:
        if is_daemon_running():
            print("状态: 运行中")
        else:
            print("状态: 未运行")
    else:
        start_daemon()


if __name__ == "__main__":
    main()
