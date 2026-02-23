# Agent 消息流说明

## 消息来源

你收到的消息来自 WebSocket 客户端连接。每个客户端通过 `ws://HOST:PORT/ws/{client_id}` 建立连接。

**消息结构** (`MessageChannelMessage`)：
- `message_channel_id`: 当前消息来源的客户端 ID（你回复的消息会发送给这个客户端）
- `multimodal`: 多模态内容（文本、图片等）
- `audio`: 音频数据（base64 编码）

## 消息发送

你的回复会自动流式发送给 `message_channel_id` 对应的客户端。

## 与其他客户端通信

你可以通过技能 `skill-channel-active` 与其他已连接的客户端通信：

1. **获取所有活跃客户端 ID**：
   ```bash
   python skills/skill-channel-active/scripts/get_clients.py
   ```

2. **向指定客户端发送消息**：
   ```bash
   python skills/skill-channel-active/scripts/send_message.py -c <client_id> -m "<消息内容>"
   ```

## 使用场景示例

- 当用户请求广播消息给所有客户端时，先调用 `get_clients.py` 获取列表，再逐个调用 `send_message.py`
- 当需要通知其他客户端某个事件时，使用 `send_message.py` 发送

## 注意事项

- 客户端连接断开后，其 ID 会从活跃列表中移除
- 发送消息前应先确认目标客户端仍在活跃列表中
