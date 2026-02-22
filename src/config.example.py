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
HOST = "127.0.0.1"
PORT = 8000

# 日志配置
LOG_LEVEL = "INFO"
LOG_DIR = "logs"
LOG_FILE = "server.log"
LOG_JSON_FORMAT = False

# 火山引擎 ASR 配置
ASR_APP_KEY = ""  # 火山引擎 ASR App Key
ASR_ACCESS_KEY = ""  # 火山引擎 Access Key
ASR_RESOURCE_ID = "volc.seedasr.auc"  # Seed-ASR 模型 2.0

# 讯飞声纹识别配置
XFYUN_API_KEY = ""  # 讯飞 API Key
XFYUN_API_SECRET = ""  # 讯飞 API Secret
XFYUN_VOICEPRINT_URL = "https://api.xf-yun.com/v1/private/s1aa729d0"
XFYUN_VOICEPRINT_GROUP_ID = "default_group"  # 声纹组 ID
XFYUN_VOICEPRINT_THRESHOLD = 0.8  # 声纹匹配阈值
