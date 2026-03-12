# coding: utf-8
"""
CapsWriter STT Gateway 启动入口。

与 start_server.py 共用同一套核心逻辑，保留旧入口兼容性，
同时为后续的跨平台 gateway 形态提供更明确的命名。
"""

from multiprocessing import freeze_support
import sys

import core_server


if __name__ == '__main__':
    freeze_support()
    core_server.init()
    sys.exit(0)
