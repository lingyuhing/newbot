"""
火山引擎 ASR 语音识别模块（带说话人识别）

支持两种模型：
- volc.bigasr.auc: 语音识别大模型 1.0
- volc.seedasr.auc: Seed-ASR 模型 2.0（推荐）
"""

import hashlib
import hmac
import time
import json
import uuid
import requests
from dataclasses import dataclass
from typing import Optional
from src.config import (
    ASR_APP_KEY,
    ASR_ACCESS_KEY,
    ASR_RESOURCE_ID,
    LOG_LEVEL,
    LOG_DIR,
    LOG_JSON_FORMAT,
)
from src.logger import setup_logger

logger = setup_logger(
    name="newbot.asr",
    level=LOG_LEVEL,
    log_file="asr.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"


@dataclass
class SpeakerSegment:
    """说话人片段"""

    speaker_id: str  # ASR 返回的说话人 ID
    text: str  # 该说话人的文本
    start_time: int  # 开始时间（毫秒）
    end_time: int  # 结束时间（毫秒）


@dataclass
class ASRResult:
    """ASR 识别结果"""

    text: str  # 完整文本
    utterances: list[SpeakerSegment]  # 各说话人片段


class VolcanoASR:
    """火山引擎 ASR 客户端"""

    def __init__(
        self,
        app_key: str = ASR_APP_KEY,
        access_key: str = ASR_ACCESS_KEY,
        resource_id: str = ASR_RESOURCE_ID,
    ):
        self.app_key = app_key
        self.access_key = access_key
        self.resource_id = resource_id

    def _get_headers(self, sequence: int = -1) -> dict:
        """生成请求头"""
        request_id = str(uuid.uuid4())
        date_str = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())

        # 签名计算
        signature_str = f"x-date:{date_str}\n"
        signature = hmac.new(
            self.access_key.encode("utf-8"),
            signature_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        authorization = (
            f'hmac username="{self.app_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="x-date", '
            f'signature="{signature}"'
        )

        return {
            "X-Api-App-Key": self.app_key,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": str(sequence),
            "Authorization": authorization,
            "Content-Type": "application/json",
            "X-Date": date_str,
        }

    def submit(self, audio_url: str, enable_speaker: bool = True) -> str:
        """
        提交 ASR 任务

        Args:
            audio_url: 音频文件 URL
            enable_speaker: 是否开启说话人识别

        Returns:
            任务 ID
        """
        payload = {
            "app": {
                "appid": self.app_key,
                "cluster": "volc_tts",
                "token": "access_token",
            },
            "user": {"uid": "default_user"},
            "audio": {
                "url": audio_url,
                "format": "wav",
                "sample_rate": 16000,
                "bits": 16,
                "channel": 1,
                "language": "zh-CN",
            },
            "request": {
                "model_name": "bigmodel",
                "enable_speaker_info": enable_speaker,
                "result_type": "single",
            },
        }

        headers = self._get_headers(sequence=-1)
        response = requests.post(SUBMIT_URL, headers=headers, json=payload)

        if response.status_code != 200:
            logger.error(f"ASR 提交失败: {response.status_code} - {response.text}")
            raise Exception(f"ASR 提交失败: {response.text}")

        result = response.json()
        if result.get("status_code") != 0:
            logger.error(f"ASR 任务提交错误: {result}")
            raise Exception(f"ASR 任务提交错误: {result.get('status_msg', '未知错误')}")

        task_id = result["result"]["task_id"]
        logger.info(f"ASR 任务已提交: task_id={task_id}")
        return task_id

    def query(self, task_id: str) -> dict:
        """
        查询 ASR 任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务结果
        """
        headers = self._get_headers(sequence=1)
        params = {"task_id": task_id}

        response = requests.get(QUERY_URL, headers=headers, params=params)

        if response.status_code != 200:
            logger.error(f"ASR 查询失败: {response.status_code} - {response.text}")
            raise Exception(f"ASR 查询失败: {response.text}")

        return response.json()

    def recognize(self, audio_url: str, enable_speaker: bool = True, timeout: int = 300) -> ASRResult:
        """
        识别音频（提交 + 轮询）

        Args:
            audio_url: 音频文件 URL
            enable_speaker: 是否开启说话人识别
            timeout: 超时时间（秒）

        Returns:
            ASR 识别结果
        """
        task_id = self.submit(audio_url, enable_speaker)

        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.query(task_id)
            status_code = result.get("status_code", -1)

            if status_code == 0:
                # 任务完成
                return self._parse_result(result)
            elif status_code == 1:
                # 任务进行中
                logger.debug(f"ASR 任务进行中: task_id={task_id}")
                time.sleep(2)
            else:
                # 任务失败
                logger.error(f"ASR 任务失败: {result}")
                raise Exception(f"ASR 任务失败: {result.get('status_msg', '未知错误')}")

        raise TimeoutError(f"ASR 任务超时: task_id={task_id}")

    def _parse_result(self, result: dict) -> ASRResult:
        """解析 ASR 结果"""
        utterances = []
        full_text = ""

        if "result" in result and "text" in result["result"]:
            full_text = result["result"]["text"]

            # 解析说话人信息
            if "utterances" in result["result"]:
                for utt in result["result"]["utterances"]:
                    segment = SpeakerSegment(
                        speaker_id=utt.get("speaker_id", "unknown"),
                        text=utt.get("text", ""),
                        start_time=utt.get("start_time", 0),
                        end_time=utt.get("end_time", 0),
                    )
                    utterances.append(segment)

        logger.info(f"ASR 识别完成: text_len={len(full_text)}, segments={len(utterances)}")
        return ASRResult(text=full_text, utterances=utterances)


def transcribe_audio(audio_url: str, enable_speaker: bool = True) -> ASRResult:
    """
    便捷函数：转录音频

    Args:
        audio_url: 音频文件 URL
        enable_speaker: 是否开启说话人识别

    Returns:
        ASR 识别结果
    """
    client = VolcanoASR()
    return client.recognize(audio_url, enable_speaker)
