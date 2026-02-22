"""
音频处理工具模块

提供音频分段提取、格式转换等功能
"""

import base64
import subprocess
import tempfile
import os
import requests
from typing import Optional
from src.config import LOG_LEVEL, LOG_DIR, LOG_JSON_FORMAT
from src.logger import setup_logger

logger = setup_logger(
    name="newbot.audio_utils",
    level=LOG_LEVEL,
    log_file="audio_utils.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)


def download_audio(audio_url: str, output_path: Optional[str] = None) -> str:
    """
    下载音频文件

    Args:
        audio_url: 音频 URL
        output_path: 输出路径，不指定则使用临时文件

    Returns:
        本地音频文件路径
    """
    if output_path is None:
        # 创建临时文件
        fd, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

    logger.info(f"下载音频: {audio_url}")
    response = requests.get(audio_url, stream=True)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    logger.info(f"音频已下载: {output_path}")
    return output_path


def extract_audio_segment_base64(
    audio_path: str,
    start_ms: int,
    end_ms: int,
    sample_rate: int = 16000,
    channels: int = 1,
) -> str:
    """
    提取音频片段并转换为 Base64

    使用 ffmpeg 提取指定时间段的音频，转换为 16k 16bit mono wav 格式

    Args:
        audio_path: 音频文件路径或 URL
        start_ms: 开始时间（毫秒）
        end_ms: 结束时间（毫秒）
        sample_rate: 采样率（默认 16000）
        channels: 声道数（默认 1）

    Returns:
        Base64 编码的音频数据
    """
    start_sec = start_ms / 1000
    duration = (end_ms - start_ms) / 1000

    logger.debug(f"提取音频片段: start={start_sec}s, duration={duration}s")

    # 使用 ffmpeg 提取片段并输出到 stdout
    cmd = [
        "ffmpeg",
        "-y",  # 覆盖输出文件
        "-ss",
        str(start_sec),  # 开始时间
        "-i",
        audio_path,  # 输入文件
        "-t",
        str(duration),  # 持续时间
        "-f",
        "wav",  # 输出格式
        "-acodec",
        "pcm_s16le",  # 16bit PCM
        "-ar",
        str(sample_rate),  # 采样率
        "-ac",
        str(channels),  # 声道数
        "-",  # 输出到 stdout
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True,
        )
        audio_data = result.stdout
        logger.debug(f"音频片段提取成功: {len(audio_data)} bytes")
        return base64.b64encode(audio_data).decode("utf-8")

    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg 提取失败: {e.stderr.decode()}")
        raise RuntimeError(f"音频提取失败: {e.stderr.decode()}")
    except FileNotFoundError:
        logger.error("ffmpeg 未安装")
        raise RuntimeError("ffmpeg 未安装，请先安装 ffmpeg")


def extract_audio_segment_from_url(
    audio_url: str,
    start_ms: int,
    end_ms: int,
    sample_rate: int = 16000,
    channels: int = 1,
    keep_local: bool = False,
) -> tuple[str, Optional[str]]:
    """
    从 URL 提取音频片段

    Args:
        audio_url: 音频 URL
        start_ms: 开始时间（毫秒）
        end_ms: 结束时间（毫秒）
        sample_rate: 采样率
        channels: 声道数
        keep_local: 是否保留本地下载的文件

    Returns:
        (Base64 音频数据, 本地文件路径或 None)
    """
    # 下载音频到本地
    local_path = download_audio(audio_url)

    try:
        # 提取片段
        audio_base64 = extract_audio_segment_base64(
            local_path, start_ms, end_ms, sample_rate, channels
        )

        if keep_local:
            return audio_base64, local_path
        else:
            # 删除临时文件
            os.remove(local_path)
            return audio_base64, None

    except Exception as e:
        # 确保清理临时文件
        if os.path.exists(local_path):
            os.remove(local_path)
        raise


def convert_to_wav16k(
    audio_path: str,
    output_path: Optional[str] = None,
) -> str:
    """
    将音频转换为 16k 16bit mono wav 格式

    Args:
        audio_path: 输入音频路径
        output_path: 输出路径，不指定则使用临时文件

    Returns:
        转换后的文件路径
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        audio_path,
        "-f",
        "wav",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        output_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"音频转换成功: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"音频转换失败: {e.stderr.decode()}")
        raise RuntimeError(f"音频转换失败: {e.stderr.decode()}")
