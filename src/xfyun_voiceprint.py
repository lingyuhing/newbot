# -*- coding: utf-8 -*-
"""
讯飞声纹管理模块

功能：
1. 声纹注册/更新/删除（HTTP API）
2. 声纹库 JSON 存储
3. 待注册说话人音频片段累积
4. 合并片段并自动注册

JSON 存储格式：
{
    "registered": {
        "feature_id": {
            "name": "speaker_20260224_100000",
            "created_at": "2026-02-24T10:00:00"
        }
    },
    "pending": {
        "pending_1": {
            "audio_segments": [
                {"file": "pending/pending_1_seg_1.wav", "duration_ms": 5000}
            ],
            "total_duration_ms": 5000,
            "created_at": "2026-02-24T10:00:00"
        }
    }
}
"""
import base64
import hmac
import json
import os
import time
import random
import string
import requests
import urllib.parse
import datetime
import wave
import io
import warnings
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from src.logger import setup_logger
from src.config import (
    LOG_LEVEL, LOG_DIR, LOG_JSON_FORMAT,
    XFYUN_ASR_APP_ID, XFYUN_ASR_ACCESS_KEY_ID, XFYUN_ASR_ACCESS_KEY_SECRET,
    VOICEPRINT_STORE_PATH
)

warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 讯飞声纹 API 配置
VOICEPRINT_HOST = "https://office-api-personal-dx.iflyaisol.com"
REGISTER_URL = "/res/feature/v1/register"
UPDATE_URL = "/res/feature/v1/update"
DELETE_URL = "/res/feature/v1/delete"

# 声纹注册最小音频时长（毫秒）
MIN_REGISTER_DURATION_MS = 10000  # 10秒

# 待注册片段存储目录
PENDING_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "voiceprint_pending")

logger = setup_logger(
    name="newbot.voiceprint",
    level=LOG_LEVEL,
    log_file="voiceprint.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)


@dataclass
class VoiceprintInfo:
    """已注册声纹信息"""
    feature_id: str
    name: str
    created_at: str


@dataclass
class PendingSpeaker:
    """待注册说话人"""
    pending_id: str
    audio_segments: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_ms: int = 0
    created_at: str = ""
    
    def add_segment(self, file_path: str, duration_ms: int):
        """添加音频片段"""
        self.audio_segments.append({
            "file": file_path,
            "duration_ms": duration_ms
        })
        self.total_duration_ms += duration_ms


class XfyunVoiceprintManager:
    """讯飞声纹管理器"""
    
    def __init__(
        self,
        app_id: str = None,
        access_key_id: str = None,
        access_key_secret: str = None,
        store_path: str = None
    ):
        self.app_id = app_id or XFYUN_ASR_APP_ID
        self.access_key_id = access_key_id or XFYUN_ASR_ACCESS_KEY_ID
        self.access_key_secret = access_key_secret or XFYUN_ASR_ACCESS_KEY_SECRET
        self.store_path = store_path or VOICEPRINT_STORE_PATH
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        os.makedirs(PENDING_DIR, exist_ok=True)
        
        # 加载存储数据
        self._store_data = self._load_store()
        
        # 随机字符串（用于签名）
        self._signature_random = self._generate_random_str()
        
        logger.info(f"声纹管理器初始化完成: store_path={self.store_path}")
    
    def _generate_random_str(self, length: int = 16) -> str:
        """生成随机字符串"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    
    def _get_local_time_with_tz(self) -> str:
        """生成带时区偏移的本地时间"""
        local_now = datetime.datetime.now()
        tz_offset = local_now.astimezone().strftime('%z')
        return f"{local_now.strftime('%Y-%m-%dT%H:%M:%S')}{tz_offset}"
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """生成签名"""
        # 排除 signature 参数，按参数名自然排序
        sign_params = {k: v for k, v in params.items() if k != "signature"}
        sorted_params = sorted(sign_params.items(), key=lambda x: x[0])
        
        # 构建签名字符串
        base_parts = []
        for k, v in sorted_params:
            if v is not None and str(v).strip() != "":
                encoded_key = urllib.parse.quote(k, safe='')
                encoded_value = urllib.parse.quote(str(v), safe='')
                base_parts.append(f"{encoded_key}={encoded_value}")
        
        base_str = "&".join(base_parts)
        
        # HMAC-SHA1 加密 + Base64 编码
        hmac_obj = hmac.new(
            self.access_key_secret.encode("utf-8"),
            base_str.encode("utf-8"),
            digestmod="sha1"
        )
        return base64.b64encode(hmac_obj.digest()).decode("utf-8")
    
    def _build_request_url(self, func_url: str, url_params: Dict[str, Any]) -> str:
        """构建请求 URL"""
        encoded_params = []
        for k, v in url_params.items():
            encoded_key = urllib.parse.quote(k, safe='')
            encoded_value = urllib.parse.quote(str(v), safe='')
            encoded_params.append(f"{encoded_key}={encoded_value}")
        return f"{VOICEPRINT_HOST}{func_url}?{'&'.join(encoded_params)}"
    
    def _load_store(self) -> Dict[str, Any]:
        """加载 JSON 存储"""
        if os.path.exists(self.store_path):
            try:
                with open(self.store_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.debug(f"加载声纹库: {len(data.get('registered', {}))} 已注册, {len(data.get('pending', {}))} 待处理")
                    return data
            except Exception as e:
                logger.error(f"加载声纹库失败: {e}")
        
        # 返回默认结构
        return {
            "registered": {},
            "pending": {}
        }
    
    def _save_store(self):
        """保存 JSON 存储"""
        try:
            with open(self.store_path, 'w', encoding='utf-8') as f:
                json.dump(self._store_data, f, ensure_ascii=False, indent=2)
            logger.debug("声纹库已保存")
        except Exception as e:
            logger.error(f"保存声纹库失败: {e}")
    
    # ==================== 声纹注册 API ====================
    
    def register_voiceprint(self, audio_base64: str, name: str = None) -> Optional[str]:
        """
        注册声纹
        
        Args:
            audio_base64: 音频的 base64 编码（PCM/WAV 格式）
            name: 声纹名称，不传则使用时间戳
            
        Returns:
            注册成功返回 feature_id，失败返回 None
        """
        try:
            # 生成名称
            if not name:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"speaker_{timestamp}"
            
            # 构建请求参数
            date_time = self._get_local_time_with_tz()
            self._signature_random = self._generate_random_str()
            
            url_params = {
                "appId": self.app_id,
                "accessKeyId": self.access_key_id,
                "dateTime": date_time,
                "signatureRandom": self._signature_random,
            }
            
            signature = self._generate_signature(url_params)
            
            headers = {
                "Content-Type": "application/json",
                "signature": signature,
            }
            
            url = self._build_request_url(REGISTER_URL, url_params)
            
            body = {
                "audio_data": audio_base64,
                "audio_type": "raw",  # PCM/WAV 格式
            }
            
            logger.info(f"开始注册声纹: name={name}")
            
            response = requests.post(
                url=url,
                headers=headers,
                json=body,
                timeout=60,
                verify=False
            )
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"注册响应: {result}")
            
            if result.get("code") == "000000":
                data = json.loads(result.get("data", "{}"))
                feature_id = data.get("feature_id")
                
                if feature_id:
                    # 保存到本地存储
                    self._store_data["registered"][feature_id] = {
                        "name": name,
                        "created_at": datetime.datetime.now().isoformat()
                    }
                    self._save_store()
                    
                    logger.info(f"声纹注册成功: feature_id={feature_id}, name={name}")
                    return feature_id
            else:
                logger.error(f"声纹注册失败: code={result.get('code')}, desc={result.get('desc')}")
                
        except Exception as e:
            logger.error(f"声纹注册异常: {e}", exc_info=True)
        
        return None
    
    def update_voiceprint(self, feature_id: str, audio_base64: str) -> bool:
        """
        更新声纹
        
        Args:
            feature_id: 声纹 ID
            audio_base64: 新音频的 base64 编码
            
        Returns:
            更新成功返回 True
        """
        try:
            date_time = self._get_local_time_with_tz()
            self._signature_random = self._generate_random_str()
            
            url_params = {
                "appId": self.app_id,
                "accessKeyId": self.access_key_id,
                "dateTime": date_time,
                "signatureRandom": self._signature_random,
            }
            
            signature = self._generate_signature(url_params)
            
            headers = {
                "Content-Type": "application/json",
                "signature": signature,
            }
            
            url = self._build_request_url(UPDATE_URL, url_params)
            
            body = {
                "audio_data": audio_base64,
                "audio_type": "raw",
                "feature_id": feature_id,
            }
            
            logger.info(f"开始更新声纹: feature_id={feature_id}")
            
            response = requests.post(
                url=url,
                headers=headers,
                json=body,
                timeout=60,
                verify=False
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("code") == "000000":
                logger.info(f"声纹更新成功: feature_id={feature_id}")
                return True
            else:
                logger.error(f"声纹更新失败: code={result.get('code')}, desc={result.get('desc')}")
                
        except Exception as e:
            logger.error(f"声纹更新异常: {e}", exc_info=True)
        
        return False
    
    def delete_voiceprint(self, feature_ids: List[str]) -> bool:
        """
        删除声纹
        
        Args:
            feature_ids: 要删除的声纹 ID 列表
            
        Returns:
            删除成功返回 True
        """
        try:
            date_time = self._get_local_time_with_tz()
            self._signature_random = self._generate_random_str()
            
            url_params = {
                "appId": self.app_id,
                "accessKeyId": self.access_key_id,
                "dateTime": date_time,
                "signatureRandom": self._signature_random,
            }
            
            signature = self._generate_signature(url_params)
            
            headers = {
                "Content-Type": "application/json",
                "signature": signature,
            }
            
            url = self._build_request_url(DELETE_URL, url_params)
            
            body = {
                "feature_ids": feature_ids,
            }
            
            logger.info(f"开始删除声纹: feature_ids={feature_ids}")
            
            response = requests.post(
                url=url,
                headers=headers,
                json=body,
                timeout=30,
                verify=False
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("code") == "000000":
                # 从本地存储删除
                for fid in feature_ids:
                    self._store_data["registered"].pop(fid, None)
                self._save_store()
                
                logger.info(f"声纹删除成功: feature_ids={feature_ids}")
                return True
            else:
                logger.error(f"声纹删除失败: code={result.get('code')}, desc={result.get('desc')}")
                
        except Exception as e:
            logger.error(f"声纹删除异常: {e}", exc_info=True)
        
        return False
    
    # ==================== 声纹库查询 ====================
    
    def get_feature_ids(self) -> str:
        """
        获取所有已注册声纹 ID（逗号分隔）
        
        Returns:
            声纹 ID 字符串，如 "id1,id2,id3"
        """
        feature_ids = list(self._store_data.get("registered", {}).keys())
        return ",".join(feature_ids)
    
    def get_registered_voiceprints(self) -> Dict[str, VoiceprintInfo]:
        """获取所有已注册声纹信息"""
        result = {}
        for fid, info in self._store_data.get("registered", {}).items():
            result[fid] = VoiceprintInfo(
                feature_id=fid,
                name=info.get("name", "unknown"),
                created_at=info.get("created_at", "")
            )
        return result
    
    # ==================== 待注册说话人管理 ====================
    
    def create_pending_speaker(self) -> str:
        """
        创建新的待注册说话人
        
        Returns:
            pending_id
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        pending_id = f"pending_{timestamp}"
        
        self._store_data["pending"][pending_id] = {
            "audio_segments": [],
            "total_duration_ms": 0,
            "created_at": datetime.datetime.now().isoformat()
        }
        self._save_store()
        
        logger.info(f"创建待注册说话人: pending_id={pending_id}")
        return pending_id
    
    def add_pending_segment(
        self,
        pending_id: str,
        audio_data: bytes,
        duration_ms: int
    ) -> bool:
        """
        添加待注册音频片段
        
        Args:
            pending_id: 待注册说话人 ID
            audio_data: 音频数据（PCM 格式）
            duration_ms: 片段时长（毫秒）
            
        Returns:
            成功返回 True
        """
        if pending_id not in self._store_data["pending"]:
            logger.error(f"待注册说话人不存在: pending_id={pending_id}")
            return False
        
        try:
            # 保存音频片段到文件
            seg_index = len(self._store_data["pending"][pending_id]["audio_segments"])
            seg_filename = f"{pending_id}_seg_{seg_index}.wav"
            seg_filepath = os.path.join(PENDING_DIR, seg_filename)
            
            # 写入 WAV 文件
            with wave.open(seg_filepath, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(audio_data)
            
            # 更新存储
            self._store_data["pending"][pending_id]["audio_segments"].append({
                "file": seg_filepath,
                "duration_ms": duration_ms
            })
            self._store_data["pending"][pending_id]["total_duration_ms"] += duration_ms
            self._save_store()
            
            logger.debug(f"添加待注册片段: pending_id={pending_id}, duration={duration_ms}ms, total={self._store_data['pending'][pending_id]['total_duration_ms']}ms")
            return True
            
        except Exception as e:
            logger.error(f"添加待注册片段失败: {e}", exc_info=True)
            return False
    
    def get_pending_total_duration(self, pending_id: str) -> int:
        """获取待注册说话人的累积时长（毫秒）"""
        pending = self._store_data.get("pending", {}).get(pending_id, {})
        return pending.get("total_duration_ms", 0)
    
    def merge_and_register(self, pending_id: str, name: str = None) -> Optional[str]:
        """
        合并所有片段并注册声纹
        
        Args:
            pending_id: 待注册说话人 ID
            name: 声纹名称，不传则使用 pending_id
            
        Returns:
            注册成功返回 feature_id，失败返回 None
        """
        pending = self._store_data.get("pending", {}).get(pending_id)
        if not pending:
            logger.error(f"待注册说话人不存在: pending_id={pending_id}")
            return None
        
        segments = pending.get("audio_segments", [])
        total_duration = pending.get("total_duration_ms", 0)
        
        if total_duration < MIN_REGISTER_DURATION_MS:
            logger.warning(f"累积时长不足: total={total_duration}ms, 需要>={MIN_REGISTER_DURATION_MS}ms")
            return None
        
        try:
            # 合并所有音频片段
            merged_audio = io.BytesIO()
            
            with wave.open(merged_audio, 'wb') as merged_wav:
                merged_wav.setnchannels(1)
                merged_wav.setsampwidth(2)
                merged_wav.setframerate(16000)
                
                for seg in segments:
                    seg_path = seg["file"]
                    if os.path.exists(seg_path):
                        with wave.open(seg_path, 'rb') as seg_wav:
                            merged_wav.writeframes(seg_wav.readframes(seg_wav.getnframes()))
            
            # 转换为 base64
            merged_audio.seek(0)
            audio_base64 = base64.b64encode(merged_audio.read()).decode("utf-8")
            
            # 注册声纹
            if not name:
                name = pending_id.replace("pending_", "speaker_")
            
            feature_id = self.register_voiceprint(audio_base64, name=name)
            
            if feature_id:
                # 清理待注册数据
                self._cleanup_pending(pending_id)
                
            return feature_id
            
        except Exception as e:
            logger.error(f"合并注册失败: {e}", exc_info=True)
            return None
    
    def _cleanup_pending(self, pending_id: str):
        """清理待注册说话人的数据"""
        pending = self._store_data.get("pending", {}).get(pending_id, {})
        
        # 删除音频片段文件
        for seg in pending.get("audio_segments", []):
            seg_path = seg.get("file")
            if seg_path and os.path.exists(seg_path):
                try:
                    os.remove(seg_path)
                except Exception as e:
                    logger.warning(f"删除片段文件失败: {seg_path}, {e}")
        
        # 从存储中删除
        self._store_data["pending"].pop(pending_id, None)
        self._save_store()
        
        logger.info(f"清理待注册数据: pending_id={pending_id}")


# 全局单例
voiceprint_manager = XfyunVoiceprintManager()
