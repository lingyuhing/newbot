#!/usr/bin/env python3
"""
WebSocket CLI 客户端
连接到 newbot 服务器并进行交互式对话
"""

import asyncio
import sys
from typing import Optional
import websockets


class CLIClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8000, client_id: Optional[str] = None):
        self.host = host
        self.port = port
        self.client_id = client_id or "cli-client"
        self.ws_url = f"ws://{host}:{port}/ws/{self.client_id}"
        self.websocket = None
        self.running = False

    async def connect(self):
        """连接到 WebSocket 服务器"""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            print(f"✓ 已连接到 {self.ws_url}")
            print(f"  客户端 ID: {self.client_id}")
            print("-" * 50)
            return True
        except Exception as e:
            print(f"✗ 连接失败: {e}")
            return False

    async def receive_messages(self):
        """接收并显示来自服务器的消息"""
        try:
            while self.running:
                message = await self.websocket.recv()
                # 流式输出，不换行
                print(message, end="", flush=True)
        except websockets.ConnectionClosed:
            if self.running:
                print("\n连接已断开")
                self.running = False
        except Exception as e:
            if self.running:
                print(f"\n接收错误: {e}")
                self.running = False

    async def send_message(self, message: str):
        """发送消息到服务器"""
        if self.websocket:
            await self.websocket.send(message)

    async def run(self):
        """运行客户端主循环"""
        if not await self.connect():
            return

        self.running = True
        
        # 启动接收任务
        receive_task = asyncio.create_task(self.receive_messages())
        
        print("输入消息后按回车发送，输入 /quit 或 /exit 退出")
        print("-" * 50)

        try:
            loop = asyncio.get_event_loop()
            
            while self.running:
                # 使用线程池读取用户输入，避免阻塞事件循环
                try:
                    user_input = await loop.run_in_executor(None, input)
                except EOFError:
                    break
                
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ("/quit", "/exit"):
                    print("正在断开连接...")
                    break
                
                if user_input.startswith("/"):
                    # 处理命令
                    if user_input == "/help":
                        print("命令列表:")
                        print("  /help  - 显示帮助")
                        print("  /quit  - 退出客户端")
                        print("  /exit  - 退出客户端")
                        continue
                    else:
                        print(f"未知命令: {user_input}")
                        continue
                
                # 发送消息
                await self.send_message(user_input)
                
                # 等待接收完成（简单实现：等待一小段时间确保响应开始）
                await asyncio.sleep(0.1)
                
                # 等待响应完成（通过检测 websocket 队列为空）
                await asyncio.sleep(0.2)
                print()  # 响应结束后换行
        
        except KeyboardInterrupt:
            print("\n正在断开连接...")
        finally:
            self.running = False
            receive_task.cancel()
            try:
                await asyncio.wait_for(self.websocket.close(), timeout=2)
            except:
                pass
            print("已断开连接")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="WebSocket CLI 客户端")
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址 (默认: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="服务器端口 (默认: 8000)")
    parser.add_argument("--client-id", default=None, help="客户端 ID (默认: cli-client)")
    
    args = parser.parse_args()
    
    client = CLIClient(
        host=args.host,
        port=args.port,
        client_id=args.client_id
    )
    
    asyncio.run(client.run())


if __name__ == "__main__":
    main()