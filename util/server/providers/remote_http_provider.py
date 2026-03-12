# coding: utf-8
"""远端 HTTP STT provider。"""

from array import array
from base64 import b64encode
from io import BytesIO
import json
import ssl
import struct
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid
import wave

from config_server import RemoteHTTPArgs
from util.server.result_builder import SegmentRecognition, apply_segment_result

from .. import logger
from .base import BaseSTTProvider


class RemoteHTTPProvider(BaseSTTProvider):
    """
    将音频片段转发给远端 STT HTTP 服务。

    远端接口约定：
    - POST JSON
    - 请求体包含 `audio`(base64 float32 mono 16k)、task 元信息
    - 响应体至少返回 `text`
    - 可选返回 `tokens` 和 `timestamps`
    """

    name = 'remote_http'

    def __init__(self):
        self.endpoint = RemoteHTTPArgs.endpoint.strip()
        self.timeout = float(RemoteHTTPArgs.timeout)
        self.authorization_token = RemoteHTTPArgs.authorization_token.strip()
        self.verify_ssl = bool(RemoteHTTPArgs.verify_ssl)
        self.headers = dict(getattr(RemoteHTTPArgs, 'headers', {}) or {})
        self.request_format = RemoteHTTPArgs.request_format.strip().lower()
        self.multipart_field = RemoteHTTPArgs.multipart_field
        self.multipart_filename = RemoteHTTPArgs.multipart_filename
        self.vad_filter = bool(RemoteHTTPArgs.vad_filter)
        self.language = (getattr(RemoteHTTPArgs, 'language', '') or '').strip()
        self.send_context_as_initial_prompt = bool(
            getattr(RemoteHTTPArgs, 'send_context_as_initial_prompt', True)
        )

    def load(self) -> None:
        if not self.endpoint:
            raise ValueError("RemoteHTTPArgs.endpoint 不能为空")
        logger.info(
            f"远端 STT provider 已启用: {self.endpoint} "
            f"(request_format={self.request_format})"
        )

    @staticmethod
    def _with_query(url: str, extra_query: dict[str, str]) -> str:
        parsed = urlsplit(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update(extra_query)
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
        )

    @staticmethod
    def _audio_to_wav_bytes(audio_bytes: bytes, samplerate: int) -> bytes:
        samples = array('f')
        samples.frombytes(audio_bytes)

        pcm16 = bytearray()
        for sample in samples:
            sample = max(-1.0, min(1.0, sample))
            pcm16.extend(struct.pack('<h', int(sample * 32767)))

        buffer = BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(samplerate)
            wav_file.writeframes(bytes(pcm16))
        return buffer.getvalue()

    @staticmethod
    def _build_multipart_body(field_name: str, filename: str, content_type: str, file_bytes: bytes):
        boundary = f'----CapsWriterBoundary{uuid.uuid4().hex}'
        head = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f'Content-Type: {content_type}\r\n\r\n'
        ).encode('utf-8')
        tail = f'\r\n--{boundary}--\r\n'.encode('utf-8')
        return boundary, head + file_bytes + tail

    def _build_request(self, task):
        if self.request_format == 'capswriter_json':
            payload = {
                'task_id': task.task_id,
                'source': task.source,
                'audio': b64encode(task.data).decode('ascii'),
                'offset': task.offset,
                'overlap': task.overlap,
                'is_final': task.is_final,
                'time_start': task.time_start,
                'time_submit': task.time_submit,
                'samplerate': task.samplerate,
                'context': task.context,
            }
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                **self.headers,
            }
            return self.endpoint, body, headers

        if self.request_format == 'multipart_wav':
            wav_bytes = self._audio_to_wav_bytes(task.data, task.samplerate)
            boundary, body = self._build_multipart_body(
                self.multipart_field,
                self.multipart_filename,
                'audio/wav',
                wav_bytes,
            )
            headers = {
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Accept': 'application/json',
                **self.headers,
            }
            source_prefix = 'mic' if task.source == 'mic' else 'file'
            query = {
                'source': task.source,
                'vad_filter': str(
                    getattr(RemoteHTTPArgs, f'{source_prefix}_vad_filter', self.vad_filter)
                ).lower(),
                'word_timestamps': str(
                    getattr(RemoteHTTPArgs, f'{source_prefix}_word_timestamps', False)
                ).lower(),
                'condition_on_previous_text': str(
                    getattr(
                        RemoteHTTPArgs,
                        f'{source_prefix}_condition_on_previous_text',
                        False,
                    )
                ).lower(),
                'beam_size': str(getattr(RemoteHTTPArgs, f'{source_prefix}_beam_size', 5)),
                'best_of': str(getattr(RemoteHTTPArgs, f'{source_prefix}_best_of', 5)),
            }
            if self.language:
                query['language'] = self.language
            if task.context and self.send_context_as_initial_prompt:
                query['initial_prompt'] = task.context
            url = self._with_query(
                self.endpoint,
                query,
            )
            return url, body, headers

        raise ValueError(
            f"不支持的 RemoteHTTPArgs.request_format: {self.request_format}"
        )

    def recognize(self, task):
        url, body, headers = self._build_request(task)
        if self.authorization_token:
            headers['Authorization'] = f'Bearer {self.authorization_token}'

        request = Request(
            url,
            data=body,
            headers=headers,
            method='POST',
        )

        ssl_context = None
        if not self.verify_ssl:
            ssl_context = ssl._create_unverified_context()

        try:
            with urlopen(request, timeout=self.timeout, context=ssl_context) as response:
                body = response.read().decode('utf-8')
        except HTTPError as exc:
            error_body = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(
                f"远端 STT 服务返回 HTTP {exc.code}: {error_body}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"无法连接远端 STT 服务: {exc}") from exc

        try:
            remote_result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"远端 STT 响应不是合法 JSON: {body[:200]}") from exc

        timestamps = remote_result.get('timestamps') or []
        tokens = remote_result.get('tokens') or []
        if (not tokens or len(tokens) != len(timestamps)) and remote_result.get('words'):
            words = remote_result.get('words') or []
            tokens = [word.get('word', '') for word in words]
            timestamps = [word.get('start', 0.0) for word in words]

        segment = SegmentRecognition(
            text=remote_result.get('text') or remote_result.get('text_accu') or '',
            tokens=tokens,
            timestamps=timestamps,
        )
        return apply_segment_result(task, segment)
