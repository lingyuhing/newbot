---
name: channel-active
description: 此技能用于管理活跃的消息通道。提供获取已连接客户端ID列表和向特定客户端发送消息的工具。当用户想要查看已连接的客户端、检查通道状态或向特定已连接客户端发送消息时使用此技能。
---

# 通道管理技能

此技能为消息通道系统提供通道管理能力。通过HTTP API端点与已连接的WebSocket客户端进行交互。

## 使用场景

在以下情况下使用此技能：
- 用户想要列出所有当前已连接的客户端/通道
- 用户想要查看哪些通道ID处于活跃状态
- 用户想要向特定的已连接客户端发送消息
- 用户询问通道状态或已连接用户

## 可用脚本

### 1. 获取已连接客户端

**脚本：** `scripts/get_clients.py`

从通道服务器获取当前所有已连接的客户端ID列表。

```bash
python scripts/get_clients.py
```

此脚本返回当前连接到服务器的所有活跃WebSocket连接ID。

### 2. 发送消息给客户端

**脚本：** `scripts/send_message.py`

通过通道系统向指定的已连接客户端发送消息。

```bash
python scripts/send_message.py -c <客户端ID> -m "<消息内容>"
```

**参数说明：**
- `-c, --client`: 目标客户端ID（必填）
- `-m, --message`: 要发送的消息内容（必填）

## 工作流程

1. **查看已连接客户端：** 执行 `scripts/get_clients.py` 获取所有活跃的通道ID
2. **发送消息：** 首先使用 get_clients.py 获取客户端ID，然后使用 `send_message.py` 并指定目标客户端ID和消息内容

## 配置

此技能使用 `src/config.py` 中的以下配置：
- `HOST`: 服务器主机地址（默认：http://127.0.0.1）
- `PORT`: 服务器端口（默认：8000）

## 使用的API端点

- `GET /get_channel_id` - 返回已连接的客户端ID列表
- `POST /send_message` - 向指定客户端发送消息（请求体：`{"context": "<消息内容>", "channel_id": "<客户端ID>"}`）
