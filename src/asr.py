"""火山引擎 ASR 语音识别服务"""
import base64
import hashlib
import hmac
import io
import time
import uuid
import wave
import requests
from typing import Optional
from dataclasses import dataclass
from src.logger import setup_logger
from src.config import (
    ASR_APP_KEY, ASR_ACCESS_KEY, ASR_RESOURCE_ID,
    LOG_LEVEL, LOG_DIR, LOG_JSON_FORMAT
)

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
class Utterance:
    """单个说话片段"""
    text: str
    speaker_id: int
    start_time: int  # 毫秒
    end_time: int  # 毫秒


@dataclass
class ASRResult:
    """ASR 识别结果"""
    text: str  # 完整文本
    utterances: list[Utterance]  # 按说话人分段的片段列表


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
        
    def _get_headers(self, sequence: int = 1) -> dict:
        """生成请求头"""
        request_id = str(uuid.uuid4())
        timestamp = str(int(time.time()))
        
        # 签名: HMAC-SHA256(access_key, timestamp)
        signature = hmac.new(
            self.access_key.encode("utf-8"),
            timestamp.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "X-Api-App-Key": self.app_key,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": str(sequence),
            "X-Api-Signature": signature,
            "X-Api-Signature-Timestamp": timestamp,
            "Content-Type": "application/json",
        }
    
    def _ensure_wav_format(self, audio_base64: str) -> str:
        """
        确保音频是 WAV 格式
        
        Args:
            audio_base64: base64 编码的音频数据
            
        Returns:
            WAV 格式的 base64 编码音频
        """
        audio_data = base64.b64decode(audio_base64)
        
        # 已经是 WAV 格式
        if audio_data[:4] == b'RIFF':
            return audio_base64
        
        # 原始 PCM 数据，添加 WAV 头（16kHz, 16bit, mono）
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_data)
        
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    def submit(self, audio_base64: str, enable_speaker_info: bool = True) -> Optional[str]:
        """
        提交 ASR 任务
        
        Args:
            audio_base64: base64 编码的音频数据
            enable_speaker_info: 是否开启说话人识别
            
        Returns:
            任务 ID，失败返回 None
        """
        headers = self._get_headers(sequence=1)
        
        # 确保音频是 WAV 格式
        audio_base64 = self._ensure_wav_format(audio_base64)
        
        payload = {
            "audio": {
                "data": audio_base64,
            },
            "enable_speaker_info": enable_speaker_info,
        }
        
        try:
            response = requests.post(SUBMIT_URL, headers=headers, json=payload)
            result = response.json()
            
            if result.get("code") == 0:
                task_id = result.get("data", {}).get("task_id")
                logger.info(f"ASR 任务提交成功: task_id={task_id}")
                return task_id
            else:
                logger.error(f"ASR 任务提交失败: {result}")
                return None
                
        except Exception as e:
            logger.error(f"ASR 任务提交异常: {e}", exc_info=True)
            return None
    
    def query(self, task_id: str, max_retries: int = 30, interval: float = 2.0) -> Optional[dict]:
        """
        查询 ASR 任务结果
        
        Args:
            task_id: 任务 ID
            max_retries: 最大重试次数
            interval: 重试间隔（秒）
            
        Returns:
            识别结果，失败返回 None
        """
        headers = self._get_headers(sequence=-1)  # -1 表示查询
        
        for i in range(max_retries):
            try:
                response = requests.post(
                    QUERY_URL,
                    headers=headers,
                    json={"task_id": task_id}
                )
                result = response.json()
                
                if result.get("code") == 0:
                    status = result.get("data", {}).get("status")
                    
                    if status == 2:  # 识别完成
                        logger.info(f"ASR 任务完成: task_id={task_id}")
                        return result.get("data", {})
                    elif status == 1:  # 识别中
                        logger.debug(f"ASR 任务进行中 ({i+1}/{max_retries})")
                        time.sleep(interval)
                    else:
                        logger.error(f"ASR 任务状态异常: {result}")
                        return None
                else:
                    logger.error(f"ASR 查询失败: {result}")
                    return None
                    
            except Exception as e:
                logger.error(f"ASR 查询异常: {e}", exc_info=True)
                time.sleep(interval)
        
        logger.error(f"ASR 任务超时: task_id={task_id}")
        return None
    
    def recognize(self, audio_base64: str, enable_speaker_info: bool = True) -> Optional[ASRResult]:
        """
        执行语音识别（提交 + 查询）
        
        Args:
            audio_base64: base64 编码的音频数据
            enable_speaker_info: 是否开启说话人识别
            
        Returns:
            ASRResult 或 None
        """
        # 提交任务
        task_id = self.submit(audio_base64, enable_speaker_info)
        if not task_id:
            return None
        
        # 查询结果
        result = self.query(task_id)
        if not result:
            return None
        
        # 解析结果
        try:
            utterance_list = result.get("result", {}).get("utterances", [])
            utterances = []
            full_text = ""
            
            for u in utterance_list:
                text = u.get("text", "")
                speaker_id = u.get("speaker_id", 0)
                start_time = u.get("start_time", 0)
                end_time = u.get("end_time", 0)
                
                utterances.append(Utterance(
                    text=text,
                    speaker_id=speaker_id,
                    start_time=start_time,
                    end_time=end_time,
                ))
                full_text += text
            
            logger.info(f"ASR 识别完成: 共 {len(utterances)} 个片段")
            return ASRResult(text=full_text, utterances=utterances)
            
        except Exception as e:
            logger.error(f"解析 ASR 结果失败: {e}", exc_info=True)
            return None


# 单例
asr_client = VolcanoASR()
