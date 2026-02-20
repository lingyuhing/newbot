import httpx
import asyncio
from src.config import HOST, PORT

async def get_connected_clients(base_url: str = f"http://{HOST}:{PORT}"):
    """获取所有连接的客户端ID"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{base_url}/get_channel_id")
            response.raise_for_status()
            clients = response.json()
            return clients
        except httpx.RequestError as e:
            print(f"请求错误: {e}")
            return []
        except httpx.HTTPStatusError as e:
            print(f"HTTP错误: {e}")
            return []

async def main():
    clients = await get_connected_clients()
    if clients:
        print(f"当前连接的客户端 ({len(clients)} 个):")
        for client_id in clients:
            print(f"  - {client_id}")
    else:
        print("没有连接的客户端")

if __name__ == "__main__":
    asyncio.run(main())
