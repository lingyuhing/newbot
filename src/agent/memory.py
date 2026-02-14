from mem0 import MemoryClient
from src.config import USER_ID
from langchain.tools import tool
from typing import List, Dict, Any

client = MemoryClient(api_key="m0-JmNINAM9EjWON6hytbxEGquIiZl19wDYL5EMgQx8")
user_id = USER_ID

def add_memory(messages:list):
    client.add(messages,user_id=user_id)

def search_memory(text:str):
    return client.search(text,user_id=user_id)["results"]

@tool
def search_memory_tool(query: str) -> List[Dict[str, Any]]:
    """
    搜索历史记忆/信息。

    当需要了解用户的偏好、历史对话内容、个人信息或过去的交互记录时使用此工具。

    Args:
        query: 搜索关键词或问题描述

    Returns:
        包含相关记忆内容的列表，每个记忆包含记忆内容和元数据
    """
    return client.search(query, user_id=user_id)["results"]