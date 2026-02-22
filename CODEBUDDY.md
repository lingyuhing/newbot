# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## 项目概述

newbot 是一个基于 LangChain/LangGraph 的 AI Agent 服务，提供 WebSocket 接口进行实时对话交互。Agent 具备规划、文件操作、子代理调用、长期记忆和多模态音频处理等能力。

## 常用命令

### 启动服务器
```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

### 配置文件
首次运行前，复制 `src/config.example.py` 为 `src/config.py` 并填写必要的 API 密钥。

### 查看日志
```bash
# 查看服务器日志
tail -f logs/server.log

# 查看Agent日志
tail -f logs/agent.log
```

### 依赖安装
项目主要依赖：
- fastapi, uvicorn (Web服务)
- langchain, langgraph (Agent框架)
- pydantic (数据验证)
- deepagents (中间件和Backend)
- 其他：websockets, python-multipart

安装依赖（根据项目实际环境配置）：
```bash
pip install fastapi uvicorn langchain langgraph pydantic
```

## 架构概览

### 核心组件

**WebSocket 服务器 (`main.py`)**
- FastAPI 应用，提供 `/ws/{client_id}` WebSocket 端点
- `ConnectionManager` 管理多客户端连接，支持重复连接拒绝
- HTTP 端点：
  - `GET /get_channel_id`：返回当前所有活跃连接的客户端 ID 列表（供技能调用）
  - `POST /send_message`：向指定客户端发送消息（供技能调用）
- 消息流通过 `stream()` 函数处理，支持异步并发响应
- 使用 `asyncio.to_thread()` 在后台线程中运行 Agent，避免阻塞 WebSocket

**Agent 系统 (`src/agent/agent.py`)**
- 使用 `create_deep_agent()` 创建深度 Agent（定义见 `src/agent/langchain_fix/graph.py`）
- Agent 核心配置：
  - LLM 模型：通过 `init_chat_model()` 初始化（支持 OpenAI 兼容接口）
  - Backend：`LocalShellBackend` 提供文件系统和 shell 执行能力
  - 技能目录：从 `SKILL_DIR` 配置加载
  - 记忆工具：`search_memory_tool` 用于长期记忆检索
  - Checkpointer：SQLite (`checkpoints.db`) 持久化会话状态
- 会话管理：使用 `thread_id` (配置为 `USER_ID`) 保持会话上下文
- `MessageChannelMessage` 封装消息渠道 ID、多模态内容和可选音频
- `_process_audio()` 函数处理音频输入：ASR 识别 + 声纹识别

**音频处理系统**
- `src/asr.py`：火山引擎 ASR 语音识别（支持说话人分离）
  - `ASRResult` 包含识别文本和 `utterances` 列表（每个片段含 speaker_id、start_time、end_time）
  - 通过 `enable_speaker_info=True` 开启说话人分离
- `src/voiceprint.py`：讯飞声纹识别（说话人身份识别）
  - 维护声纹库，识别说话人身份（返回 feature_id）
  - 支持新说话人自动注册
- `src/audio_utils.py`：音频工具集
  - `extract_audio_segment()`：根据时间戳提取音频片段
  - `save_audio_to_disk()`：保存音频到 `audio/` 目录
- 完整处理流程：
  1. 保存音频到磁盘
  2. ASR 识别（获取文本 + 说话人分段）
  3. 对每个说话人片段提取音频
  4. 声纹识别匹配说话人身份
  5. 构建带说话人标识的格式化文本返回

**记忆系统 (`src/agent/memory.py`)**
- 基于 Mem0 云服务的长期记忆存储
- `search_memory_tool` 作为 LangChain 工具注入 Agent
- 通过 `USER_ID` 隔离不同用户的记忆数据

**深度 Agent 构建 (`src/agent/langchain_fix/graph.py`)**
- `create_deep_agent()` 工厂函数，构建具备完整能力的 Agent
- 中间件栈（按加载顺序）：
  1. `TodoListMiddleware`：任务列表管理
  2. `MemoryMiddleware`（可选）：当 `memory` 参数非空时加载，注入记忆内容到系统提示
  3. `SkillsMiddleware`（可选）：当 `skills` 参数非空时加载，提供技能调用能力
  4. `FilesystemMiddleware`：文件系统操作
  5. `SubAgentMiddleware`：子代理调用（包含通用子代理和自定义子代理）
  6. `_DeepAgentsSummarizationMiddleware`：对话历史摘要，避免上下文过长
  7. `AnthropicPromptCachingMiddleware`：Anthropic 提示缓存优化
  8. `PatchToolCallsMiddleware`：工具调用补丁
- 内置工具：
  - `write_todos`：任务列表管理
  - 文件操作：`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`
  - `execute`：执行 shell 命令（需 Backend 支持）
  - `task`：调用子代理
- 子代理系统：
  - 内置通用子代理 (`GENERAL_PURPOSE_SUBAGENT`)：具备完整的文件操作、摘要等能力
  - 支持自定义子代理：可指定独立的 model、tools、middleware
  - 子代理继承主代理的技能配置（如指定）
- 递归限制：1000（通过 `.with_config({"recursion_limit": 1000})` 配置）

### 技能系统

技能位于 `skills/` 目录，每个技能包含：
- `SKILL.md`：技能描述和使用说明（YAML frontmatter 包含 name 和 description）
- `scripts/`：可执行的 Python 脚本

技能通过 `SkillsMiddleware` 加载，Agent 可通过调用脚本执行特定任务。

**当前技能示例：`skill-channel-active`**
- 用途：管理 WebSocket 连接和消息发送
- 脚本：
  - `scripts/get_clients.py`：获取所有活跃连接的客户端 ID 列表
  - `scripts/send_message.py`：向指定客户端发送消息（参数：`-c <客户端ID> -m "<消息内容>"`）
- 调用的 HTTP 端点：
  - `GET /get_channel_id`
  - `POST /send_message`

### 日志系统 (`src/logger.py`)

统一日志配置，支持控制台/文件双输出、JSON 格式、自动轮转。各模块通过 `setup_logger()` 创建独立日志器（命名模式：`newbot.*`）。

### 配置 (`src/config.py`)

关键配置项：
- **LLM 服务**：
  - `LLM_MODEL`：模型名称
  - `LLM_KEY`：API 密钥
  - `LLM_BASE_URL`：API 基础 URL（支持 OpenAI 兼容接口）
- **Agent 工作环境**：
  - `ROOT_DIR`：Agent 工作目录（默认 `work/`）
  - `SKILL_DIR`：技能目录列表
  - `VIRTUAL_MODE`：虚拟模式开关（影响 `LocalShellBackend` 的执行行为）
- **记忆与持久化**：
  - `MEM0_API_KEY`：Mem0 记忆服务密钥
  - `USER_ID`：用户标识（用于会话持久化和记忆检索）
- **音频服务**：
  - `ASR_APP_KEY`/`ASR_ACCESS_KEY`：火山引擎 ASR 配置
  - `ASR_RESOURCE_ID`：ASR 资源 ID
  - `XFYUN_API_KEY`/`XFYUN_API_SECRET`：讯飞声纹识别配置
  - `XFYUN_VOICEPRINT_GROUP_ID`：声纹库组 ID
  - `XFYUN_VOICEPRINT_THRESHOLD`：声纹匹配阈值
- **服务器与日志**：
  - `HOST`/`PORT`：服务器监听地址
  - `LOG_LEVEL`/`LOG_DIR`/`LOG_FILE`：日志配置
  - `LOG_JSON_FORMAT`：是否使用 JSON 格式输出日志

### 数据流

**消息处理流程：**
1. 客户端通过 WebSocket 连接到 `/ws/{client_id}`
2. 客户端发送 JSON 消息（支持文本、多模态内容、音频 base64）
3. `ConnectionManager` 检查是否重复连接，拒绝已存在的连接
4. 消息被封装为 `MessageChannelMessage`（包含 channel_id、multimodal、audio）
5. 在后台线程中调用 `stream()` 函数处理消息

**音频处理流程：**
1. 检测到 `audio` 字段时，调用 `_process_audio()`
2. 保存音频到 `audio/` 目录（以 channel_id 和时间戳命名）
3. 调用火山引擎 ASR 识别音频（开启说话人分离）
4. 对每个说话人片段：
   - 提取该时间段的音频片段
   - 调用讯飞声纹识别确定说话人身份
   - 缓存识别结果避免重复识别
5. 构建格式化文本：`[音频内容：\n[说话人 ID]: 文本...]`
6. 将音频上下文添加到消息内容中

**Agent 处理流程：**
1. 构建消息内容（channel_id + 音频上下文 + multimodal 内容）
2. 使用 `thread_id = USER_ID` 调用 `agent.stream()` 保持会话上下文
3. Agent 通过 SQLite checkpointer 加载历史会话状态
4. Agent 执行：
   - 解析用户意图
   - 调用工具（文件操作、shell、记忆检索等）
   - 调用技能脚本
   - 调用子代理处理子任务
5. 以流式方式返回 token 给客户端

**会话持久化机制：**
- 使用 LangGraph 的 `SqliteSaver` 作为 checkpointer
- 每次调用时通过 `thread_id` 恢复会话状态
- 所有对话历史和工具调用结果都持久化到 `checkpoints.db`
- 服务重启后会话状态仍然保留
