"""
讯飞声纹识别模块

支持功能：
- 创建声纹组 (createGroup)
- 创建声纹特征 (createFeature)
- 1:N 声纹检索 (searchFea)
- 1:1 声纹比对 (searchScoreFea)
"""

import base64
import hashlib
import hmac
import time
import json
import requests
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from src.config import (
    XFYUN_API_KEY,
    XFYUN_API_SECRET,
    XFYUN_VOICEPRINT_URL,
    XFYUN_VOICEPRINT_GROUP_ID,
    XFYUN_VOICEPRINT_THRESHOLD,
    LOG_LEVEL,
    LOG_DIR,
    LOG_JSON_FORMAT,
)
from src.logger import setup_logger

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
    score: float  # 匹配分数
    is_new: bool  # 是否为新声纹
    speaker_name: Optional[str] = None  # 说话人名称（如有）


class XunfeiVoiceprint:
    """讯飞声纹识别客户端"""

    def __init__(
        self,
        api_key: str = XFYUN_API_KEY,
        api_secret: str = XFYUN_API_SECRET,
        base_url: str = XFYUN_VOICEPRINT_URL,
        group_id: str = XFYUN_VOICEPRINT_GROUP_ID,
        threshold: float = XFYUN_VOICEPRINT_THRESHOLD,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.group_id = group_id
        self.threshold = threshold

    def _get_auth_headers(self) -> dict:
        """生成鉴权请求头"""
        # RFC1123 格式时间
        date_str = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        # 签名原串
        signature_origin = f"host: api.xf-yun.com\ndate: {date_str}\nGET /v1/private/s1aa729d0 HTTP/1.1"
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                signature_origin.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

        return {
            "Authorization": authorization,
            "Date": date_str,
            "Host": "api.xf-yun.com",
            "Content-Type": "application/json",
        }

    def _build_url(self, params: dict) -> str:
        """构建带签名的 URL"""
        # 时间戳
        ts = str(int(time.time()))
        # 签名
        base_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        sign = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                base_string.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        query = f"?{base_string}&signature={sign}"
        return f"{self.base_url}{query}"

    def create_group(self, group_name: str) -> str:
        """
        创建声纹组

        Args:
            group_name: 声纹组名称

        Returns:
            声纹组 ID
        """
        headers = self._get_auth_headers()
        payload = {
            "header": {"app_id": self.api_key, "status": 3},
            "parameter": {"s1aa729d0": {"groupId": self.group_id, "groupName": group_name}},
        }

        response = requests.post(
            f"{self.base_url}?action=createGroup",
            headers=headers,
            json=payload,
        )

        if response.status_code != 200:
            logger.error(f"创建声纹组失败: {response.status_code} - {response.text}")
            raise Exception(f"创建声纹组失败: {response.text}")

        result = response.json()
        if result.get("header", {}).get("code") != 0:
            logger.error(f"创建声纹组错误: {result}")
            raise Exception(f"创建声纹组错误: {result}")

        logger.info(f"声纹组已创建: group_id={self.group_id}")
        return self.group_id

    def create_feature(self, audio_base64: str, feature_id: Optional[str] = None) -> str:
        """
        创建声纹特征

        Args:
            audio_base64: Base64 编码的音频数据（16k, 16bit, mono wav）
            feature_id: 指定特征 ID，不指定则自动生成

        Returns:
            特征 ID
        """
        if feature_id is None:
            import uuid

            feature_id = str(uuid.uuid4())

        headers = self._get_auth_headers()
        payload = {
            "header": {"app_id": self.api_key, "status": 3},
            "parameter": {
                "s1aa729d0": {
                    "groupId": self.group_id,
                    "featureId": feature_id,
                    "audioType": "wav",
                }
            },
            "payload": {"audio": audio_base64},
        }

        response = requests.post(
            f"{self.base_url}?action=createFeature",
            headers=headers,
            json=payload,
        )

        if response.status_code != 200:
            logger.error(f"创建声纹特征失败: {response.status_code} - {response.text}")
            raise Exception(f"创建声纹特征失败: {response.text}")

        result = response.json()
        if result.get("header", {}).get("code") != 0:
            logger.error(f"创建声纹特征错误: {result}")
            raise Exception(f"创建声纹特征错误: {result}")

        logger.info(f"声纹特征已创建: feature_id={feature_id}")
        return feature_id

    def search_feature(self, audio_base64: str, top_k: int = 1) -> Optional[VoiceprintResult]:
        """
        1:N 声纹检索

        Args:
            audio_base64: Base64 编码的音频数据
            top_k: 返回前 K 个匹配结果

        Returns:
            最佳匹配结果，无匹配则返回 None
        """
        headers = self._get_auth_headers()
        payload = {
            "header": {"app_id": self.api_key, "status": 3},
            "parameter": {
                "s1aa729d0": {
                    "groupId": self.group_id,
                    "audioType": "wav",
                    "topK": top_k,
                }
            },
            "payload": {"audio": audio_base64},
        }

        response = requests.post(
            f"{self.base_url}?action=searchFea",
            headers=headers,
            json=payload,
        )

        if response.status_code != 200:
            logger.error(f"声纹检索失败: {response.status_code} - {response.text}")
            raise Exception(f"声纹检索失败: {response.text}")

        result = response.json()
        if result.get("header", {}).get("code") != 0:
            logger.error(f"声纹检索错误: {result}")
            raise Exception(f"声纹检索错误: {result}")

        # 解析结果
        payload = result.get("payload", {})
        if "features" not in payload or not payload["features"]:
            return None

        # 解码 features
        features_json = base64.b64decode(payload["features"]).decode("utf-8")
        features = json.loads(features_json)

        if not features:
            return None

        # 取最佳匹配
        best_match = features[0]
        feature_id = best_match.get("featureId", "")
        score = best_match.get("score", 0.0)

        logger.info(f"声纹检索结果: feature_id={feature_id}, score={score}")
        return VoiceprintResult(
            feature_id=feature_id,
            score=score,
            is_new=False,
        )

    def identify_or_create(self, audio_base64: str) -> VoiceprintResult:
        """
        识别声纹，如无匹配则创建新声纹

        Args:
            audio_base64: Base64 编码的音频数据

        Returns:
            声纹识别结果
        """
        # 先检索
        result = self.search_feature(audio_base64)

        if result is not None and result.score >= self.threshold:
            logger.info(f"声纹匹配成功: feature_id={result.feature_id}, score={result.score}")
            return result

        # 无匹配或分数低于阈值，创建新声纹
        logger.info(f"声纹无匹配，创建新声纹: score={result.score if result else 'N/A'}")
        new_feature_id = self.create_feature(audio_base64)

        return VoiceprintResult(
            feature_id=new_feature_id,
            score=0.0,
            is_new=True,
        )


def identify_speaker(audio_base64: str, threshold: float = XFYUN_VOICEPRINT_THRESHOLD) -> VoiceprintResult:
    """
    便捷函数：识别说话人

    Args:
        audio_base64: Base64 编码的音频数据
        threshold: 匹配阈值

    Returns:
        声纹识别结果
    """
    client = XunfeiVoiceprint(threshold=threshold)
    return client.identify_or_create(audio_base64)
