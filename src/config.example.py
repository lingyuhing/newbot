# 用户配置
USER_ID="1"

# LLM 配置
LLM_MODEL="your-llm-model-name"
LLM_KEY="your-llm-api-key"
LLM_BASE_URL="https://your-llm-api-endpoint.com/api/v3"

# 工作目录配置
ROOT_DIR="/path/to/your/work/directory"
SKILL_DIR=["/path/to/your/skills/directory"]
VIRTUAL_MODE=False

# Mem0 记忆服务配置
MEM0_API_KEY="your-mem0-api-key"

# 服务器配置
HOST = "http://127.0.0.1"
PORT = 8000

# 日志配置
LOG_LEVEL = "INFO"          # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_DIR = "logs"            # 日志目录
LOG_FILE = "server.log"     # 主日志文件名
LOG_JSON_FORMAT = False     # 是否使用 JSON 格式（生产环境推荐 True）
