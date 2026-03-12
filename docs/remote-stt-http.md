# Remote HTTP STT Provider

`ServerConfig.provider_type = 'remote_http'` 时，CapsWriter 服务端不再直接加载本地语音模型，而是把客户端上传的音频片段转发给远端 HTTP 服务，再把结果按原有协议聚合后回传给 Windows 客户端。

目前支持两种请求格式：

- `capswriter_json`：发送 JSON + base64 音频
- `multipart_wav`：把片段封装成 wav 文件，再用 `multipart/form-data` 上传

## 请求格式：capswriter_json

- 方法：`POST`
- `Content-Type: application/json`

请求体字段：

```json
{
  "task_id": "task-uuid",
  "source": "mic",
  "audio": "<base64-float32-16k-mono>",
  "offset": 0.0,
  "overlap": 4.0,
  "is_final": false,
  "time_start": 1710000000.0,
  "time_submit": 1710000001.0,
  "samplerate": 16000,
  "context": ""
}
```

说明：

- `audio` 是客户端原始 float32 PCM 音频，单声道，16kHz，base64 编码。
- `offset` / `overlap` 由 gateway 继续用于分段拼接。
- 远端服务只需要识别当前片段，不需要自己维护整段任务状态。

## 响应格式

响应体至少返回：

```json
{
  "text": "你好世界"
}
```

推荐返回：

```json
{
  "text": "你好世界",
  "tokens": ["你", "好", "世", "界"],
  "timestamps": [0.0, 0.2, 0.4, 0.6]
}
```

说明：

- `tokens` 和 `timestamps` 是可选的。
- 如果缺失，gateway 会退回到只用 `text` 聚合，并在最终结果阶段生成粗略时间戳。
- `timestamps` 预期是“相对于当前片段起点”的秒数，gateway 会再叠加片段 `offset`。

## 配置项

`config_server.py` 中的相关配置：

```python
class ServerConfig:
    provider_type = 'remote_http'

class RemoteHTTPArgs:
    endpoint = 'http://127.0.0.1:9999/stt'
    timeout = 60.0
    authorization_token = ''
    verify_ssl = True
    headers = {}
    request_format = 'capswriter_json'
```

## 请求格式：multipart_wav

适合像 `.20` 上的 Faster Whisper 服务这种接口：

- `POST /transcribe`
- `multipart/form-data`
- 文件字段名默认是 `audio`
- 可附带 `vad_filter=true/false`

示例配置：

```python
class ServerConfig:
    provider_type = 'remote_http'

class RemoteHTTPArgs:
    endpoint = 'http://192.168.0.20:9001/transcribe'
    request_format = 'multipart_wav'
    multipart_field = 'audio'
    multipart_filename = 'audio.wav'
    vad_filter = True
```

## 当前边界

这个 provider 只替换 **STT 执行层**。以下能力仍然留在 Windows 客户端：

- 热键和录音控制
- 文本上屏
- 热词替换
- LLM 后处理
- 日记、录音保存、UDP 控制/广播
