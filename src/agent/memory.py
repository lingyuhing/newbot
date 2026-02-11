from mem0 import MemoryClient
from ..config import USER_ID

client = MemoryClient(api_key="m0-JmNINAM9EjWON6hytbxEGquIiZl19wDYL5EMgQx8")
user_id = USER_ID

def add_memory(messages:list):
    client.add(messages,user_id=user_id)

def search_memory(text:str):
    return client.search(text,user_id=user_id)["results"]