from langchain.chat_models import init_chat_model
from src.config import LLM_BASE_URL, LLM_KEY, LLM_MODEL, ROOT_DIR, SKILL_DIR,USER_ID,VIRTUAL_MODE,LOG_LEVEL,LOG_DIR,LOG_JSON_FORMAT
from src.agent.langchain_fix.graph import create_deep_agent
from deepagents.backends import LocalShellBackend
from src.agent.memory import search_memory_tool
import json
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel
from src.logger import setup_logger, get_logger

class MessageChannelMessage(BaseModel):
    message_channel_id: str
    multimodal:list[dict] = []
    audio:str | None = None

# 初始化日志
logger = setup_logger(
    name="newbot.agent",
    level=LOG_LEVEL,
    log_file="agent.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)

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

logger.info(f"Agent 初始化完成: model={LLM_MODEL}, root_dir={ROOT_DIR}")

def stream(messages: MessageChannelMessage):
    """
    流式处理消息
    
    Args:
        messages: 包含消息渠道ID和内容的消息对象
    
    Yields:
        处理后的 token 内容
    """
    logger.debug(f"开始处理消息: channel_id={messages.message_channel_id}")
    
    # 添加 thread_id 配置以保持会话记忆
    config = {
        "configurable": {
            "thread_id": USER_ID
        }
    }
    
    try:
        result = agent.stream(
            {"messages": [{"role": "user", "content": [{"type":"text","text":f"消息渠道ID: {messages.message_channel_id}"}]+messages.multimodal}]},
            config=config,
            stream_mode="messages"
        )
        
        for token, message in result:
            yield token.content
            
    except Exception as e:
        logger.error(f"Agent 处理错误: {e}", exc_info=True)
        raise