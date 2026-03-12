# coding: utf-8
"""本地模型片段识别模块。"""

import numpy as np

from . import logger
from util.server.result_builder import SegmentRecognition, apply_segment_result
from util.server.server_classes import Task


def recognize(recognizer, punc_model, task: Task):
    """用本地模型识别单个片段，再交给结果聚合器。"""
    try:
        samples = np.frombuffer(task.data, dtype=np.float32)

        logger.debug(
            f"识别片段: task={task.task_id[:8]}, duration={len(samples) / task.samplerate:.2f}s, "
            f"offset={task.offset:.2f}s, is_final={task.is_final}"
        )

        stream = recognizer.create_stream()
        stream.accept_waveform(task.samplerate, samples)

        try:
            recognizer.decode_stream(stream, context=task.context)
        except TypeError:
            recognizer.decode_stream(stream)

        segment = SegmentRecognition(
            text=stream.result.text,
            tokens=list(getattr(stream.result, 'tokens', []) or []),
            timestamps=list(getattr(stream.result, 'timestamps', []) or []),
        )
        return apply_segment_result(task, segment, punc_model=punc_model)

    except Exception as e:
        logger.error(f"识别错误: {e}", exc_info=True)
        raise


def clear_results_by_socket_id(socket_id: str) -> None:
    """兼容旧导入路径。"""
    from util.server.result_builder import clear_results_by_socket_id as _clear

    _clear(socket_id)
