# coding: utf-8
"""内置本地 STT provider。"""

from config_server import (
    ServerConfig as Config,
    ModelPaths,
    ParaformerArgs,
    Qwen3ASRGGUFArgs,
    SenseVoiceArgs,
    FunASRNanoGGUFArgs,
)
from util.fun_asr_gguf import create_asr_engine as create_fun_asr_engine
from util.qwen_asr_gguf import create_asr_engine as create_qwen_asr_engine
from util.server.server_recognize import recognize

from .. import logger
from .base import BaseSTTProvider


class LocalBuiltinProvider(BaseSTTProvider):
    """复用当前仓库已有的本地模型链路。"""

    name = 'local_builtin'

    def __init__(self):
        self.recognizer = None
        self.punc_model = None

    def load(self) -> None:
        model_type = Config.model_type.lower()

        if model_type == 'fun_asr_nano':
            logger.debug("使用 Fun-ASR-Nano 模型")
            self.recognizer = create_fun_asr_engine(
                **{
                    key: value
                    for key, value in FunASRNanoGGUFArgs.__dict__.items()
                    if not key.startswith('_')
                }
            )
            return

        if model_type == 'qwen_asr':
            logger.debug("使用 Qwen-ASR 模型")
            self.recognizer = create_qwen_asr_engine(
                **{
                    key: value
                    for key, value in Qwen3ASRGGUFArgs.__dict__.items()
                    if not key.startswith('_')
                }
            )
            return

        import sherpa_onnx

        if model_type == 'sensevoice':
            logger.debug("使用 SenseVoice 模型")
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                **{
                    key: value
                    for key, value in SenseVoiceArgs.__dict__.items()
                    if not key.startswith('_')
                }
            )
            return

        if model_type == 'paraformer':
            logger.debug("使用 Paraformer 模型")
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                **{
                    key: value
                    for key, value in ParaformerArgs.__dict__.items()
                    if not key.startswith('_')
                }
            )
            config = sherpa_onnx.OfflinePunctuationConfig(
                model=sherpa_onnx.OfflinePunctuationModelConfig(
                    ct_transformer=ModelPaths.punc_model_dir.as_posix()
                ),
            )
            self.punc_model = sherpa_onnx.OfflinePunctuation(config)
            return

        raise ValueError(
            f"不支持的模型类型: {Config.model_type}，"
            "请选择 'fun_asr_nano'、'qwen_asr'、'sensevoice' 或 'paraformer'"
        )

    def recognize(self, task):
        return recognize(self.recognizer, self.punc_model, task)
