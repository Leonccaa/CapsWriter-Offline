# coding: utf-8
"""
服务端结果聚合模块

将每个音频片段的识别结果聚合成客户端可消费的 Result。
这一层与具体模型实现解耦，可供本地 provider 和远端 provider 共同使用。
"""

from dataclasses import dataclass, field
import re
import time
from typing import List

from config_server import ServerConfig as Config
from util.constants import AudioFormat
from util.server.server_classes import Result, Task
from util.server.text_merge import (
    merge_by_text,
    merge_tokens_by_sequence_matcher,
    process_tokens_safely,
    tokens_to_text,
)
from util.tools.chinese_itn import chinese_to_num
from util.tools.format_tools import adjust_space

from . import logger


@dataclass
class SegmentRecognition:
    """单个音频片段的识别结果。"""

    text: str = ''
    tokens: List[str] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)


_results: dict[str, Result] = {}


def format_text(text: str, punc_model) -> str:
    """对最终识别文本做统一格式整理。"""
    if text and Config.format_spell:
        text = adjust_space(text)
    if text and punc_model:
        text = punc_model.add_punctuation(text)
    if text and Config.format_num:
        text = chinese_to_num(text)
    return text


def _process_simple_merge(result: Result, segment_text: str) -> None:
    """维护 result.text 的简单文本拼接。"""
    try:
        segment_text = segment_text.replace('@@', '').strip()
        segment_text = re.sub(r'\s+', ' ', segment_text)

        prev_len = len(result.text)
        result.text = merge_by_text(result.text, segment_text)
        added_chars = len(result.text) - prev_len

        logger.debug(
            f"简单拼接: +{added_chars} 字符, 片段={len(segment_text)}, 总={len(result.text)}"
        )
    except Exception as exc:
        logger.warning(f"简单文本拼接失败: {exc}")


def apply_segment_result(task: Task, segment: SegmentRecognition, punc_model=None) -> Result:
    """
    将单个片段识别结果聚合到任务级 Result 中。

    这里维持原有客户端所依赖的 text/text_accu/tokens/timestamps 语义，
    让上层 WebSocket 协议保持兼容。
    """
    is_first_segment = task.task_id not in _results
    if is_first_segment:
        _results[task.task_id] = Result(task.task_id, task.socket_id, task.source)
        logger.debug(f"新任务: {task.task_id[:8]}...")

    result = _results[task.task_id]

    duration = AudioFormat.bytes_to_seconds(len(task.data))
    result.duration += duration - task.overlap
    if task.is_final:
        result.duration += task.overlap

    logger.debug(
        f"聚合片段: task={task.task_id[:8]}, duration={duration:.2f}s, "
        f"offset={task.offset:.2f}s, is_final={task.is_final}"
    )

    result.time_start = task.time_start
    result.time_submit = task.time_submit
    result.time_complete = time.time()

    _process_simple_merge(result, segment.text or '')

    try:
        new_tokens = process_tokens_safely(segment.tokens or [])
        new_timestamps = list(segment.timestamps or [])
        result.tokens, result.timestamps = merge_tokens_by_sequence_matcher(
            prev_tokens=result.tokens,
            prev_timestamps=result.timestamps,
            new_tokens=new_tokens,
            new_timestamps=new_timestamps,
            offset=task.offset,
            overlap=task.overlap,
            is_first_segment=is_first_segment,
        )
        logger.debug(f"时间戳拼接完成: 总 {len(result.tokens)} tokens")
    except (UnicodeDecodeError, UnicodeError) as exc:
        logger.warning(f"时间戳拼接失败: {exc}")

    result.text_accu = tokens_to_text(result.tokens)

    if not task.is_final:
        logger.debug(f"中间结果: {result.text[:30]}...")
        return result

    result.text = format_text(result.text, punc_model)
    result.text_accu = format_text(result.text_accu, punc_model)

    if not result.tokens and result.text:
        result.text_accu = result.text
        if result.source == 'file':
            chars = list(result.text_accu.replace(' ', ''))
            if chars and result.duration > 0:
                time_per_char = result.duration / len(chars)
                result.tokens = chars
                result.timestamps = [i * time_per_char for i in range(len(chars))]
                logger.warning(
                    f"文件转录模型无时间戳，使用粗略估计: {len(chars)} 字符, "
                    f"{result.duration:.2f}s"
                )
        else:
            logger.info("麦克风识别结果无时间戳，保留纯文本输出")

    result = _results.pop(task.task_id)
    result.is_final = True

    process_time = result.time_complete - task.time_submit
    rtf_value = process_time / result.duration if result.duration > 0 else 0
    logger.info(
        f"识别完成: task={task.task_id[:8]}, duration={result.duration:.2f}(s), "
        f"process_time={process_time:.3f}(s), RTF={rtf_value:.3f}"
    )
    logger.debug(f"最终文本: {result.text[:100]}...")
    return result


def clear_results_by_socket_id(socket_id: str) -> None:
    """连接断开时清理残留结果缓存。"""
    tasks_to_remove = [
        task_id for task_id, result in _results.items() if result.socket_id == socket_id
    ]
    for task_id in tasks_to_remove:
        _results.pop(task_id, None)

    if tasks_to_remove:
        logger.debug(
            f"已清理断开连接相关的缓存: socket_id={socket_id}, 任务数={len(tasks_to_remove)}"
        )
