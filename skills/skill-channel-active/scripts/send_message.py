import httpx
import asyncio
import argparse
from src.config import HOST, PORT


async def send_to_client(
    client_id: str, 
    message: str, 
    base_url: str = f"http://{HOST}:{PORT}"
) -> dict:
    """发送消息给特定客户端
    
    Args:
        client_id: 目标客户端ID
        message: 要发送的消息内容
        base_url: 服务器基础URL
        
    Returns:
        响应结果
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{base_url}/send_message",
                json={"context": message, "channel_id": client_id}
            )
            response.raise_for_status()
            return {"success": True, "result": response.text}
        except httpx.RequestError as e:
            return {"success": False, "error": f"请求错误: {e}"}
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"HTTP错误: {e}"}


async def main():
    parser = argparse.ArgumentParser(description="发送消息给特定连接客户端")
    parser.add_argument("-c", "--client", required=True, help="目标客户端ID")
    parser.add_argument("-m", "--message", required=True, help="要发送的消息内容")
    args = parser.parse_args()
    
    result = await send_to_client(args.client, args.message)
    
    if result["success"]:
        print(f"✓ 发送成功: {result['result']}")
    else:
        print(f"✗ 发送失败: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
