"""
记忆系统模块

提供基于 Mem0 的长期记忆存储和检索功能
"""

from mem0 import MemoryClient
from src.config import USER_ID, MEM0_API_KEY, LOG_LEVEL, LOG_DIR, LOG_JSON_FORMAT
from langchain.tools import tool
from typing import List, Dict, Any
from src.logger import setup_logger

# 初始化日志
logger = setup_logger(
    name="newbot.memory",
    level=LOG_LEVEL,
    log_file="memory.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)

client = MemoryClient(api_key=MEM0_API_KEY)
user_id = USER_ID

logger.info(f"Mem0 客户端初始化完成: user_id={user_id}")

def add_memory(messages: list) -> dict:
    """
    添加记忆到存储中
    
    Args:
        messages: 要存储的消息列表
    
    Returns:
        Mem0 API 返回的结果
    """
    logger.debug(f"添加记忆: {len(messages)} 条消息")
    try:
        result = client.add(messages, user_id=user_id)
        logger.info(f"记忆添加成功")
        return result
    except Exception as e:
        logger.error(f"添加记忆失败: {e}", exc_info=True)
        raise


def search_memory(text: str) -> List[Dict[str, Any]]:
    """
    搜索记忆
    
    Args:
        text: 搜索关键词
    
    Returns:
        匹配的记忆列表
    """
    logger.debug(f"搜索记忆: query={text[:50]}...")
    try:
        results = client.search(text, user_id=user_id)["results"]
        logger.info(f"搜索完成: 找到 {len(results)} 条记忆")
        return results
    except Exception as e:
        logger.error(f"搜索记忆失败: {e}", exc_info=True)
        raise


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
    return search_memory(query)