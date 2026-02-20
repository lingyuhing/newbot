from fastapi import FastAPI
from fastapi.websockets import WebSocket,WebSocketDisconnect
from src.agent.agent import MessageChannelMessage,stream
from pydantic import BaseModel
from src.config import HOST,PORT,LOG_LEVEL,LOG_FILE,LOG_DIR,LOG_JSON_FORMAT
from src.logger import setup_logger, log_websocket, log_error, log_request, log_response
import asyncio

class Message(BaseModel):
    context: str
    channel_id: str

app = FastAPI()

# 初始化日志
logger = setup_logger(
    name="newbot.server",
    level=LOG_LEVEL,
    log_file=LOG_FILE,
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)
logger.info("服务器启动中...")

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket,client_id):
        await websocket.accept()
        self.active_connections[client_id] = websocket
    
    def disconnect(self, client_id):
        self.active_connections.pop(client_id, None) 
    
    async def broadcast(self, message):
        for connection in self.active_connections.values():
            await connection.send_text(message)
    
    async def send_to(self, client_id, message):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)

manager = ConnectionManager()
@app.websocket("/ws/{client_id}")
async def chat(websocket: WebSocket, client_id: str):
    if client_id not in manager.active_connections.keys():
        await manager.connect(websocket,client_id)
        log_websocket(logger, "CONNECT", client_id, "新连接已建立")
        try:
            while True:
                data = await websocket.receive_text()
                log_request(logger, client_id, data)

                token_count = 0
                def send_token():
                    nonlocal token_count
                    for token in stream(MessageChannelMessage(message_channel_id=client_id, context=data)):
                        token_count += 1
                        asyncio.run(websocket.send_text(token))
                await asyncio.to_thread(send_token)
                log_response(logger, client_id, token_count)
        except WebSocketDisconnect:
            log_websocket(logger, "DISCONNECT", client_id, "客户端主动断开")
            manager.disconnect(client_id)
        except Exception as e:
            log_error(logger, e, {"client_id": client_id})
            await websocket.send_text(f"服务器错误: {e}")
            manager.disconnect(client_id)
            log_websocket(logger, "ERROR_DISCONNECT", client_id, str(e))
    else:
        log_websocket(logger, "REJECT", client_id, "重复连接被拒绝")
        await websocket.close(code=4000,reason="已存在连接")

@app.get("/get_channel_id")
def get_channel_id():
    clients = list(manager.active_connections.keys())
    logger.debug(f"查询活跃连接: {len(clients)} 个客户端")
    return clients

@app.post("/send_message")
async def send_message(message: Message):
    if message.channel_id not in manager.active_connections.keys():
        logger.warning(f"发送失败: 频道不存在 channel_id={message.channel_id}")
        return "频道不存在"
    await manager.send_to(message.channel_id, message.context)
    logger.info(f"消息已发送: channel_id={message.channel_id}")
    return "成功"

if __name__ == "__main__":
    import uvicorn
    logger.info(f"服务器监听 {HOST}:{PORT}")
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)