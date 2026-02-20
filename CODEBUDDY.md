# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## 项目概述

这是一个基于 FastAPI 的 WebSocket 聊天代理系统，使用 LangChain 和 deep agents 架构构建。系统支持多客户端 WebSocket 连接、长期记忆存储、以及可扩展的技能系统。

## 常用命令

### 运行服务器

```bash
python main.py
```

服务器将在配置的 HOST:PORT 上启动（默认 http://127.0.0.1:8000）。

### 运行测试

```bash
pytest
```

### 安装依赖

```bash
pip install -e .
```

## 架构概览

### 核心组件

**1. 主入口 (main.py)**

FastAPI WebSocket 服务器，提供：
- `/ws/{client_id}` - WebSocket 连接端点，处理客户端消息并流式返回代理响应
- `/get_channel_id` - GET 端点，返回所有已连接的客户端 ID
- `/send_message` - POST 端点，向指定客户端发送消息

`ConnectionManager` 类管理所有活跃的 WebSocket 连接。

**2. 代理系统 (src/agent/agent.py)**

使用 `create_deep_agent` 创建深度代理，配置包括：
- LLM 模型初始化（通过 config.py 配置）
- SqliteSaver 检查点存储（checkpoints.db），用于会话状态持久化
- LocalShellBackend 后端，支持文件系统操作和命令执行
- 技能系统集成
- 记忆搜索工具集成

`stream()` 异步函数处理消息流，使用 thread_id 维护会话上下文。

**3. 记忆系统 (src/agent/memory.py)**

集成 Mem0 服务，提供长期记忆存储：
- `add_memory()` - 添加记忆
- `search_memory()` - 搜索记忆
- `search_memory_tool` - LangChain 工具封装，供代理调用

**4. LangChain 扩展 (src/agent/langchain_fix/)**

包含自定义的代理图和摘要中间件实现：
- `graph.py` - `create_deep_agent()` 函数，构建具有规划、文件系统、子代理能力的深度代理
- `summarization.py` - 对话摘要中间件

代理中间件栈包括：TodoListMiddleware、FilesystemMiddleware、SubAgentMiddleware、SummarizationMiddleware、AnthropicPromptCachingMiddleware、PatchToolCallsMiddleware。

**5. 技能系统 (skills/)**

可扩展的技能模块，每个技能包含：
- `SKILL.md` - 技能描述和使用说明
- `scripts/` - 可执行脚本

当前包含 `skill-channel-active` 技能，用于管理活跃的消息通道。

### 配置系统

`src/config.py` 包含所有配置项（从 `config.example.py` 复制并填入实际值）：
- `USER_ID` - 用户标识
- `LLM_MODEL`, `LLM_KEY`, `LLM_BASE_URL` - LLM 配置
- `ROOT_DIR` - 工作目录
- `SKILL_DIR` - 技能目录列表
- `VIRTUAL_MODE` - 虚拟模式开关
- `MEM0_API_KEY` - Mem0 API 密钥
- `HOST`, `PORT` - 服务器配置

### 数据流

1. 客户端通过 WebSocket 连接到 `/ws/{client_id}`
2. 消息被包装为 JSON 格式（包含消息渠道 ID 和内容）
3. 代理通过 `astream()` 流式处理消息
4. 响应 token 通过 WebSocket 返回给客户端
5. 会话状态通过 SqliteSaver 持久化，支持跨会话记忆

### 技能开发

新技能应放在 `skills/` 目录下，结构如下：
```
skills/
└── skill-name/
    ├── SKILL.md      # 技能描述（包含 name, description 元数据）
    └── scripts/      # 可执行 Python 脚本
```

技能通过 `SKILL_DIR` 配置加载到代理中。
