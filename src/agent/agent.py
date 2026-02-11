from langchain.chat_models import init_chat_model
from src.config import LLM_BASE_URL, LLM_KEY, LLM_MODEL,ROOT_DIR,SKILL_DIR,SHORT_TERM_MEMORY_DIR
from src.agent.langchain_fix.graph import create_deep_agent
from deepagents.backends import FilesystemBackend
from dataclasses import dataclass
import pickle
import json

@dataclass
class MessageChannelMessage:
    message_channel_id: str
    context:list[dict[str, str]]

model = init_chat_model(
    model=LLM_MODEL,
    model_provider="openai",
    base_url=LLM_BASE_URL,
    api_key=LLM_KEY,
)

agent = create_deep_agent(
    model=model,
    backend=FilesystemBackend(root_dir=ROOT_DIR),
    skills=SKILL_DIR
)

def invoke(messages: MessageChannelMessage):
    try:
        history_messages # type: ignore
    except:
        try:
            with open(SHORT_TERM_MEMORY_DIR, "rb") as f:
                history_messages = pickle.load(f)
        except:
            history_messages = []
    
    open_messages={
    "消息渠道ID":messages.message_channel_id,
    "消息内容":messages.context
    }
    open_messages_json = json.dumps(open_messages, ensure_ascii=False)
    result = agent.invoke(input={"messages":history_messages+[{"role":"user","content":open_messages_json}]})
    history_messages = result
    with open(SHORT_TERM_MEMORY_DIR, "wb") as f:
        pickle.dump(history_messages, f)
    return result["messages"][-1].content