if __name__ == '__main__':
    from src.agent.agent import invoke,MessageChannelMessage
    message = MessageChannelMessage(message_channel_id="123456789", context=[{"role": "user", "content": "你好"}])
    print(invoke(message))