# coding: utf-8
"""STT provider 抽象基类。"""

from abc import ABC, abstractmethod

from util.server.server_classes import Result, Task


class BaseSTTProvider(ABC):
    """所有 STT provider 的统一接口。"""

    name = 'base'

    def load(self) -> None:
        """加载模型或初始化远端连接。"""

    @abstractmethod
    def recognize(self, task: Task) -> Result:
        """处理单个音频片段并返回聚合后的 Result。"""

    def close(self) -> None:
        """释放 provider 资源。"""
