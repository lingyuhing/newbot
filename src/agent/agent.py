from langchain.chat_models import init_chat_model
from src.config import (
    LLM_BASE_URL, LLM_KEY, LLM_MODEL, ROOT_DIR, SKILL_DIR, USER_ID, VIRTUAL_MODE,
    LOG_LEVEL, LOG_DIR, LOG_JSON_FORMAT,
    ASR_ROLE_TYPE, ASR_ENG_SPK_MATCH, VOICEPRINT_MIN_DURATION_MS
)
from src.agent.langchain_fix.graph import create_deep_agent
from deepagents.backends import LocalShellBackend
from src.agent.memory import search_memory_tool
import json
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel
from src.logger import setup_logger, get_logger
from src.xfyun_rtasr import rtasr_client, RTASRResult, Utterance
from src.xfyun_voiceprint import voiceprint_manager
from src.audio_utils import save_audio_to_disk
import base64
import os


class MessageChannelMessage(BaseModel):
    message_channel_id: str
    multimodal: list[dict] = []
    audio: str | None = None


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
    message_content = [{"type": "text", "text": f"消息渠道ID: {messages.message_channel_id}"}]
    
    # 处理音频（如果有）
    if messages.audio:
        logger.info("检测到音频，开始语音转写...")
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
    处理音频：讯飞实时语音转写 + 声纹分离 + 自动注册未识别说话人
    
    Args:
        audio_base64: base64 编码的音频数据
        channel_id: 可选的频道ID，用于音频文件命名
        
    Returns:
        音频识别上下文字符串
    """
    # 1. 保存音频到磁盘
    saved_path = save_audio_to_disk(audio_base64, channel_id)
    if saved_path:
        logger.info(f"音频已保存至: {saved_path}")
    
    # 2. 获取已注册声纹 ID 列表
    feature_ids = voiceprint_manager.get_feature_ids()
    
    # 3. 调用讯飞实时语音转写
    result = rtasr_client.transcribe(
        audio_base64,
        feature_ids=feature_ids,
        role_type=ASR_ROLE_TYPE,
        eng_spk_match=ASR_ENG_SPK_MATCH
    )
    
    if not result:
        logger.warning("语音转写失败")
        return "\n[音频内容：识别失败]"
    
    # 4. 如果没有说话人分段信息，直接返回文本
    if not result.utterances:
        return f"\n[音频内容：{result.text}]"
    
    # 5. 处理未匹配说话人（累积片段 + 自动注册）
    speaker_map = _process_unknown_speakers(
        audio_base64,
        result.utterances,
        result.unknown_speaker_ids
    )
    
    # 6. 构建带说话人标识的文本
    formatted_text = _format_result(result.utterances, speaker_map)
    
    logger.info(f"音频处理完成: {len(result.utterances)} 个片段, {len(speaker_map)} 个说话人")
    return formatted_text


def _process_unknown_speakers(
    audio_base64: str,
    utterances: list[Utterance],
    unknown_speaker_ids: set[int]
) -> dict[int, str]:
    """
    处理未匹配说话人：累积片段 + 自动注册
    
    Args:
        audio_base64: 原始音频 base64
        utterances: 所有语音片段
        unknown_speaker_ids: 未匹配的说话人 ID 集合
        
    Returns:
        说话人映射 {speaker_id: feature_id 或 "未知说话人_N"}
    """
    speaker_map = {}
    
    if not unknown_speaker_ids:
        return speaker_map
    
    # 解码音频数据
    try:
        audio_data = base64.b64decode(audio_base64)
        # 跳过 WAV 头
        if audio_data[:4] == b'RIFF':
            audio_data = audio_data[44:]
    except Exception as e:
        logger.error(f"解码音频失败: {e}")
        return {sid: f"未知说话人_{sid}" for sid in unknown_speaker_ids}
    
    # 为每个未知说话人创建待注册记录
    pending_speakers = {}  # speaker_id -> pending_id
    
    for speaker_id in unknown_speaker_ids:
        # 收集该说话人的所有音频片段
        speaker_segments = []
        total_duration_ms = 0
        
        for utterance in utterances:
            if utterance.speaker_id == speaker_id:
                segment_data = _extract_segment(
                    audio_data,
                    utterance.start_time,
                    utterance.end_time
                )
                if segment_data:
                    duration_ms = utterance.end_time - utterance.start_time
                    speaker_segments.append((segment_data, duration_ms))
                    total_duration_ms += duration_ms
        
        if not speaker_segments:
            speaker_map[speaker_id] = f"未知说话人_{speaker_id}"
            continue
        
        # 检查累积时长
        pending_id = voiceprint_manager.create_pending_speaker()
        pending_speakers[speaker_id] = pending_id
        
        for segment_data, duration_ms in speaker_segments:
            voiceprint_manager.add_pending_segment(
                pending_id,
                segment_data,
                duration_ms
            )
        
        # 尝试注册
        total_duration = voiceprint_manager.get_pending_total_duration(pending_id)
        
        if total_duration >= VOICEPRINT_MIN_DURATION_MS:
            # 合并并注册
            feature_id = voiceprint_manager.merge_and_register(pending_id)
            if feature_id:
                speaker_map[speaker_id] = feature_id
                logger.info(f"说话人 {speaker_id} 已自动注册: feature_id={feature_id}")
            else:
                speaker_map[speaker_id] = f"未知说话人_{speaker_id}"
                logger.warning(f"说话人 {speaker_id} 注册失败")
        else:
            speaker_map[speaker_id] = f"未知说话人_{speaker_id}"
            logger.info(f"说话人 {speaker_id} 累积音频不足 {total_duration}ms，等待更多数据")
    
    return speaker_map


def _extract_segment(audio_data: bytes, start_ms: int, end_ms: int) -> bytes:
    """
    从 PCM 音频数据中提取指定时间段的片段
    
    Args:
        audio_data: PCM 音频数据
        start_ms: 起始时间（毫秒）
        end_ms: 结束时间（毫秒）
        
    Returns:
        提取的 PCM 数据
    """
    try:
        # 16k 16bit mono = 32000 bytes/s = 32 bytes/ms
        bytes_per_ms = 32
        
        start_byte = start_ms * bytes_per_ms
        end_byte = end_ms * bytes_per_ms
        
        # 边界检查
        if start_byte >= len(audio_data):
            return b''
        
        end_byte = min(end_byte, len(audio_data))
        
        return audio_data[start_byte:end_byte]
        
    except Exception as e:
        logger.error(f"提取音频片段失败: {e}")
        return b''


def _format_result(utterances: list[Utterance], speaker_map: dict[int, str]) -> str:
    """
    格式化转写结果
    
    Args:
        utterances: 语音片段列表
        speaker_map: 说话人映射
        
    Returns:
        格式化的文本
    """
    formatted_text = "\n[音频内容：\n"
    current_speaker = None
    
    for utterance in utterances:
        speaker_id = utterance.speaker_id
        
        # 获取说话人标识
        if utterance.feature_id:
            # 已匹配声纹
            speaker_label = utterance.feature_id
        elif speaker_id in speaker_map:
            # 未匹配但已处理
            speaker_label = speaker_map[speaker_id]
        else:
            speaker_label = f"说话人_{speaker_id}"
        
        # 切换说话人时换行
        if speaker_id != current_speaker:
            formatted_text += f"\n[{speaker_label}]: "
            current_speaker = speaker_id
        
        formatted_text += utterance.text
    
    formatted_text += "\n]"
    return formatted_text
