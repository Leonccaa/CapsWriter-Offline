# coding: utf-8


"""
这个文件仅仅是为了 PyInstaller 打包用
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

import typer


def _write_bootstrap_log(error_text: str) -> str | None:
    """在核心模块导入前失败时，尽量把错误落盘到 logs 目录。"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(base_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(
            log_dir,
            f'bootstrap_client_{datetime.now().strftime("%Y%m%d")}.log'
        )
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"\n[{datetime.now().isoformat()}]\n")
            f.write(error_text)
            if not error_text.endswith('\n'):
                f.write('\n')
        return log_path
    except Exception:
        return None


def _pause_before_exit(message: str) -> None:
    """让双击启动的控制台不要一闪而过。"""
    print(message, file=sys.stderr)
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input('\n按回车退出...')
        except EOFError:
            pass


def _load_client_entrypoints():
    """延迟导入，确保 config_client 等导入错误能被捕获并显示。"""
    from core_client import init_file, init_mic
    return init_file, init_mic

if __name__ == "__main__":
    try:
        init_file, init_mic = _load_client_entrypoints()

        # 如果参数传入文件，那就转录文件
        # 如果没有多余参数，就从麦克风输入
        if sys.argv[1:]:
            typer.run(init_file)
        else:
            init_mic()
    except Exception:
        error_text = traceback.format_exc()
        log_path = _write_bootstrap_log(error_text)
        message = (
            "CapsWriter 客户端在启动早期失败。\n"
            "这通常是 config_client.py 或其它顶层导入文件存在语法/编码问题。\n\n"
            f"{error_text}"
        )
        if log_path:
            message += f"\n引导期错误日志已写入: {log_path}"
        _pause_before_exit(message)
        raise
