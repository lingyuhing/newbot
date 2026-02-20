"""
日志配置模块

提供统一的日志配置，支持：
- 控制台和文件双输出
- 不同日志级别
- 结构化 JSON 格式（可选）
- 日志文件自动轮转
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import json
from typing import Optional


class JsonFormatter(logging.Formatter):
    """JSON 格式化器，用于结构化日志"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data
        
        return json.dumps(log_data, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """彩色控制台格式化器"""
    
    COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logger(
    name: str = "newbot",
    level: str = "INFO",
    log_file: Optional[str] = None,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    json_format: bool = False,
    console_output: bool = True,
) -> logging.Logger:
    """
    配置并返回日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件名（不含路径），None 则使用默认名称
        log_dir: 日志文件目录
        max_bytes: 单个日志文件最大字节数
        backup_count: 保留的日志文件数量
        json_format: 是否使用 JSON 格式
        console_output: 是否输出到控制台
    
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    
    # 避免重复配置
    if logger.handlers:
        return logger
    
    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # 日志格式
    if json_format:
        formatter = JsonFormatter()
    else:
        formatter = ColoredFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    # 文件处理器
    if log_file is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_path / log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str = "newbot") -> logging.Logger:
    """
    获取已配置的日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        日志记录器实例
    """
    return logging.getLogger(name)


# 创建子模块便捷函数
def log_request(logger: logging.Logger, client_id: str, message: str):
    """记录请求日志"""
    logger.info(
        f"[Request] client={client_id} | message={message[:100]}{'...' if len(message) > 100 else ''}"
    )


def log_response(logger: logging.Logger, client_id: str, tokens: int = 0):
    """记录响应日志"""
    logger.info(f"[Response] client={client_id} | tokens={tokens}")


def log_error(logger: logging.Logger, error: Exception, context: dict = None):
    """记录错误日志"""
    extra = {"extra_data": context} if context else {}
    logger.error(f"Error: {type(error).__name__}: {error}", extra=extra, exc_info=True)


def log_websocket(logger: logging.Logger, event: str, client_id: str, details: str = ""):
    """记录 WebSocket 事件日志"""
    logger.info(f"[WebSocket] {event} | client={client_id} | {details}")
