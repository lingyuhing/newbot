#!/usr/bin/env python3
"""
WebSocket 客户端，支持 WebRTC VAD 语音活动检测
自动检测语音段，静音后自动发送音频
"""

import asyncio
import json
import base64
import time
import uuid
from collections import deque

import numpy as np
import pyaudio
import webrtcvad
import websockets

# ============ 配置 ============
SERVER_URL = "ws://127.0.0.1:8000/ws"
CLIENT_ID = f"client_{uuid.uuid4().hex[:8]}"

# 音频输入设备 (None=默认，或指定设备索引如 0)
AUDIO_DEVICE_INDEX = None  # 设为 0 使用 HDA Intel PCH

# 音频配置
SAMPLE_RATE = 16000  # 采样率 (WebRTC VAD 支持 8k/16k/32k)
CHANNELS = 1         # 单声道
FRAME_DURATION_MS = 30  # 帧时长 (WebRTC VAD 支持 10/20/30ms)
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 每帧采样数
BYTES_PER_SAMPLE = 2  # 16bit = 2 bytes
FRAME_BYTES = FRAME_SIZE * CHANNELS * BYTES_PER_SAMPLE

# VAD 配置
VAD_AGGRESSIVENESS = 0  # 0-3, 越大越激进过滤非语音
SILENCE_THRESHOLD_MS = 5000  # 静音阈值，超过此时间认为说话结束
MIN_SPEECH_DURATION_MS = 500  # 最小语音时长，过短的忽略


class VADAudioClient:
    def __init__(self):
        self.vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        self.audio = pyaudio.PyAudio()
        
        # 音频缓冲区
        self.audio_buffer = deque()
        self.speech_frames = []
        
        # 状态
        self.is_speaking = False
        self.last_speech_time = 0
        self.speech_start_time = 0
        
    def list_audio_devices(self):
        """列出所有音频设备"""
        print("\n可用音频输入设备:")
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  [{i}] {info['name']} (输入通道: {info['maxInputChannels']})")
        print()
        
    def is_speech(self, frame: bytes) -> bool:
        """检测帧是否包含语音"""
        return self.vad.is_speech(frame, SAMPLE_RATE)
    
    def process_audio(self, websocket):
        """主音频处理循环"""
        stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=AUDIO_DEVICE_INDEX,
            frames_per_buffer=FRAME_SIZE,
        )
        
        print(f"麦克风已开启，采样率: {SAMPLE_RATE}Hz, VAD 模式: {VAD_AGGRESSIVENESS}")
        print("开始监听... (说话后自动发送，按 Ctrl+C 退出)\n")
        
        silence_frame_count = 0
        silence_frames_needed = SILENCE_THRESHOLD_MS // FRAME_DURATION_MS
        min_speech_frames = MIN_SPEECH_DURATION_MS // FRAME_DURATION_MS
        
        try:
            while True:
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
                is_speech = self.is_speech(frame)
                current_time = time.time()
                
                if is_speech:
                    if not self.is_speaking:
                        # 开始说话
                        self.is_speaking = True
                        self.speech_start_time = current_time
                        self.speech_frames = []
                        print("🎙️ 检测到语音开始...")
                    
                    self.speech_frames.append(frame)
                    self.last_speech_time = current_time
                    silence_frame_count = 0
                else:
                    if self.is_speaking:
                        silence_frame_count += 1
                        # 静音期间也收集帧（防止切断尾音）
                        self.speech_frames.append(frame)
                        
                        # 检查是否超过静音阈值
                        if silence_frame_count >= silence_frames_needed:
                            self.is_speaking = False
                            speech_duration = (current_time - self.speech_start_time) * 1000
                            
                            # 移除尾部静音帧
                            actual_speech_frames = len(self.speech_frames) - silence_frame_count
                            
                            if actual_speech_frames >= min_speech_frames:
                                print(f"✅ 语音结束，时长: {speech_duration:.0f}ms，发送中...")
                                # 发送音频
                                audio_data = b''.join(self.speech_frames[:-silence_frame_count])
                                asyncio.run(self.send_audio(websocket, audio_data))
                            else:
                                print(f"⏭️ 语音过短 ({speech_duration:.0f}ms)，忽略")
                            
                            self.speech_frames = []
                            silence_frame_count = 0
        finally:
            stream.stop_stream()
            stream.close()
    
    async def send_audio(self, websocket, audio_data: bytes):
        """发送音频到服务器"""
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        message = {
            "multimodal": [
                {"type": "text", "text": "[用户发送了音频消息]"}
            ],
            "audio": audio_base64
        }
        
        try:
            await websocket.send(json.dumps(message))
            print("📤 音频已发送，等待响应...\n")
        except Exception as e:
            print(f"❌ 发送失败: {e}")
    
    async def receive_messages(self, websocket):
        """接收服务器消息"""
        try:
            async for message in websocket:
                # 流式接收，直接打印
                print(message, end='', flush=True)
        except websockets.exceptions.ConnectionClosed:
            print("\n连接已关闭")
    
    async def run(self):
        """主运行函数"""
        uri = f"{SERVER_URL}/{CLIENT_ID}"
        print(f"连接到: {uri}")
        
        try:
            async with websockets.connect(uri) as websocket:
                print("✅ WebSocket 已连接\n")
                
                # 启动接收任务
                receive_task = asyncio.create_task(self.receive_messages(websocket))
                
                # 在线程中运行音频处理
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.process_audio, websocket)
                
                receive_task.cancel()
                
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"连接被拒绝或关闭: {e}")
        except KeyboardInterrupt:
            print("\n\n用户中断，退出...")
        finally:
            self.audio.terminate()


def main():
    print("=" * 50)
    print("WebSocket VAD 音频客户端")
    print("=" * 50)
    
    client = VADAudioClient()
    client.list_audio_devices()
    
    asyncio.run(client.run())


if __name__ == "__main__":
    main()
