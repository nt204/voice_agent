import base64
import asyncio
import audioop
import json
from collections import deque
from html import escape
from urllib.parse import parse_qsl
from urllib.parse import urljoin, urlparse, urlunparse

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status

from app.audio import (
    extract_sample_rate,
    pcm16_to_signalwire_payload,
    signalwire_payload_to_pcm16,
)
from app.config import config
from app.gemini_bridge import GeminiCallBridge
from app.logging_utils import log

app = FastAPI(title="Viber Gemini Live Bridge")


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/infobip/events")
async def infobip_events(payload: dict) -> dict[str, bool]:
    print("Infobip event:", json.dumps(payload, ensure_ascii=False))
    return {"ok": True}


@app.api_route("/signalwire/stream-status", methods=["GET", "POST"])
async def signalwire_stream_status(request: Request) -> dict[str, bool]:
    payload = dict(request.query_params)
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload.update(await request.json())
        else:
            body = (await request.body()).decode("utf-8", errors="replace")
            payload.update(dict(parse_qsl(body)))
    log(f"SignalWire stream status: {payload}")
    return {"ok": True}


@app.api_route("/signalwire/answer", methods=["GET", "POST"])
async def signalwire_answer() -> Response:
    stream_url = _public_ws_url("/signalwire/ws")
    status_url = _public_http_url("/signalwire/stream-status")
    auth = ""
    if config.signalwire.stream_bearer_token:
        auth = f' authBearerToken="{escape(config.signalwire.stream_bearer_token)}"'

    cxml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{escape(stream_url)}" codec="{escape(config.signalwire.stream_codec)}" realtime="true" statusCallback="{escape(status_url)}" statusCallbackMethod="POST"{auth} />
  </Connect>
</Response>
"""
    return Response(content=cxml, media_type="application/xml")


@app.websocket("/signalwire/ws")
async def signalwire_ws(websocket: WebSocket) -> None:
    expected_token = config.signalwire.stream_bearer_token
    authorization = websocket.headers.get("authorization", "")
    if expected_token and authorization and authorization != f"Bearer {expected_token}":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    bridge: GeminiCallBridge | None = None
    call_id = "unknown-call"
    stream_sid: str | None = None
    sample_rate = config.signalwire.stream_sample_rate
    encoding = "audio/x-L16"
    next_send_at = 0.0
    outbound_frame_count = 0
    ignore_media_before_ms = 0
    speech_active = False
    speech_frames = 0
    silence_frames = 0
    speech_threshold = 700
    speech_start_frames = 2
    speech_end_silence_frames = 25
    speech_prebuffer = deque(maxlen=10)

    async def send_audio(frame: bytes) -> None:
        nonlocal next_send_at, outbound_frame_count
        if not stream_sid:
            return
        now = asyncio.get_running_loop().time()
        if next_send_at > now:
            await asyncio.sleep(next_send_at - now)
        next_send_at = max(next_send_at, now) + 0.02

        payload = pcm16_to_signalwire_payload(frame, encoding)
        await websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": base64.b64encode(payload).decode("ascii")},
                }
            )
        )
        outbound_frame_count += 1
        if outbound_frame_count <= 3 or outbound_frame_count % 50 == 0:
            log(
                f"[{call_id}] SignalWire outbound media "
                f"{outbound_frame_count} ({len(payload)} bytes {encoding})"
            )

    try:
        inbound_frame_count = 0
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "text" not in message or message["text"] is None:
                continue

            event = json.loads(message["text"])
            event_type = event.get("event")

            if event_type == "connected":
                log("[signalwire] WebSocket connected")

            elif event_type == "start":
                start = event.get("start") or {}
                media_format = start.get("mediaFormat") or {}
                stream_sid = start.get("streamSid")
                call_id = start.get("callSid") or call_id
                sample_rate = int(media_format.get("sampleRate") or sample_rate)
                encoding = media_format.get("encoding") or encoding
                log(
                    f"[{call_id}] SignalWire stream started: {stream_sid} "
                    f"{encoding} {sample_rate}Hz"
                )

                bridge = GeminiCallBridge(
                    call_id=call_id,
                    call_sample_rate=sample_rate,
                    send_audio=send_audio,
                )
                await bridge.start()
                ignore_media_before_ms = max(ignore_media_before_ms, 9000)
                log(f"[{call_id}] Ignoring inbound media before {ignore_media_before_ms}ms")

            elif event_type == "media":
                if not bridge:
                    continue
                media = event.get("media") or {}
                timestamp_ms = int(media.get("timestamp") or 0)
                if timestamp_ms < ignore_media_before_ms:
                    continue
                raw = base64.b64decode(media.get("payload") or "")
                inbound_frame_count += 1
                pcm = signalwire_payload_to_pcm16(raw, encoding)
                rms = audioop.rms(pcm, 2)
                if inbound_frame_count <= 3 or inbound_frame_count % 100 == 0:
                    log(
                        f"[{call_id}] SignalWire inbound media "
                        f"{inbound_frame_count} ({len(raw)} bytes {encoding}, "
                        f"timestamp={timestamp_ms}ms, rms={rms})"
                    )

                if rms >= speech_threshold:
                    speech_frames += 1
                    silence_frames = 0
                else:
                    silence_frames += 1

                started_now = False
                if not speech_active:
                    speech_prebuffer.append(pcm)
                    if speech_frames >= speech_start_frames:
                        speech_active = True
                        started_now = True
                        silence_frames = 0
                        log(
                            f"[{call_id}] Speech started "
                            f"(timestamp={timestamp_ms}ms, rms={rms})"
                        )
                        for buffered_pcm in speech_prebuffer:
                            await bridge.send_input_audio(buffered_pcm)
                        speech_prebuffer.clear()
                    else:
                        continue

                if not started_now:
                    await bridge.send_input_audio(pcm)

                if speech_active and silence_frames >= speech_end_silence_frames:
                    speech_active = False
                    speech_frames = 0
                    silence_frames = 0
                    log(f"[{call_id}] Speech ended (timestamp={timestamp_ms}ms)")

            elif event_type == "stop":
                log(f"[{call_id}] SignalWire stream stopped")
                break

            elif event_type == "dtmf":
                log(f"[{call_id}] SignalWire DTMF: {event.get('dtmf')}")

            elif event_type == "mark":
                pass

            else:
                log(f"[{call_id}] SignalWire event: {event}")

    except WebSocketDisconnect:
        log(f"[{call_id}] SignalWire WebSocket disconnected")
    finally:
        if bridge:
            await bridge.close()


@app.websocket("/infobip/ws")
async def infobip_ws(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if config.infobip.ws_shared_secret and token != config.infobip.ws_shared_secret:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    bridge: GeminiCallBridge | None = None
    call_id = "unknown-call"
    sample_rate = config.infobip.ws_sample_rate

    async def send_audio(frame: bytes) -> None:
        await websocket.send_bytes(frame)

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if "text" in message and message["text"] is not None:
                event = json.loads(message["text"])

                if event.get("event") == "websocket:connected":
                    call_id = (
                        event.get("callId")
                        or event.get("call_id")
                        or event.get("dialogId")
                        or call_id
                    )
                    sample_rate = extract_sample_rate(event.get("content-type"), sample_rate)
                    print(f"[{call_id}] Infobip WebSocket connected at {sample_rate}Hz", flush=True)

                    bridge = GeminiCallBridge(
                        call_id=call_id,
                        call_sample_rate=sample_rate,
                        send_audio=send_audio,
                    )
                    await bridge.start()
                elif event.get("event") == "mock:audio_end":
                    if bridge:
                        await bridge.end_input_audio()
                else:
                    print(f"[{call_id}] Infobip text event: {event}", flush=True)

            elif "bytes" in message and message["bytes"] is not None:
                if bridge:
                    await bridge.send_input_audio(message["bytes"])

    except WebSocketDisconnect:
        print(f"[{call_id}] Infobip WebSocket disconnected", flush=True)
    finally:
        if bridge:
            await bridge.close()


def _public_ws_url(path: str) -> str:
    public_base_url = config.public_base_url
    if not public_base_url:
        public_base_url = "http://localhost:3000"
    parsed = urlparse(urljoin(public_base_url.rstrip("/") + "/", path.lstrip("/")))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, parsed.path, "", "", ""))


def _public_http_url(path: str) -> str:
    public_base_url = config.public_base_url
    if not public_base_url:
        public_base_url = "http://localhost:3000"
    parsed = urlparse(urljoin(public_base_url.rstrip("/") + "/", path.lstrip("/")))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
