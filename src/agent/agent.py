from langchain.chat_models import init_chat_model
from src.config import LLM_BASE_URL, LLM_KEY, LLM_MODEL, ROOT_DIR, SKILL_DIR,USER_ID,VIRTUAL_MODE,LOG_LEVEL,LOG_DIR,LOG_JSON_FORMAT
from src.agent.langchain_fix.graph import create_deep_agent
from deepagents.backends import LocalShellBackend
from src.agent.memory import search_memory_tool
from src.asr import transcribe_audio, ASRResult
from src.voiceprint import identify_speaker
from src.audio_utils import download_audio, extract_audio_segment_base64
import json
import sqlite3
import os
import tempfile
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel
from src.logger import setup_logger, get_logger

class MessageChannelMessage(BaseModel):
    message_channel_id: str
    multimodal:list[dict] = []
    audio:str | None = None

# 初始化日志
logger = setup_logger(
    name="newbot.agent",
    level=LOG_LEVEL,
    log_file="agent.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)

model = init_chat_model(
    model=LLM_MODEL,
    model_provider="openai",
    base_url=LLM_BASE_URL,
    api_key=LLM_KEY,
)

# 正确方式：直接构造 SqliteSaver
conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
checkpointer = SqliteSaver(conn)

agent = create_deep_agent(
    model=model,
    backend=LocalShellBackend(root_dir=ROOT_DIR, virtual_mode=VIRTUAL_MODE),
    skills=SKILL_DIR,
    tools=[search_memory_tool],
    checkpointer=checkpointer
)

logger.info(f"Agent 初始化完成: model={LLM_MODEL}, root_dir={ROOT_DIR}")

def stream(messages: MessageChannelMessage):
    """
    流式处理消息
    
    Args:
        messages: 包含消息渠道ID和内容的消息对象
    
    Yields:
        处理后的 token 内容
    """
    logger.debug(f"开始处理消息: channel_id={messages.message_channel_id}")
    
    # 添加 thread_id 配置以保持会话记忆
    config = {
        "configurable": {
            "thread_id": USER_ID
        }
    }
    
    # 处理音频（如果有）
    audio_context = ""
    if messages.audio:
        try:
            audio_context = process_audio(messages.audio)
            logger.info(f"音频处理完成: {len(audio_context)} 字符")
        except Exception as e:
            logger.error(f"音频处理失败: {e}", exc_info=True)
            audio_context = f"[音频处理失败: {e}]"
    
    # 构建消息内容
    content = [{"type": "text", "text": f"消息渠道ID: {messages.message_channel_id}"}]
    
    if audio_context:
        content.append({"type": "text", "text": audio_context})
    
    content.extend(messages.multimodal)
    
    try:
        result = agent.stream(
            {"messages": [{"role": "user", "content": content}]},
            config=config,
            stream_mode="messages"
        )
        
        for token, message in result:
            yield token.content
            
    except Exception as e:
        logger.error(f"Agent 处理错误: {e}", exc_info=True)
        raise


def process_audio(audio_url: str) -> str:
    """
    处理音频：ASR + 声纹识别

    流程：
    1. 调用 ASR 识别（带说话人识别）
    2. 下载音频到本地
    3. 对每个说话人片段提取音频并进行声纹识别
    4. 组装结果

    Args:
        audio_url: 音频文件 URL

    Returns:
        音频识别结果文本
    """
    # 1. ASR 识别（带说话人识别）
    logger.info(f"开始 ASR 识别: {audio_url}")
    asr_result: ASRResult = transcribe_audio(audio_url, enable_speaker=True)

    if not asr_result.utterances:
        # 无说话人分段，直接返回文本
        return f"[语音内容] {asr_result.text}"

    # 2. 下载音频到本地（用于后续分段提取）
    local_audio_path = None
    try:
        local_audio_path = download_audio(audio_url)
        logger.info(f"音频已下载到本地: {local_audio_path}")

        # 3. 对每个说话人片段进行声纹识别
        speaker_results = []
        speaker_feature_map = {}  # 缓存已识别的说话人

        for segment in asr_result.utterances:
            try:
                # 检查是否已识别过该 speaker_id
                if segment.speaker_id in speaker_feature_map:
                    feature_id = speaker_feature_map[segment.speaker_id]
                    speaker_label = f"说话人({feature_id})"
                    speaker_results.append(f"[{speaker_label}] {segment.text}")
                    continue

                # 提取该时间段的音频片段
                audio_base64 = extract_audio_segment_base64(
                    local_audio_path,
                    segment.start_time,
                    segment.end_time,
                )

                # 声纹识别
                voiceprint_result = identify_speaker(audio_base64)
                feature_id = voiceprint_result.feature_id

                # 缓存结果
                speaker_feature_map[segment.speaker_id] = feature_id

                # 标记是否为新声纹
                if voiceprint_result.is_new:
                    speaker_label = f"说话人({feature_id})[新]"
                else:
                    speaker_label = f"说话人({feature_id})"

                speaker_results.append(f"[{speaker_label}] {segment.text}")
                logger.info(
                    f"声纹识别完成: speaker_id={segment.speaker_id}, "
                    f"feature_id={feature_id}, is_new={voiceprint_result.is_new}"
                )

            except Exception as e:
                logger.warning(f"声纹识别失败: {e}")
                speaker_results.append(f"[说话人{segment.speaker_id}] {segment.text}")

        # 4. 组装结果
        result = "[语音内容]\n" + "\n".join(speaker_results)
        return result

    finally:
        # 清理临时文件
        if local_audio_path and os.path.exists(local_audio_path):
            os.remove(local_audio_path)
            logger.debug(f"已清理临时文件: {local_audio_path}")