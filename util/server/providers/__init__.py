# coding: utf-8
"""STT provider 工厂。"""

from config_server import ServerConfig as Config


def create_provider():
    provider_type = Config.provider_type.lower()
    if provider_type == 'local_builtin':
        from .local_provider import LocalBuiltinProvider

        return LocalBuiltinProvider()
    if provider_type == 'remote_http':
        from .remote_http_provider import RemoteHTTPProvider

        return RemoteHTTPProvider()
    raise ValueError(
        f"不支持的 provider_type: {Config.provider_type}，"
        "请选择 'local_builtin' 或 'remote_http'"
    )


__all__ = [
    'create_provider',
]
