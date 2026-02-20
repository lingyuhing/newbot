# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## 项目概述

newbot 是一个基于 LangChain/LangGraph 的 AI Agent 服务，提供 WebSocket 接口进行实时对话交互。Agent 具备规划、文件操作、子代理调用和长期记忆等能力。

## 常用命令

### 启动服务器
```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

### 启动 CLI 客户端
```bash
python cli_client.py [--host HOST] [--port PORT] [--client-id ID]
```

### 配置文件
首次运行前，复制 `src/config.example.py` 为 `src/config.py` 并填写必要的 API 密钥。

## 架构概览

### 核心组件

**WebSocket 服务器 (`main.py`)**
- FastAPI 应用，提供 `/ws/{client_id}` WebSocket 端点
- `ConnectionManager` 管理多客户端连接
- HTTP 端点 `/get_channel_id` 和 `/send_message` 用于通道管理
- 消息流通过 `stream()` 函数处理

**Agent 系统 (`src/agent/agent.py`)**
- 使用 `create_deep_agent()` 创建深度 Agent（见 `langchain_fix/graph.py`）
- Agent 配置：LLM 模型、LocalShellBackend、技能目录、记忆工具
- SQLite checkpointer (`checkpoints.db`) 持久化会话状态
- `MessageChannelMessage` 封装消息渠道 ID、内容和可选图片

**记忆系统 (`src/agent/memory.py`)**
- 基于 Mem0 云服务的长期记忆存储
- `search_memory_tool` 作为 LangChain 工具注入 Agent

**深度 Agent 构建 (`src/agent/langchain_fix/graph.py`)**
- `create_deep_agent()` 工厂函数，构建具备完整能力的 Agent
- 中间件栈：TodoListMiddleware → MemoryMiddleware → SkillsMiddleware → FilesystemMiddleware → SubAgentMiddleware → SummarizationMiddleware → AnthropicPromptCachingMiddleware → PatchToolCallsMiddleware
- 内置工具：write_todos、文件操作（ls/read_file/write_file/edit_file/glob/grep）、execute（shell）、task（子代理调用）
- 递归限制：1000

### 技能系统

技能位于 `skills/` 目录，每个技能包含：
- `SKILL.md`：技能描述和使用说明
- `scripts/`：可执行的 Python 脚本

技能通过 `SkillsMiddleware` 加载，Agent 可调用脚本执行特定任务。

### 日志系统 (`src/logger.py`)

统一日志配置，支持控制台/文件双输出、JSON 格式、自动轮转。各模块通过 `setup_logger()` 创建独立日志器（命名模式：`newbot.*`）。

### 配置 (`src/config.py`)

关键配置项：
- `LLM_MODEL`/`LLM_KEY`/`LLM_BASE_URL`：LLM 服务配置
- `ROOT_DIR`：Agent 工作目录（默认 `work/`）
- `SKILL_DIR`：技能目录列表
- `VIRTUAL_MODE`：虚拟模式开关
- `MEM0_API_KEY`：Mem0 记忆服务密钥
- `USER_ID`：用户标识（用于会话持久化和记忆检索）

### 数据流

1. 客户端通过 WebSocket 发送消息
2. 服务器将消息封装为 `MessageChannelMessage`
3. `stream()` 调用 Agent 的 `stream()` 方法，以 thread_id 保持会话上下文
4. Agent 处理消息，可调用工具、技能或子代理
5. 响应以流式 token 返回客户端
