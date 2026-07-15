import base64
import asyncio
import audioop
import httpx
import json
from collections import deque
from html import escape
from pathlib import Path
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urljoin, urlparse, urlunparse

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.audio import (
    extract_sample_rate,
    pcm16_to_signalwire_payload,
    pcm16_to_telnyx_payload,
    signalwire_payload_to_pcm16,
    telnyx_payload_to_pcm16,
)
from app.call_history import CallHistoryStore
from app.config import config, gemini_system_instruction
from app.database import init_db
from app.gemini_bridge import GeminiCallBridge
from app.logging_utils import log
from app.admin import router as admin_router

app = FastAPI(title="Viber Gemini Live Bridge")
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize the recordings database tables
init_db()

call_history = CallHistoryStore(config.database_url)
legacy_call_history_path = BASE_DIR / "data" / "call_history.db"
if not config.database_url.startswith("sqlite") and legacy_call_history_path.exists():
    migrated_counts = call_history.migrate_from_sqlite(legacy_call_history_path)
    if migrated_counts:
        log(f"Migrated SQLite call history to PostgreSQL: {migrated_counts}")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")


class RealtimeInputGate:
    def __init__(
        self,
        bridge: GeminiCallBridge,
        call_id: str,
        speech_threshold: int = 900,
        speech_start_frames: int = 10,
        speech_end_silence_frames: int = 50,
        prebuffer_frames: int = 10,
        require_initial_turn: bool = True,
        wait_for_turn_before_commit: bool = True,
        adaptive_threshold: bool = False,
        noise_multiplier: float = 3.0,
        noise_margin: int = 80,
        barge_in_threshold: int | None = None,
        echo_suppression_ms: int = 700,
    ):
        self.bridge = bridge
        self.call_id = call_id
        self.speech_threshold = speech_threshold
        self.speech_start_frames = speech_start_frames
        self.speech_end_silence_frames = speech_end_silence_frames
        self.require_initial_turn = require_initial_turn
        self.wait_for_turn_before_commit = wait_for_turn_before_commit
        self.adaptive_threshold = adaptive_threshold
        self.noise_multiplier = noise_multiplier
        self.noise_margin = noise_margin
        self.barge_in_threshold = barge_in_threshold or speech_threshold
        self.echo_suppression_seconds = echo_suppression_ms / 1000
        self.noise_floor = 0.0
        self.prebuffer: deque[bytes] = deque(maxlen=prebuffer_frames)
        self.speech_active = False
        self.waiting_for_response = False
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

        if self.waiting_for_response:
            if self.bridge.turn_complete.is_set():
                self.waiting_for_response = False
            else:
                self.speech_frames = 0
                self.prebuffer.clear()
                return

        # If configured, wait for the initial AI greeting to finish before
        # listening. After that, strong caller speech is treated as barge-in.
        if self.require_initial_turn and self.bridge.completed_turn_count == 0:
            self.speech_frames = 0
            self.prebuffer.clear()
            return

        output_recent = self.bridge.output_recent(self.echo_suppression_seconds)
        threshold = self._effective_threshold(output_recent=output_recent)
        self.prebuffer.append(pcm)
        if rms >= threshold:
            self.speech_frames += 1
        else:
            self.speech_frames = 0
            self._update_noise_floor(rms, output_recent=output_recent)

        if self.speech_frames < self.speech_start_frames:
            return

        self.speech_active = True
        self.silence_frames = 0
        if hasattr(self.bridge, "set_output_muted"):
            await self.bridge.set_output_muted(True)
        if timestamp_ms is None:
            log(f"[{self.call_id}] Speech started (rms={rms}, threshold={threshold})")
        else:
            log(
                f"[{self.call_id}] Speech started "
                f"(timestamp={timestamp_ms}ms, rms={rms}, threshold={threshold})"
            )
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
        self.waiting_for_response = not self.bridge.turn_complete.is_set()
        if self.wait_for_turn_before_commit:
            try:
                await asyncio.wait_for(self.bridge.turn_complete.wait(), timeout=30)
                self.waiting_for_response = False
            except asyncio.TimeoutError:
                log(f"[{self.call_id}] Timed out waiting for current Gemini turn before commit")
        if hasattr(self.bridge, "set_output_muted"):
            await getattr(self.bridge, "set_output_muted")(False)
        await self.bridge.commit_input_audio_turn()

    def _effective_threshold(self, *, output_recent: bool) -> int:
        threshold = self.speech_threshold
        if self.adaptive_threshold:
            adaptive_threshold = max(
                int(self.noise_floor * self.noise_multiplier),
                int(self.noise_floor + self.noise_margin),
            )
            threshold = max(threshold, adaptive_threshold)
        if output_recent:
            threshold = max(threshold, self.barge_in_threshold)
        return threshold

    def _update_noise_floor(self, rms: int, *, output_recent: bool) -> None:
        if not self.adaptive_threshold or output_recent:
            return
        self.noise_floor = rms if self.noise_floor == 0 else (self.noise_floor * 0.9) + (rms * 0.1)


class RealtimePassthroughInput:
    def __init__(self, bridge: GeminiCallBridge, call_id: str):
        self.bridge = bridge
        self.call_id = call_id
        self.frame_count = 0

    async def push(self, pcm: bytes, rms: int, timestamp_ms: int | None = None) -> None:
        self.frame_count += 1
        await self.bridge.send_input_audio(pcm)
        if self.frame_count <= 3 or self.frame_count % 100 == 0:
            if timestamp_ms is None:
                log(f"[{self.call_id}] Realtime input frame {self.frame_count} (rms={rms})")
            else:
                log(
                    f"[{self.call_id}] Realtime input frame {self.frame_count} "
                    f"(timestamp={timestamp_ms}ms, rms={rms})"
                )

    async def force_end(self) -> None:
        await self.bridge.end_input_audio()


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/")
async def dashboard() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "index.html")


@app.get("/admin")
async def admin_dashboard() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "index.html")


app.include_router(admin_router)


def _call_counts() -> dict[str, int]:
    calls = call_history.list_calls(limit=500)
    return {
        "all": len(calls),
        "inbound": sum(1 for call in calls if call["direction"] == "inbound"),
        "outbound": sum(1 for call in calls if call["direction"] == "outbound"),
    }


def _interest_counts() -> dict[str, int]:
    stats = call_history.sales_statistics()
    return stats["interest_counts"]


def _store_transcript(call_id: str):
    async def record(speaker: str, text: str) -> None:
        call_history.add_transcript(call_id, speaker, text)

    return record


async def _finalize_call(bridge, call_id: str, store=None) -> None:
    target_store = store or call_history
    if bridge:
        try:
            await bridge.finalize_transcript(target_store)
        except Exception as exc:
            log(f"[{call_id}] Final ASR stage failed: {type(exc).__name__}: {exc}")
        finally:
            try:
                await bridge.close()
            except Exception as exc:
                log(f"[{call_id}] Gemini close failed: {type(exc).__name__}: {exc}")

    if call_id == "unknown-call":
        return
    log(f"[{call_id}] ASR stage complete; starting final sales extraction")
    await asyncio.to_thread(target_store.finish_call, call_id)


def _telnyx_audio_turn_handler(call_id: str):
    if (
        not config.gemini.secondary_asr_enabled
        or not config.gemini.in_call_secondary_asr_enabled
    ):
        return None

    from app.secondary_asr import SecondaryAsrTranscriber

    transcriber = SecondaryAsrTranscriber()

    async def transcribe_turn(
        audio: bytes,
        sample_rate: int,
        turn_number: int,
        live_candidate: str,
    ) -> str:
        corrected = await transcriber.transcribe(audio, sample_rate, live_candidate)
        if corrected:
            log(
                f"[{call_id}] Secondary ASR turn {turn_number}: "
                f"live='{live_candidate}' corrected='{corrected}'"
            )
        return corrected

    return transcribe_turn


@app.get("/api/calls")
async def api_calls(
    direction: str | None = None,
    q: str = "",
    interest_status: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    return {
        "calls": call_history.list_calls(
            direction=direction,
            query=q,
            interest_status=interest_status,
            limit=limit,
        ),
        "counts": _call_counts(),
        "interest_counts": _interest_counts(),
    }


@app.get("/api/calls/{call_id}")
async def api_call_detail(call_id: str) -> dict[str, object]:
    call = call_history.get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@app.get("/api/admin/summary")
async def api_admin_summary() -> dict[str, object]:
    recent_leads = call_history.list_calls(
        interest_status="needs_consultation",
        limit=12,
    )
    recent_calls = call_history.list_calls(limit=12)
    return {
        "stats": call_history.sales_statistics(),
        "recent_leads": recent_leads,
        "recent_calls": recent_calls,
    }


@app.get("/api/orders")
async def api_orders(limit: int = 100) -> dict[str, object]:
    return {"orders": call_history.list_orders(limit=limit)}


@app.get("/api/outbound/requests")
async def api_outbound_requests(limit: int = 50) -> dict[str, object]:
    return {"requests": call_history.list_outbound_requests(limit=limit)}


async def _request_payload(request: Request) -> dict:
    payload = dict(request.query_params)
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload.update(await request.json())
        else:
            body = (await request.body()).decode("utf-8", errors="replace")
            payload.update(dict(parse_qsl(body)))
    return payload


def _telnyx_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return f"Telnyx API error {response.status_code}: {response.text}"
    return f"Telnyx API error {response.status_code}: {data}"


def _normalize_phone_number(number: str) -> str:
    cleaned = "".join(char for char in number.strip() if char.isdigit() or char == "+")
    if cleaned.startswith("+"):
        return f"+{''.join(char for char in cleaned[1:] if char.isdigit())}"
    digits = "".join(char for char in cleaned if char.isdigit())
    if digits.startswith("0") and len(digits) >= 9:
        return f"+84{digits[1:]}"
    return digits


@app.post("/infobip/events")
async def infobip_events(payload: dict) -> dict[str, bool]:
    print("Infobip event:", json.dumps(payload, ensure_ascii=False))
    return {"ok": True}


@app.api_route("/telnyx/status", methods=["GET", "POST"])
async def telnyx_stream_status(request: Request) -> dict[str, bool]:
    payload = dict(request.query_params)
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload.update(await request.json())
        else:
            body = (await request.body()).decode("utf-8", errors="replace")
            payload.update(dict(parse_qsl(body)))
    log(f"Telnyx stream status: {payload}")
    return {"ok": True}


@app.api_route("/telnyx/outbound/status", methods=["GET", "POST"])
async def telnyx_outbound_stream_status(request: Request) -> dict[str, bool]:
    payload = await _request_payload(request)
    log(f"Telnyx outbound stream status: {payload}")
    call_sid = str(payload.get("CallSid") or payload.get("call_sid") or "").strip()
    call_status = str(payload.get("CallStatus") or payload.get("call_status") or "").strip()
    if call_sid and call_status:
        call_history.update_outbound_request_by_call_sid(
            call_sid,
            call_status,
            customer_phone=str(payload.get("To") or payload.get("to") or "").strip(),
            started_at=str(
                payload.get("AnsweredTime")
                or payload.get("StartTime")
                or payload.get("start_time")
                or ""
            ).strip(),
            ended_at=str(
                payload.get("EndTime")
                or payload.get("end_time")
                or ""
            ).strip(),
        )
    return {"ok": True}


@app.api_route("/telnyx/answer", methods=["GET", "POST"])
async def telnyx_answer() -> Response:
    stream_url = _public_ws_url("/telnyx/ws")
    status_url = _public_http_url("/telnyx/status")
    stream_track = getattr(config.telnyx, "stream_track", "inbound_track")
    pause_length_seconds = getattr(config.telnyx, "pause_length_seconds", 600)
    if config.telnyx.stream_token:
        stream_url = f"{stream_url}?{urlencode({'token': config.telnyx.stream_token})}"

    texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{escape(stream_url)}" track="{escape(stream_track)}" codec="{escape(config.telnyx.stream_codec)}" bidirectionalMode="rtp" bidirectionalCodec="{escape(config.telnyx.stream_codec)}" bidirectionalSamplingRate="{config.telnyx.stream_sample_rate}" statusCallback="{escape(status_url)}" statusCallbackMethod="POST"></Stream>
  </Connect>
  <Pause length="{pause_length_seconds}" />
</Response>
"""
    return Response(content=texml, media_type="application/xml")


@app.api_route("/telnyx/outbound/answer", methods=["GET", "POST"])
async def telnyx_outbound_answer() -> Response:
    stream_url = _public_ws_url("/telnyx/outbound/ws")
    status_url = _public_http_url("/telnyx/outbound/status")
    stream_track = getattr(config.telnyx, "stream_track", "inbound_track")
    pause_length_seconds = getattr(config.telnyx, "pause_length_seconds", 600)
    greeting_delay_seconds = max(
        0,
        int(getattr(config.telnyx, "outbound_greeting_delay_seconds", 2)),
    )
    if config.telnyx.stream_token:
        stream_url = f"{stream_url}?{urlencode({'token': config.telnyx.stream_token})}"

    texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Pause length="{greeting_delay_seconds}" />
  <Connect>
    <Stream url="{escape(stream_url)}" track="{escape(stream_track)}" codec="{escape(config.telnyx.stream_codec)}" bidirectionalMode="rtp" bidirectionalCodec="{escape(config.telnyx.stream_codec)}" bidirectionalSamplingRate="{config.telnyx.stream_sample_rate}" statusCallback="{escape(status_url)}" statusCallbackMethod="POST"></Stream>
  </Connect>
  <Pause length="{pause_length_seconds}" />
</Response>
"""
    return Response(content=texml, media_type="application/xml")


@app.post("/telnyx/outbound/call")
async def telnyx_outbound_call(request: Request) -> dict[str, object]:
    payload = await request.json()
    to_number = _normalize_phone_number(str(payload.get("to_number") or ""))
    from_number = _normalize_phone_number(str(
        payload.get("from_number") or config.telnyx.outbound_from_number or ""
    ))
    if not to_number:
        raise HTTPException(status_code=400, detail="Missing to_number")
    if not from_number:
        outbound_request = call_history.create_outbound_request(to_number=to_number)
        call_history.mark_outbound_request_failed(
            outbound_request["id"],
            "Missing from_number or TELNYX_OUTBOUND_FROM_NUMBER",
        )
        raise HTTPException(status_code=400, detail="Missing from_number or TELNYX_OUTBOUND_FROM_NUMBER")

    outbound_request = call_history.create_outbound_request(
        to_number=to_number,
        from_number=from_number,
    )

    missing = [
        name
        for name, value in {
            "TELNYX_API_KEY": config.telnyx.api_key,
            "TELNYX_ACCOUNT_SID": config.telnyx.account_sid,
            "TELNYX_TEXML_APP_ID": config.telnyx.texml_app_id,
            "PUBLIC_BASE_URL": config.public_base_url,
        }.items()
        if not value
    ]
    if missing:
        detail = f"Missing config: {', '.join(missing)}"
        call_history.mark_outbound_request_failed(outbound_request["id"], detail)
        raise HTTPException(status_code=500, detail=detail)

    url = f"https://api.telnyx.com/v2/texml/Accounts/{config.telnyx.account_sid}/Calls"
    texml_url = _public_http_url("/telnyx/outbound/answer")
    status_callback = _public_http_url("/telnyx/outbound/status")
    body = {
        "ApplicationSid": config.telnyx.texml_app_id,
        "To": to_number,
        "From": from_number,
        "Url": texml_url,
        "UrlMethod": "POST",
        "StatusCallback": status_callback,
        "StatusCallbackMethod": "POST",
    }
    headers = {
        "Authorization": f"Bearer {config.telnyx.api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=config.telnyx.outbound_call_timeout_seconds) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _telnyx_error_detail(exc.response)
        call_history.mark_outbound_request_failed(outbound_request["id"], detail)
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        detail = f"Telnyx request failed: {exc}"
        call_history.mark_outbound_request_failed(outbound_request["id"], detail)
        raise HTTPException(status_code=502, detail=detail) from exc

    data = response.json()
    call_sid = data.get("sid") or data.get("call_sid") or (data.get("data") or {}).get("sid")
    call_history.mark_outbound_request_started(outbound_request["id"], call_sid or "")
    log(f"Telnyx outbound call requested: to={to_number} from={from_number} sid={call_sid}")
    return {
        "ok": True,
        "call_sid": call_sid,
        "request": call_history.get_outbound_request(outbound_request["id"]),
        "telnyx": data,
    }


@app.get("/telnyx/greeting.wav")
async def telnyx_greeting() -> FileResponse:
    return FileResponse(_telnyx_greeting_audio_path(), media_type="audio/wav")


@app.websocket("/telnyx/outbound/ws")
async def telnyx_outbound_ws(websocket: WebSocket) -> None:
    await _telnyx_ws(websocket, mode="outbound")


@app.websocket("/telnyx/ws")
async def telnyx_ws(websocket: WebSocket) -> None:
    await _telnyx_ws(websocket, mode="inbound")


def _telnyx_bridge_options(mode: str) -> dict[str, object]:
    return {
        "send_initial_greeting": True,
        "system_instruction": (
            gemini_system_instruction("outbound") if mode == "outbound" else None
        ),
    }


def _telnyx_input_gate_options(mode: str) -> dict[str, object]:
    return {
        "speech_threshold": config.telnyx.speech_threshold,
        "speech_start_frames": getattr(config.telnyx, "speech_start_frames", 2),
        "speech_end_silence_frames": getattr(config.telnyx, "speech_end_silence_frames", 30),
        "require_initial_turn": mode == "outbound",
        "wait_for_turn_before_commit": False,
        "adaptive_threshold": getattr(config.telnyx, "adaptive_threshold", True),
        "noise_multiplier": getattr(config.telnyx, "noise_multiplier", 3.0),
        "noise_margin": getattr(config.telnyx, "noise_margin", 80),
        "barge_in_threshold": getattr(config.telnyx, "barge_in_threshold", 900),
        "echo_suppression_ms": getattr(config.telnyx, "echo_suppression_ms", 700),
    }


async def _telnyx_ws(websocket: WebSocket, mode: str = "inbound") -> None:
    expected_token = config.telnyx.stream_token
    token = websocket.query_params.get("token")
    if expected_token and token != expected_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    bridge: GeminiCallBridge | None = None
    input_gate: RealtimeInputGate | RealtimePassthroughInput | None = None
    recorder = None
    call_id = "unknown-call"
    stream_id: str | None = None
    sample_rate = config.telnyx.stream_sample_rate
    codec = config.telnyx.stream_codec
    next_send_at = 0.0
    outbound_frame_count = 0

    async def send_audio(frame: bytes) -> None:
        nonlocal next_send_at, outbound_frame_count
        now = asyncio.get_running_loop().time()
        if next_send_at > now:
            await asyncio.sleep(next_send_at - now)
        next_send_at = max(next_send_at, now) + 0.02

        payload = pcm16_to_telnyx_payload(frame, codec)
        if recorder:
            recorder.write_outbound(frame)
        message = {
            "event": "media",
            "media": {"payload": base64.b64encode(payload).decode("ascii")},
        }
        await websocket.send_text(json.dumps(message))

        outbound_frame_count += 1
        if outbound_frame_count <= 3 or outbound_frame_count % 50 == 0:
            log(
                f"[{call_id}] Telnyx outbound media "
                f"{outbound_frame_count} ({len(payload)} bytes {codec})"
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
                log("[telnyx] WebSocket connected")

            elif event_type == "start":
                start = event.get("start") or {}
                media_format = start.get("media_format") or start.get("mediaFormat") or {}
                stream_id = event.get("stream_id") or start.get("stream_id") or stream_id
                call_id = (
                    start.get("call_control_id")
                    or start.get("call_session_id")
                    or start.get("call_leg_id")
                    or call_id
                )
                cust_phone = (
                    str(start.get("to") or start.get("from") or "")
                    if mode == "outbound"
                    else str(start.get("from") or start.get("to") or "")
                )
                call_history.start_call(
                    call_id=call_id,
                    direction="outbound" if mode == "outbound" else "inbound",
                    provider="telnyx",
                    customer_phone=cust_phone,
                )
                sample_rate = int(media_format.get("sample_rate") or sample_rate)
                codec = media_format.get("encoding") or codec
                log(
                    f"[{call_id}] Telnyx stream started: {stream_id} "
                    f"{codec} {sample_rate}Hz"
                )
                log(
                    f"[{call_id}] Telnyx realtime mode: explicit_vad=True "
                    f"speech_threshold={config.telnyx.speech_threshold} "
                )
                
                # Initialize recorder
                from app.call_recording import CallRecorder
                to_phone = (
                    str(start.get("from") or start.get("to") or "")
                    if mode == "outbound"
                    else str(start.get("to") or start.get("from") or "")
                )
                recorder = CallRecorder(
                    call_id=call_id,
                    sample_rate=sample_rate,
                    phone_number=cust_phone,
                    to_number=to_phone,
                    stream_id=stream_id,
                    codec=codec,
                    direction="outbound" if mode == "outbound" else "inbound",
                )

                input_gate_options = _telnyx_input_gate_options(mode)
                speech_start_frames = input_gate_options["speech_start_frames"]
                speech_end_silence_frames = input_gate_options["speech_end_silence_frames"]
                log(
                    f"[{call_id}] Telnyx VAD gate: "
                    f"speech_start_frames={speech_start_frames} "
                    f"speech_end_silence_frames={speech_end_silence_frames} "
                    f"adaptive_threshold={config.telnyx.adaptive_threshold}"
                )

                async def clear_audio() -> None:
                    await websocket.send_json(
                        {
                            "event": "clear",
                            "stream_id": stream_id,
                        }
                    )
                    log(f"[{call_id}] Sent Telnyx clear event")

                bridge_options = _telnyx_bridge_options(mode)
                bridge = GeminiCallBridge(
                    call_id=call_id,
                    call_sample_rate=sample_rate,
                    send_audio=send_audio,
                    clear_audio=clear_audio,
                    explicit_vad=True,
                    send_initial_greeting=bridge_options["send_initial_greeting"],
                    realtime_input=True,
                    system_instruction=bridge_options["system_instruction"],
                    on_transcript=_store_transcript(call_id),
                    on_audio_turn=_telnyx_audio_turn_handler(call_id),
                )
                input_gate = RealtimeInputGate(
                    bridge,
                    call_id,
                    speech_threshold=input_gate_options["speech_threshold"],
                    speech_start_frames=speech_start_frames,
                    speech_end_silence_frames=speech_end_silence_frames,
                    require_initial_turn=input_gate_options["require_initial_turn"],
                    wait_for_turn_before_commit=input_gate_options["wait_for_turn_before_commit"],
                    adaptive_threshold=input_gate_options["adaptive_threshold"],
                    noise_multiplier=input_gate_options["noise_multiplier"],
                    noise_margin=input_gate_options["noise_margin"],
                    barge_in_threshold=input_gate_options["barge_in_threshold"],
                    echo_suppression_ms=input_gate_options["echo_suppression_ms"],
                )
                await bridge.start()

            elif event_type == "media":
                if not bridge:
                    continue
                media = event.get("media") or {}
                timestamp_ms = int(media.get("timestamp") or 0)
                raw = base64.b64decode(media.get("payload") or "")
                inbound_frame_count += 1
                pcm = telnyx_payload_to_pcm16(raw, codec)
                rms = audioop.rms(pcm, 2)
                if inbound_frame_count <= 3 or inbound_frame_count % 100 == 0:
                    log(
                        f"[{call_id}] Telnyx inbound media "
                        f"{inbound_frame_count} ({len(raw)} bytes {codec}, "
                        f"timestamp={timestamp_ms}ms, rms={rms})"
                    )

                if recorder:
                    recorder.write_inbound(pcm)

                if input_gate:
                    await input_gate.push(pcm, rms, timestamp_ms)

            elif event_type == "stop":
                log(f"[{call_id}] Telnyx stream stopped")
                if input_gate:
                    await input_gate.force_end()
                if bridge:
                    await bridge.end_input_audio()
                break

            elif event_type == "dtmf":
                log(f"[{call_id}] Telnyx DTMF: {event.get('dtmf')}")

            elif event_type == "mark":
                pass

            elif event_type == "error":
                log(f"[{call_id}] Telnyx error: {event}")

            else:
                log(f"[{call_id}] Telnyx event: {event}")

    except WebSocketDisconnect:
        log(f"[{call_id}] Telnyx WebSocket disconnected")
    finally:
        if recorder:
            recorder.close()
        await _finalize_call(bridge, call_id)


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
                call_history.start_call(
                    call_id=call_id,
                    direction="inbound",
                    provider="signalwire",
                    customer_phone=str(start.get("from") or ""),
                )
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
                    on_transcript=_store_transcript(call_id),
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
        await _finalize_call(bridge, call_id)


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
                    call_history.start_call(
                        call_id=call_id,
                        direction="inbound",
                        provider="infobip",
                        customer_phone=str(event.get("from") or event.get("caller") or ""),
                    )
                    sample_rate = extract_sample_rate(event.get("content-type"), sample_rate)
                    print(f"[{call_id}] Infobip WebSocket connected at {sample_rate}Hz", flush=True)

                    bridge = GeminiCallBridge(
                        call_id=call_id,
                        call_sample_rate=sample_rate,
                        send_audio=send_audio,
                        on_transcript=_store_transcript(call_id),
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
        await _finalize_call(bridge, call_id)


def _public_ws_url(path: str) -> str:
    public_base_url = config.public_base_url
    if not public_base_url:
        public_base_url = "http://localhost:3000"
    parsed = urlparse(urljoin(public_base_url.rstrip("/") + "/", path.lstrip("/")))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _public_http_url(path: str) -> str:
    public_base_url = config.public_base_url
    if not public_base_url:
        public_base_url = "http://localhost:3000"
    parsed = urlparse(urljoin(public_base_url.rstrip("/") + "/", path.lstrip("/")))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _telnyx_greeting_audio_path() -> Path:
    path = Path(getattr(config.telnyx, "greeting_audio_path", "assets/telnyx-greeting.wav"))
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path
