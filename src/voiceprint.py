"""讯飞声纹识别服务"""
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Optional
import requests
from dataclasses import dataclass
from src.logger import setup_logger
from src.config import (
    XFYUN_API_KEY, XFYUN_API_SECRET, XFYUN_VOICEPRINT_URL,
    XFYUN_VOICEPRINT_GROUP_ID, XFYUN_VOICEPRINT_THRESHOLD,
    LOG_LEVEL, LOG_DIR, LOG_JSON_FORMAT
)

logger = setup_logger(
    name="newbot.voiceprint",
    level=LOG_LEVEL,
    log_file="voiceprint.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)


@dataclass
class VoiceprintResult:
    """声纹识别结果"""
    feature_id: str  # 声纹特征 ID
    is_new: bool  # 是否为新创建的声纹
    score: float  # 匹配分数 (如果是匹配到的)


class XunfeiVoiceprint:
    """讯飞声纹识别客户端"""
    
    def __init__(
        self,
        api_key: str = XFYUN_API_KEY,
        api_secret: str = XFYUN_API_SECRET,
        base_url: str = XFYUN_VOICEPRINT_URL,
        group_id: str = XFYUN_VOICEPRINT_GROUP_ID,
        threshold: int = XFYUN_VOICEPRINT_THRESHOLD,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.group_id = group_id
        self.threshold = threshold
        
    def _get_auth_url(self) -> str:
        """生成鉴权 URL"""
        # RFC1123 格式时间
        now = datetime.utcnow()
        date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
        
        # 签名原文: host + date + request-line
        signature_origin = f"host: api.xf-yun.com\ndate: {date}\nGET /v1/private/s1aa729d0 HTTP/1.1"
        
        # HMAC-SHA256 签名
        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            hashlib.sha256
        ).digest()
        
        signature = base64.b64encode(signature_sha).decode("utf-8")
        
        # authorization
        authorization_origin = f'api_key="{self.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        
        # 最终 URL
        url = f"{self.base_url}?authorization={authorization}&date={date}&host=api.xf-yun.com"
        return url
    
    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
        }
    
    def create_group(self, group_name: str = None) -> Optional[str]:
        """
        创建声纹库
        
        Args:
            group_name: 声纹库名称
            
        Returns:
            声纹库 ID 或 None
        """
        if group_name is None:
            group_name = self.group_id
            
        url = self._get_auth_url()
        payload = {
            "header": {
                "app_id": self.api_key,
                "status": 3,  # 一次性传输完成
            },
            "parameter": {
                "s1aa729d0": {
                    "groupId": group_name,
                }
            },
            "payload": {}
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            result = response.json()
            
            if result.get("header", {}).get("code") == 0:
                logger.info(f"声纹库创建成功: group_id={group_name}")
                return group_name
            else:
                logger.error(f"声纹库创建失败: {result}")
                return None
                
        except Exception as e:
            logger.error(f"声纹库创建异常: {e}", exc_info=True)
            return None
    
    def create_feature(self, audio_base64: str, feature_id: str = None) -> Optional[str]:
        """
        创建声纹特征
        
        Args:
            audio_base64: base64 编码的音频数据 (16k, 16bit, mono wav)
            feature_id: 自定义特征 ID，不指定则自动生成
            
        Returns:
            特征 ID 或 None
        """
        import uuid
        if feature_id is None:
            feature_id = f"spk_{uuid.uuid4().hex[:12]}"
            
        url = self._get_auth_url()
        payload = {
            "header": {
                "app_id": self.api_key,
                "status": 3,
            },
            "parameter": {
                "s1aa729d0": {
                    "groupId": self.group_id,
                    "featureId": feature_id,
                }
            },
            "payload": {
                "audio": audio_base64
            }
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            result = response.json()
            
            if result.get("header", {}).get("code") == 0:
                logger.info(f"声纹特征创建成功: feature_id={feature_id}")
                return feature_id
            else:
                logger.error(f"声纹特征创建失败: {result}")
                return None
                
        except Exception as e:
            logger.error(f"声纹特征创建异常: {e}", exc_info=True)
            return None
    
    def search(self, audio_base64: str, top_k: int = 1) -> Optional[list]:
        """
        声纹 1:N 检索
        
        Args:
            audio_base64: base64 编码的音频数据
            top_k: 返回前 K 个匹配结果
            
        Returns:
            匹配结果列表 [{"featureId": str, "score": float}, ...]
        """
        url = self._get_auth_url()
        payload = {
            "header": {
                "app_id": self.api_key,
                "status": 3,
            },
            "parameter": {
                "s1aa729d0": {
                    "groupId": self.group_id,
                    "topK": top_k,
                }
            },
            "payload": {
                "audio": audio_base64
            }
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            result = response.json()
            
            if result.get("header", {}).get("code") == 0:
                candidates = result.get("payload", {}).get("candidates", [])
                logger.info(f"声纹检索完成: 找到 {len(candidates)} 个候选")
                return candidates
            else:
                logger.error(f"声纹检索失败: {result}")
                return None
                
        except Exception as e:
            logger.error(f"声纹检索异常: {e}", exc_info=True)
            return None
    
    def identify_speaker(self, audio_base64: str) -> Optional[VoiceprintResult]:
        """
        识别说话人：先检索，若匹配则返回，否则创建新声纹
        
        Args:
            audio_base64: base64 编码的音频数据
            
        Returns:
            VoiceprintResult 或 None
        """
        # 1:N 检索
        candidates = self.search(audio_base64)
        
        if candidates and len(candidates) > 0:
            best_match = candidates[0]
            score = best_match.get("score", 0)
            feature_id = best_match.get("featureId", "")
            
            # 检查是否超过阈值
            if score >= self.threshold and feature_id:
                logger.info(f"声纹匹配成功: feature_id={feature_id}, score={score}")
                return VoiceprintResult(
                    feature_id=feature_id,
                    is_new=False,
                    score=score
                )
        
        # 未匹配，创建新声纹
        new_feature_id = self.create_feature(audio_base64)
        if new_feature_id:
            logger.info(f"创建新声纹: feature_id={new_feature_id}")
            return VoiceprintResult(
                feature_id=new_feature_id,
                is_new=True,
                score=0.0
            )
        
        return None


# 单例
voiceprint_client = XunfeiVoiceprint()
