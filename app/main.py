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


class RealtimeInputGate:
    def __init__(
        self,
        bridge: GeminiCallBridge,
        call_id: str,
        speech_threshold: int = 900,
        speech_start_frames: int = 10,
        speech_end_silence_frames: int = 50,
        prebuffer_frames: int = 10,
    ):
        self.bridge = bridge
        self.call_id = call_id
        self.speech_threshold = speech_threshold
        self.speech_start_frames = speech_start_frames
        self.speech_end_silence_frames = speech_end_silence_frames
        self.prebuffer: deque[bytes] = deque(maxlen=prebuffer_frames)
        self.speech_active = False
        self.speech_frames = 0
        self.silence_frames = 0
        self.last_frame_bytes = 0

    async def push(self, pcm: bytes, rms: int, timestamp_ms: int | None = None) -> None:
        self.last_frame_bytes = len(pcm)
        if self.speech_active:
            await self.bridge.send_input_audio(pcm)
            if rms >= self.speech_threshold:
                self.silence_frames = 0
            else:
                self.silence_frames += 1

            if self.silence_frames >= self.speech_end_silence_frames:
                await self.force_end(timestamp_ms, flush_silence=False)
            return

        # Do not treat line echo/noise as caller speech while the AI is greeting
        # or while AI audio is still reaching the phone.
        if self.bridge.completed_turn_count == 0 or self.bridge.output_recent(1.2):
            self.speech_frames = 0
            self.prebuffer.clear()
            return

        self.prebuffer.append(pcm)
        if rms >= self.speech_threshold:
            self.speech_frames += 1
        else:
            self.speech_frames = 0

        if self.speech_frames < self.speech_start_frames:
            return

        self.speech_active = True
        self.silence_frames = 0
        if timestamp_ms is None:
            log(f"[{self.call_id}] Speech started (rms={rms})")
        else:
            log(f"[{self.call_id}] Speech started (timestamp={timestamp_ms}ms, rms={rms})")
        await self.bridge.start_input_activity()
        for buffered_pcm in self.prebuffer:
            await self.bridge.send_input_audio(buffered_pcm)
        self.prebuffer.clear()

    async def force_end(
        self,
        timestamp_ms: int | None = None,
        flush_silence: bool = True,
    ) -> None:
        if not self.speech_active:
            self.speech_frames = 0
            self.silence_frames = 0
            self.prebuffer.clear()
            return

        if timestamp_ms is None:
            log(f"[{self.call_id}] Speech ended")
        else:
            log(f"[{self.call_id}] Speech ended (timestamp={timestamp_ms}ms)")
        self.speech_active = False
        self.speech_frames = 0
        self.silence_frames = 0
        self.prebuffer.clear()
        if flush_silence and self.last_frame_bytes:
            silence = b"\x00" * self.last_frame_bytes
            for _ in range(self.speech_end_silence_frames):
                await self.bridge.send_input_audio(silence)
        await self.bridge.end_input_activity()
        try:
            await asyncio.wait_for(self.bridge.turn_complete.wait(), timeout=30)
        except asyncio.TimeoutError:
            log(f"[{self.call_id}] Timed out waiting for current Gemini turn before commit")
        await self.bridge.commit_input_audio_turn()


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
    input_gate: RealtimeInputGate | None = None

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
                input_gate = RealtimeInputGate(bridge, call_id)
                await bridge.start()

            elif event_type == "media":
                if not bridge:
                    continue
                media = event.get("media") or {}
                timestamp_ms = int(media.get("timestamp") or 0)
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

                if input_gate:
                    await input_gate.push(pcm, rms, timestamp_ms)

            elif event_type == "stop":
                log(f"[{call_id}] SignalWire stream stopped")
                if input_gate:
                    await input_gate.force_end()
                if bridge:
                    await bridge.end_input_audio()
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
    input_gate: RealtimeInputGate | None = None
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
                    input_gate = RealtimeInputGate(bridge, call_id)
                    await bridge.start()
                elif event.get("event") == "mock:audio_end":
                    if bridge:
                        if input_gate:
                            await input_gate.force_end()
                        await bridge.end_input_audio()
                else:
                    print(f"[{call_id}] Infobip text event: {event}", flush=True)

            elif "bytes" in message and message["bytes"] is not None:
                if input_gate:
                    pcm = message["bytes"]
                    await input_gate.push(pcm, audioop.rms(pcm, 2))

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
