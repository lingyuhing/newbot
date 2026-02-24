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

# ==================== 讯飞实时语音转写大模型配置 ====================
# 支持 ASR + 声纹分离一体化
XFYUN_ASR_APP_ID = "your-xfyun-app-id"  # 讯飞应用ID
XFYUN_ASR_ACCESS_KEY_ID = "your-access-key-id"  # 讯飞访问密钥ID
XFYUN_ASR_ACCESS_KEY_SECRET = "your-access-key-secret"  # 讯飞访问密钥Secret

# ASR 转写参数配置
ASR_LANGUAGE = "autodialect"  # 语种: autodialect(中英+方言)/autominor(多语种)
ASR_ROLE_TYPE = 2  # 角色分离: 0(关闭)/2(声纹分离模式)
ASR_ENG_SPK_MATCH = 0  # 声纹匹配模式: 0(允许未知说话人)/1(严格匹配)

# 声纹库存储配置
import os
VOICEPRINT_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "voiceprint_store.json")
VOICEPRINT_PENDING_DIR = os.path.join(os.path.dirname(__file__), "..", "voiceprint_pending")
VOICEPRINT_MIN_DURATION_MS = 10000  # 声纹注册最小音频时长（毫秒）
