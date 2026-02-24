# -*- coding: utf-8 -*-
"""
讯飞实时语音转写大模型客户端

功能：
1. WebSocket 实时语音转写
2. 支持声纹分离模式
3. 返回结构化的转写结果

音频格式要求：
- 采样率：16kHz
- 位深：16bit
- 声道：单声道
- 格式：PCM

发送节奏：每 40ms 发送 1280 字节
"""
import base64
import hashlib
import hmac
import json
import time
import threading
import urllib.parse
import uuid
import datetime
from typing import Optional, List, Dict, Set
from dataclasses import dataclass, field
from websocket import create_connection, WebSocketException
import websocket

from src.logger import setup_logger
from src.config import (
    LOG_LEVEL, LOG_DIR, LOG_JSON_FORMAT,
    XFYUN_ASR_APP_ID, XFYUN_ASR_ACCESS_KEY_ID, XFYUN_ASR_ACCESS_KEY_SECRET,
    ASR_LANGUAGE, ASR_ROLE_TYPE
)

# 固定参数
FIXED_PARAMS = {
    "audio_encode": "pcm_s16le",
    "lang": ASR_LANGUAGE,  # autodialect / autominor
    "samplerate": "16000"
}

# 音频帧参数
AUDIO_FRAME_SIZE = 1280  # 每帧字节数（16k 采样率、16bit、40ms）
FRAME_INTERVAL_MS = 40   # 发送间隔（毫秒）

# WebSocket 地址
WS_URL = "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1"

logger = setup_logger(
    name="newbot.rtasr",
    level=LOG_LEVEL,
    log_file="rtasr.log",
    log_dir=LOG_DIR,
    json_format=LOG_JSON_FORMAT,
)


@dataclass
class Utterance:
    """语音片段"""
    text: str                    # 识别文本
    speaker_id: int              # 说话人编号 (rl)
    feature_id: str = ""         # 声纹ID（匹配成功时有值）
    start_time: int = 0          # 开始时间（毫秒）
    end_time: int = 0            # 结束时间（毫秒）
    
    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "speaker_id": self.speaker_id,
            "feature_id": self.feature_id,
            "start_time": self.start_time,
            "end_time": self.end_time
        }


@dataclass
class RTASRResult:
    """转写结果"""
    text: str                                # 完整文本
    utterances: List[Utterance] = field(default_factory=list)  # 分段列表
    unknown_speaker_ids: Set[int] = field(default_factory=set) # 未匹配的说话人编号
    
    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "utterances": [u.to_dict() for u in self.utterances],
            "unknown_speaker_ids": list(self.unknown_speaker_ids)
        }


class XfyunRTASRClient:
    """讯飞实时语音转写客户端"""
    
    def __init__(
        self,
        app_id: str = None,
        access_key_id: str = None,
        access_key_secret: str = None
    ):
        self.app_id = app_id or XFYUN_ASR_APP_ID
        self.access_key_id = access_key_id or XFYUN_ASR_ACCESS_KEY_ID
        self.access_key_secret = access_key_secret or XFYUN_ASR_ACCESS_KEY_SECRET
        
        self.ws = None
        self.is_connected = False
        self.session_id = None
        
        # 结果收集
        self._result_lock = threading.Lock()
        self._utterances: List[Dict] = []
        self._current_utterance: Dict = {}
        self._speaker_feature_map: Dict[int, str] = {}  # speaker_id -> feature_id
        self._is_finished = False
        
        # 接收线程
        self._recv_thread = None
        
        logger.info(f"RTASR 客户端初始化: app_id={self.app_id}")
    
    def _get_utc_time(self) -> str:
        """生成 UTC 时间格式"""
        beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
        now = datetime.datetime.now(beijing_tz)
        return now.strftime("%Y-%m-%dT%H:%M:%S%z")
    
    def _generate_auth_params(
        self,
        feature_ids: str = "",
        role_type: int = 2,
        eng_spk_match: int = 0
    ) -> Dict[str, str]:
        """生成鉴权参数"""
        auth_params = {
            "accessKeyId": self.access_key_id,
            "appId": self.app_id,
            "uuid": uuid.uuid4().hex,
            "utc": self._get_utc_time(),
            **FIXED_PARAMS
        }
        
        # 声纹分离模式
        if role_type > 0:
            auth_params["role_type"] = str(role_type)
        
        # 声纹 ID 列表
        if feature_ids:
            auth_params["feature_ids"] = feature_ids
            auth_params["eng_spk_match"] = str(eng_spk_match)
        
        # 计算签名
        sorted_params = dict(sorted([
            (k, v) for k, v in auth_params.items()
            if v is not None and str(v).strip() != ""
        ]))
        
        base_str = "&".join([
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted_params.items()
        ])
        
        signature = hmac.new(
            self.access_key_secret.encode("utf-8"),
            base_str.encode("utf-8"),
            hashlib.sha1
        ).digest()
        
        auth_params["signature"] = base64.b64encode(signature).decode("utf-8")
        return auth_params
    
    def _connect(
        self,
        feature_ids: str = "",
        role_type: int = 2,
        eng_spk_match: int = 0
    ) -> bool:
        """建立 WebSocket 连接"""
        try:
            auth_params = self._generate_auth_params(
                feature_ids=feature_ids,
                role_type=role_type,
                eng_spk_match=eng_spk_match
            )
            params_str = urllib.parse.urlencode(auth_params)
            full_url = f"{WS_URL}?{params_str}"
            
            logger.debug(f"WebSocket 连接 URL: {full_url}")
            
            self.ws = create_connection(
                full_url,
                timeout=15,
                enable_multithread=True
            )
            self.is_connected = True
            
            # 启动接收线程
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            
            # 等待连接就绪
            time.sleep(0.5)
            
            logger.info("WebSocket 连接成功")
            return True
            
        except WebSocketException as e:
            logger.error(f"WebSocket 连接失败: {e}")
            return False
        except Exception as e:
            logger.error(f"连接异常: {e}", exc_info=True)
            return False
    
    def _recv_loop(self):
        """接收消息循环"""
        while self.is_connected and self.ws:
            try:
                msg = self.ws.recv()
                if not msg:
                    logger.debug("服务端关闭连接")
                    break
                
                if isinstance(msg, str):
                    self._handle_message(msg)
                    
            except WebSocketException as e:
                logger.error(f"接收异常: {e}")
                break
            except Exception as e:
                logger.error(f"接收错误: {e}", exc_info=True)
                break
        
        self.is_connected = False
    
    def _handle_message(self, msg: str):
        """处理服务端消息"""
        try:
            data = json.loads(msg)
            msg_type = data.get("msg_type")
            
            if msg_type == "action":
                # 握手成功
                self.session_id = data.get("data", {}).get("sessionId")
                logger.debug(f"握手成功: sessionId={self.session_id}")
                
            elif msg_type == "result":
                res_type = data.get("res_type")
                
                if res_type == "asr":
                    self._handle_asr_result(data)
                elif res_type == "frc":
                    # 功能异常
                    desc = data.get("data", {}).get("desc", "未知错误")
                    logger.error(f"转写异常: {desc}")
                    
        except json.JSONDecodeError:
            logger.warning(f"非 JSON 消息: {msg[:100]}")
        except Exception as e:
            logger.error(f"消息处理错误: {e}", exc_info=True)
    
    def _handle_asr_result(self, data: dict):
        """处理 ASR 转写结果"""
        try:
            result_data = data.get("data", {})
            is_last = result_data.get("ls", False)
            
            cn_data = result_data.get("cn", {})
            st_data = cn_data.get("st", {})
            
            # 结果类型：0=最终结果，1=中间结果
            result_type = int(st_data.get("type", "1"))
            
            if result_type == 0:
                # 最终结果
                utterance = self._parse_utterance(st_data)
                if utterance:
                    with self._result_lock:
                        self._utterances.append(utterance)
                    logger.debug(f"最终结果: {utterance['text']}")
            
            if is_last:
                with self._result_lock:
                    self._is_finished = True
                logger.info("转写完成")
                
        except Exception as e:
            logger.error(f"解析 ASR 结果错误: {e}", exc_info=True)
    
    def _parse_utterance(self, st_data: dict) -> Optional[dict]:
        """解析单个语音片段"""
        try:
            rt_list = st_data.get("rt", [])
            if not rt_list:
                return None
            
            # 句子时间
            bg = int(st_data.get("bg", 0))  # 开始时间
            ed = int(st_data.get("ed", 0))  # 结束时间
            
            text_parts = []
            current_speaker = 0
            feature_id = ""
            
            for rt in rt_list:
                ws_list = rt.get("ws", [])
                for ws in ws_list:
                    cw_list = ws.get("cw", [])
                    for cw in cw_list:
                        w = cw.get("w", "")
                        wp = cw.get("wp", "n")
                        rl = int(cw.get("rl", 0))
                        lg = cw.get("lg", "")
                        
                        # 跳过标点和分段标识
                        if wp in ("p", "g"):
                            text_parts.append(w)
                            continue
                        
                        # 角色切换
                        if rl > 0:
                            current_speaker = rl
                            # 检查是否有 feature_id（需要从服务端返回中解析）
                            # 注意：讯飞的转写大模型在声纹模式下会在结果中返回匹配的声纹信息
                        
                        text_parts.append(w)
            
            text = "".join(text_parts)
            if not text.strip():
                return None
            
            return {
                "text": text,
                "speaker_id": current_speaker,
                "start_time": bg,
                "end_time": ed,
                "feature_id": feature_id
            }
            
        except Exception as e:
            logger.error(f"解析片段错误: {e}")
            return None
    
    def _send_audio(self, audio_data: bytes) -> bool:
        """发送音频数据（按节奏发送）"""
        if not self.is_connected or not self.ws:
            logger.error("WebSocket 未连接")
            return False
        
        try:
            # 发送节奏控制
            total_frames = len(audio_data) // AUDIO_FRAME_SIZE
            remaining = len(audio_data) % AUDIO_FRAME_SIZE
            if remaining > 0:
                total_frames += 1
            
            start_time = time.time() * 1000
            
            for i in range(total_frames):
                # 计算理论发送时间
                expected_time = start_time + (i * FRAME_INTERVAL_MS)
                current_time = time.time() * 1000
                
                # 动态休眠
                sleep_time = expected_time - current_time
                if sleep_time > 0:
                    time.sleep(sleep_time / 1000)
                
                # 获取当前帧
                start_byte = i * AUDIO_FRAME_SIZE
                end_byte = start_byte + AUDIO_FRAME_SIZE
                chunk = audio_data[start_byte:end_byte]
                
                # 发送
                self.ws.send_binary(chunk)
            
            # 发送结束标记
            end_msg = {"end": True}
            if self.session_id:
                end_msg["sessionId"] = self.session_id
            self.ws.send(json.dumps(end_msg))
            
            logger.info(f"音频发送完成: {len(audio_data)} 字节, {total_frames} 帧")
            return True
            
        except Exception as e:
            logger.error(f"发送音频错误: {e}", exc_info=True)
            return False
    
    def _close(self):
        """关闭连接"""
        if self.ws and self.is_connected:
            try:
                self.ws.close(status=1000, reason="正常关闭")
            except Exception as e:
                logger.warning(f"关闭连接异常: {e}")
        
        self.is_connected = False
        self.ws = None
        logger.debug("连接已关闭")
    
    def transcribe(
        self,
        audio_base64: str,
        feature_ids: str = "",
        role_type: int = 2,
        eng_spk_match: int = 0,
        timeout: int = 300
    ) -> Optional[RTASRResult]:
        """
        执行语音转写
        
        Args:
            audio_base64: 音频的 base64 编码
            feature_ids: 已注册的声纹 ID（逗号分隔）
            role_type: 角色分离模式（0=关闭，2=声纹分离）
            eng_spk_match: 是否严格匹配声纹（0=允许未知，1=严格匹配）
            timeout: 超时时间（秒）
            
        Returns:
            转写结果，失败返回 None
        """
        # 重置状态
        with self._result_lock:
            self._utterances = []
            self._current_utterance = {}
            self._speaker_feature_map = {}
            self._is_finished = False
        
        try:
            # 解码音频
            audio_data = base64.b64decode(audio_base64)
            
            # 跳过 WAV 头
            if audio_data[:4] == b'RIFF':
                audio_data = audio_data[44:]
            
            logger.info(f"开始转写: 音频大小={len(audio_data)} 字节, feature_ids={feature_ids}")
            
            # 建立连接
            if not self._connect(
                feature_ids=feature_ids,
                role_type=role_type,
                eng_spk_match=eng_spk_match
            ):
                return None
            
            # 发送音频
            if not self._send_audio(audio_data):
                self._close()
                return None
            
            # 等待结果
            start_wait = time.time()
            while True:
                with self._result_lock:
                    if self._is_finished:
                        break
                
                if time.time() - start_wait > timeout:
                    logger.warning(f"转写超时: {timeout} 秒")
                    break
                
                time.sleep(0.1)
            
            # 构建结果
            result = self._build_result()
            
            self._close()
            return result
            
        except Exception as e:
            logger.error(f"转写异常: {e}", exc_info=True)
            self._close()
            return None
    
    def _build_result(self) -> RTASRResult:
        """构建转写结果"""
        with self._result_lock:
            # 合并相同说话人的相邻片段
            merged_utterances = []
            unknown_speakers = set()
            
            for u in self._utterances:
                if merged_utterances:
                    last = merged_utterances[-1]
                    # 如果是同一说话人且相邻，合并
                    if last.speaker_id == u["speaker_id"]:
                        last.text += u["text"]
                        last.end_time = u["end_time"]
                        continue
                
                utterance = Utterance(
                    text=u["text"],
                    speaker_id=u["speaker_id"],
                    feature_id=u.get("feature_id", ""),
                    start_time=u["start_time"],
                    end_time=u["end_time"]
                )
                merged_utterances.append(utterance)
                
                # 记录未匹配的说话人
                if not utterance.feature_id and utterance.speaker_id > 0:
                    unknown_speakers.add(utterance.speaker_id)
            
            # 构建完整文本
            full_text = "".join(u.text for u in merged_utterances)
            
            logger.info(f"转写完成: {len(merged_utterances)} 个片段, {len(unknown_speakers)} 个未知说话人")
            
            return RTASRResult(
                text=full_text,
                utterances=merged_utterances,
                unknown_speaker_ids=unknown_speakers
            )


# 全局单例
rtasr_client = XfyunRTASRClient()
