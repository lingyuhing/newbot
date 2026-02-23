from langchain.chat_models import init_chat_model
from src.config import LLM_BASE_URL, LLM_KEY, LLM_MODEL, ROOT_DIR, SKILL_DIR,USER_ID,VIRTUAL_MODE,LOG_LEVEL,LOG_DIR,LOG_JSON_FORMAT
from src.agent.langchain_fix.graph import create_deep_agent
from deepagents.backends import LocalShellBackend
from src.agent.memory import search_memory_tool
import json
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel
from src.logger import setup_logger, get_logger
from src.asr import asr_client, ASRResult
from src.voiceprint import voiceprint_client
from src.audio_utils import extract_audio_segment, save_audio_to_disk

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
    checkpointer=checkpointer,
    memory=["/work/AGENTS.md"]
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
    
    # 构建消息内容
    message_content = [{"type":"text","text":f"消息渠道ID: {messages.message_channel_id}"}]
    
    # 处理音频（如果有）
    if messages.audio:
        logger.info("检测到音频，开始 ASR 识别...")
        audio_context = _process_audio(messages.audio, messages.message_channel_id)
        if audio_context:
            message_content.append({"type": "text", "text": audio_context})
    
    # 添加 multimodal 内容
    message_content.extend(messages.multimodal)
    
    try:
        result = agent.stream(
            {"messages": [{"role": "user", "content": message_content}]},
            config=config,
            stream_mode="messages"
        )
        
        for token, message in result:
            yield token.content
            
    except Exception as e:
        logger.error(f"Agent 处理错误: {e}", exc_info=True)
        raise


def _process_audio(audio_base64: str, channel_id: str = None) -> str:
    """
    处理音频：ASR + 声纹识别 + 保存到磁盘
    
    Args:
        audio_base64: base64 编码的音频数据
        channel_id: 可选的频道ID，用于音频文件命名
        
    Returns:
        音频识别上下文字符串
    """
    # 0. 保存音频到磁盘
    saved_path = save_audio_to_disk(audio_base64, channel_id)
    if saved_path:
        logger.info(f"音频已保存至: {saved_path}")
    
    # 1. ASR 识别（开启说话人识别）
    asr_result = asr_client.recognize(audio_base64, enable_speaker_info=True)
    if not asr_result:
        logger.warning("ASR 识别失败")
        return "\n[音频内容：识别失败]"
    
    # 2. 如果没有说话人分段信息，直接返回文本
    if not asr_result.utterances:
        return f"\n[音频内容：{asr_result.text}]"
    
    # 3. 对每个说话人片段进行声纹识别
    speaker_voiceprints = {}  # speaker_id -> feature_id
    
    for utterance in asr_result.utterances:
        speaker_id = utterance.speaker_id
        
        # 已识别过的说话人跳过
        if speaker_id in speaker_voiceprints:
            continue
        
        # 提取该说话人的音频片段
        segment_base64 = extract_audio_segment(
            audio_base64,
            utterance.start_time,
            utterance.end_time
        )
        
        if not segment_base64:
            logger.warning(f"提取音频片段失败: speaker_id={speaker_id}")
            continue
        
        # 声纹识别
        vp_result = voiceprint_client.identify_speaker(segment_base64)
        if vp_result:
            speaker_voiceprints[speaker_id] = vp_result.feature_id
            logger.info(f"说话人 {speaker_id} -> 声纹ID: {vp_result.feature_id} (新: {vp_result.is_new})")
    
    # 4. 构建带说话人标识的文本
    formatted_text = "\n[音频内容：\n"
    current_speaker = None
    
    for utterance in asr_result.utterances:
        speaker_id = utterance.speaker_id
        feature_id = speaker_voiceprints.get(speaker_id, f"未知说话人{speaker_id}")
        
        if speaker_id != current_speaker:
            formatted_text += f"\n[说话人 {feature_id}]: "
            current_speaker = speaker_id
        
        formatted_text += utterance.text
    
    formatted_text += "\n]"
    
    logger.info(f"音频处理完成: {len(asr_result.utterances)} 个片段, {len(speaker_voiceprints)} 个说话人")
    return formatted_text