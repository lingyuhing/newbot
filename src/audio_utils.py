"""音频处理工具"""
import base64
import io
import wave
import tempfile
import os
from datetime import datetime
from typing import Optional
from src.logger import setup_logger
from src.config import LOG_LEVEL, LOG_DIR, LOG_JSON_FORMAT

logger = setup_logger(
    name="newbot.audio_utils",
    level=LOG_LEVEL,
    log_file="audio_utils.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)

# 音频保存目录
AUDIO_SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio")


def save_audio_to_disk(audio_base64: str, channel_id: str = None) -> Optional[str]:
    """
    保存 base64 音频到磁盘
    
    Args:
        audio_base64: base64 编码的音频数据
        channel_id: 可选的频道ID，用于文件命名
        
    Returns:
        保存的文件路径，失败返回 None
    """
    try:
        # 确保目录存在
        os.makedirs(AUDIO_SAVE_DIR, exist_ok=True)
        
        # 生成文件名：时间戳 + 频道ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if channel_id:
            filename = f"{timestamp}_{channel_id}.wav"
        else:
            filename = f"{timestamp}.wav"
        
        filepath = os.path.join(AUDIO_SAVE_DIR, filename)
        
        # 解码音频数据
        audio_data = base64.b64decode(audio_base64)
        
        # 检查是否已经是 WAV 格式（有 RIFF 头）
        if audio_data[:4] == b'RIFF':
            # 已经是 WAV 格式，直接写入
            with open(filepath, "wb") as f:
                f.write(audio_data)
        else:
            # 原始 PCM 数据，需要添加 WAV 头
            # 假设格式：16kHz, 16bit, mono（与客户端配置一致）
            with wave.open(filepath, "wb") as wav_file:
                wav_file.setnchannels(1)      # 单声道
                wav_file.setsampwidth(2)       # 16bit = 2 bytes
                wav_file.setframerate(16000)   # 16kHz
                wav_file.writeframes(audio_data)
        
        logger.info(f"音频已保存: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"保存音频失败: {e}", exc_info=True)
        return None


def extract_audio_segment(
    audio_base64: str,
    start_ms: int,
    end_ms: int
) -> Optional[str]:
    """
    从 base64 音频中提取指定时间段的片段
    
    Args:
        audio_base64: 原始音频的 base64 编码
        start_ms: 起始时间（毫秒）
        end_ms: 结束时间（毫秒）
        
    Returns:
        提取片段的 base64 编码，失败返回 None
    """
    try:
        # 解码 base64
        audio_data = base64.b64decode(audio_base64)
        
        # 尝试使用 pydub 处理音频
        try:
            from pydub import AudioSegment
        except ImportError:
            logger.warning("pydub 未安装，使用简单字节截取方式")
            return _extract_segment_simple(audio_data, start_ms, end_ms)
        
        # 使用 pydub 处理
        audio = AudioSegment.from_file(io.BytesIO(audio_data))
        
        # 提取片段
        segment = audio[start_ms:end_ms]
        
        # 转换为 16k, 16bit, mono wav
        segment = segment.set_frame_rate(16000)
        segment = segment.set_sample_width(2)  # 16bit = 2 bytes
        segment = segment.set_channels(1)  # mono
        
        # 导出为 wav
        buffer = io.BytesIO()
        segment.export(buffer, format="wav")
        segment_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        logger.debug(f"提取音频片段: {start_ms}ms - {end_ms}ms")
        return segment_base64
        
    except Exception as e:
        logger.error(f"提取音频片段失败: {e}", exc_info=True)
        return None


def _extract_segment_simple(audio_data: bytes, start_ms: int, end_ms: int) -> Optional[str]:
    """
    简单的音频片段提取（假设是 16k 16bit mono wav）
    
    Args:
        audio_data: 原始音频数据
        start_ms: 起始时间（毫秒）
        end_ms: 结束时间（毫秒）
        
    Returns:
        提取片段的 base64 编码
    """
    try:
        # 跳过 wav 头 (44 bytes)
        if audio_data[:4] == b'RIFF':
            audio_data = audio_data[44:]
        
        # 16k 16bit mono = 32000 bytes/s = 32 bytes/ms
        bytes_per_ms = 32
        
        start_byte = start_ms * bytes_per_ms
        end_byte = end_ms * bytes_per_ms
        
        segment_data = audio_data[start_byte:end_byte]
        
        # 生成新的 wav 头
        import wave
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(segment_data)
        
        segment_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return segment_base64
        
    except Exception as e:
        logger.error(f"简单提取失败: {e}", exc_info=True)
        return None


def convert_to_wav_16k(audio_base64: str) -> Optional[str]:
    """
    将音频转换为 16k 16bit mono wav 格式
    
    Args:
        audio_base64: 原始音频的 base64 编码
        
    Returns:
        转换后音频的 base64 编码，失败返回 None
    """
    try:
        audio_data = base64.b64decode(audio_base64)
        
        try:
            from pydub import AudioSegment
        except ImportError:
            logger.warning("pydub 未安装，假设音频已是正确格式")
            return audio_base64
        
        audio = AudioSegment.from_file(io.BytesIO(audio_data))
        
        # 转换格式
        audio = audio.set_frame_rate(16000)
        audio = audio.set_sample_width(2)
        audio = audio.set_channels(1)
        
        # 导出
        buffer = io.BytesIO()
        audio.export(buffer, format="wav")
        
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
        
    except Exception as e:
        logger.error(f"音频格式转换失败: {e}", exc_info=True)
        return None
