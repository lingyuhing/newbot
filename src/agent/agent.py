from langchain.chat_models import init_chat_model
from src.config import LLM_BASE_URL, LLM_KEY, LLM_MODEL, ROOT_DIR, SKILL_DIR,USER_ID,VIRTUAL_MODE
from src.agent.langchain_fix.graph import create_deep_agent
from deepagents.backends import LocalShellBackend
from dataclasses import dataclass
from src.agent.memory import search_memory_tool
import json
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

class MessageChannelMessage(BaseModel):
    message_channel_id: str
    context: str

model = init_chat_model(
    model=LLM_MODEL,
    model_provider="openai",
    base_url=LLM_BASE_URL,
    api_key=LLM_KEY,
)

# 正确方式：直接构造 SqliteSaver
conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
checkpointer = SqliteSaver(conn)

agent = create_deep_agent(
    model=model,
    backend=LocalShellBackend(root_dir=ROOT_DIR, virtual_mode=VIRTUAL_MODE),
    skills=SKILL_DIR,
    tools=[search_memory_tool],
    checkpointer=checkpointer
)

async def stream(messages: MessageChannelMessage):
    # 添加 thread_id 配置以保持会话记忆
    config = {
        "configurable": {
            "thread_id": USER_ID
        }
    }
    
    messages_dict = {
        "消息渠道ID": messages.message_channel_id,
        "发送内容": messages.context
    }
    messages_json = json.dumps(messages_dict, ensure_ascii=False)
    
    result = agent.astream(
        {"messages": [{"role": "user", "content": messages_json}]},
        config=config,  # 传入配置以启用短期记忆
        stream_mode="messages"
    )
    
    async for token, message in result:
        yield token.content