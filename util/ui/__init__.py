"""UI 工具模块。"""

import importlib
import logging

# ============================================================
# Logger 代理机制
# ============================================================

class _LoggerProxy:
    """
    日志代理类（利用 __getattr__ 动态转发）
    允许先导入 logger 对象，稍后再注入真正的实现。
    """
    def __init__(self):
        self._target = logging.getLogger('util.ui')  # 默认 logger

    def set_target(self, logger):
        """注入真正的 logger 实现"""
        self._target = logger

    def __getattr__(self, name):
        """将所有属性访问转发给真正的 logger"""
        return getattr(self._target, name)

# 1. 创建代理实例
logger = _LoggerProxy()

def set_ui_logger(real_logger):
    """设置 UI 模块使用的日志记录器"""
    logger.set_target(real_logger)

_LAZY_EXPORTS = {
    'toast': ('.toast', 'toast'),
    'toast_stream': ('.toast', 'toast_stream'),
    'ToastMessage': ('.toast', 'ToastMessage'),
    'ToastMessageManager': ('.toast', 'ToastMessageManager'),
    'enable_min_to_tray': ('.tray', 'enable_min_to_tray'),
    'stop_tray': ('.tray', 'stop_tray'),
}


def __getattr__(name):
    """按需加载 UI 组件，避免服务端被 GUI 依赖拖起。"""
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_name, __name__)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'logger',
    'set_ui_logger',
    *_LAZY_EXPORTS.keys(),
]
