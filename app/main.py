import base64
import asyncio
import audioop
import httpx
import json
from collections import deque
from html import escape
from pathlib import Path
from urllib.parse import parse_qsl
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.parse import urljoin, urlparse, urlunparse
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
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
from app.config import config, gemini_initial_greeting, gemini_system_instruction
from app.database import init_db
from app.gemini_bridge import GeminiCallBridge
from app.live_order_state import clean_recipient_name
from app.logging_utils import log
import re
from app.google_sheets import fetch_and_parse_google_sheet, map_sheet_row
from app.sheet_prompts import build_outbound_sheet_greeting, build_outbound_sheet_prompt
from app.admin import router as admin_router
from app.phone_numbers import normalize_phone_number
from app.recording_manager import latest_recording_for_call, recording_path_for_call

app = FastAPI(title="Viber Gemini Live Bridge")
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize the recordings database tables
init_db()

call_history = CallHistoryStore(config.database_url)
app.state.call_history = call_history
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
        phone_speech_end_silence_frames: int | None = None,
        address_speech_end_silence_frames: int | None = None,
        prebuffer_frames: int = 10,
        require_initial_turn: bool = True,
        wait_for_turn_before_commit: bool = True,
        adaptive_threshold: bool = False,
        noise_multiplier: float = 3.0,
        noise_margin: int = 80,
        barge_in_threshold: int | None = None,
        allow_barge_in: bool = False,
        echo_suppression_ms: int = 700,
        campaign_confirmation_mode: bool = False,
        confirmation_max_speech_frames: int = 1000,
        confirmation_phone_max_speech_frames: int = 750,
        confirmation_address_max_speech_frames: int = 1500,
        phone_confirmation_speech_threshold: int = 140,
        phone_confirmation_speech_start_frames: int = 2,
    ):
        self.bridge = bridge
        self.call_id = call_id
        self.speech_threshold = speech_threshold
        self.speech_start_frames = speech_start_frames
        self.speech_end_silence_frames = speech_end_silence_frames
        self.phone_speech_end_silence_frames = (
            phone_speech_end_silence_frames or speech_end_silence_frames
        )
        self.address_speech_end_silence_frames = (
            address_speech_end_silence_frames or speech_end_silence_frames
        )
        self.require_initial_turn = require_initial_turn
        self.wait_for_turn_before_commit = wait_for_turn_before_commit
        self.adaptive_threshold = adaptive_threshold
        self.noise_multiplier = noise_multiplier
        self.noise_margin = noise_margin
        self.barge_in_threshold = barge_in_threshold or speech_threshold
        self.allow_barge_in = allow_barge_in
        self.echo_suppression_seconds = echo_suppression_ms / 1000
        self.campaign_confirmation_mode = campaign_confirmation_mode
        self.confirmation_max_speech_frames = confirmation_max_speech_frames
        self.confirmation_phone_max_speech_frames = confirmation_phone_max_speech_frames
        self.confirmation_address_max_speech_frames = confirmation_address_max_speech_frames
        self.phone_confirmation_speech_threshold = phone_confirmation_speech_threshold
        self.phone_confirmation_speech_start_frames = phone_confirmation_speech_start_frames
        self.noise_floor = 0.0
        self.prebuffer: deque[bytes] = deque(maxlen=prebuffer_frames)
        self.speech_active = False
        self.waiting_for_response = False
        self.speech_frames = 0
        self.silence_frames = 0
        self.active_frames = 0
        self.active_speech_threshold = speech_threshold
        self.last_frame_bytes = 0

    async def push(self, pcm: bytes, rms: int, timestamp_ms: int | None = None) -> None:
        self.last_frame_bytes = len(pcm)
        if (
            getattr(self.bridge, "dtmf_digits", "")
            or getattr(self.bridge, "phone_readback_active", False)
        ):
            # Key tones and handset sidetone are not customer speech. Feeding
            # them to Gemini creates a competing response before # finishes.
            self.speech_frames = 0
            self.silence_frames = 0
            self.prebuffer.clear()
            return
        if self.speech_active:
            await self.bridge.send_input_audio(pcm)
            end_threshold = (
                self.active_speech_threshold
                if self.campaign_confirmation_mode
                else self.speech_threshold
            )
            if rms >= end_threshold:
                self.silence_frames = 0
            else:
                self.silence_frames += 1

            self.active_frames += 1
            if (
                self.campaign_confirmation_mode
                and self.active_frames >= self._max_speech_frames()
            ):
                log(f"[{self.call_id}] Confirmation speech turn reached its maximum duration")
                await self.force_end(timestamp_ms, flush_silence=False)
                return

            if self.silence_frames >= self._speech_end_silence_frames():
                await self.force_end(timestamp_ms, flush_silence=False)
            return

        if self.waiting_for_response:
            if self.bridge.turn_complete.is_set():
                self.waiting_for_response = False
            elif not self.allow_barge_in:
                self.speech_frames = 0
                self.prebuffer.clear()
                return
            elif rms < self.barge_in_threshold:
                self.speech_frames = 0
                self.prebuffer.clear()
                return
            else:
                self.waiting_for_response = False

        # If configured, wait for the initial AI greeting to finish before
        # listening. After that, strong caller speech is treated as barge-in.
        if self.require_initial_turn and self.bridge.completed_turn_count == 0:
            self.speech_frames = 0
            self.prebuffer.clear()
            return

        echo_suppression_seconds = (
            min(self.echo_suppression_seconds, 0.2)
            if getattr(
                self.bridge,
                "phone_readback_awaiting_confirmation",
                False,
            )
            else self.echo_suppression_seconds
        )
        output_recent = self.bridge.output_recent(echo_suppression_seconds)
        if self.campaign_confirmation_mode and output_recent:
            # Campaign prompts are short and contain values the customer must hear
            # exactly. Do not let handset echo clear or mute them.
            self.speech_frames = 0
            self.prebuffer.clear()
            return
        threshold = self._effective_threshold(output_recent=output_recent)
        awaiting_phone_confirmation = bool(
            getattr(
                self.bridge,
                "phone_readback_awaiting_confirmation",
                False,
            )
        )
        if awaiting_phone_confirmation and not output_recent:
            # The expected answer is often a very short, softly spoken yes/no.
            # Use a narrow, temporary threshold only for this confirmation turn.
            threshold = min(
                threshold,
                self.phone_confirmation_speech_threshold,
            )
        self.prebuffer.append(pcm)
        if rms >= threshold:
            self.speech_frames += 1
        else:
            self.speech_frames = 0
            self._update_noise_floor(rms, output_recent=output_recent)

        required_start_frames = (
            self.phone_confirmation_speech_start_frames
            if awaiting_phone_confirmation
            else self.speech_start_frames
        )
        if self.speech_frames < required_start_frames:
            return

        self.speech_active = True
        self.silence_frames = 0
        self.active_frames = 0
        self.active_speech_threshold = threshold
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
        self.active_frames = 0
        self.active_speech_threshold = self.speech_threshold
        self.prebuffer.clear()
        if flush_silence and self.last_frame_bytes:
            silence = b"\x00" * self.last_frame_bytes
            for _ in range(self._speech_end_silence_frames()):
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

    async def handle_dtmf(self, digit: str) -> None:
        """Close any accidental voice turn before processing keypad input."""
        digit = str(digit or "").strip()
        if digit not in "0123456789*#":
            return
        if self.speech_active:
            log(f"[{self.call_id}] Ending accidental speech activity for DTMF input")
            await self.force_end(flush_silence=False)
        self.speech_frames = 0
        self.silence_frames = 0
        self.prebuffer.clear()

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

    def _speech_end_silence_frames(self) -> int:
        collection_focus_recent = getattr(
            self.bridge,
            "collection_focus_recent",
            lambda *_args, **_kwargs: False,
        )
        if collection_focus_recent("phone"):
            return max(self.speech_end_silence_frames, self.phone_speech_end_silence_frames)
        if collection_focus_recent("address"):
            return max(self.speech_end_silence_frames, self.address_speech_end_silence_frames)
        return self.speech_end_silence_frames

    def _max_speech_frames(self) -> int:
        collection_focus_recent = getattr(
            self.bridge,
            "collection_focus_recent",
            lambda *_args, **_kwargs: False,
        )
        if collection_focus_recent("phone"):
            return self.confirmation_phone_max_speech_frames
        if collection_focus_recent("address"):
            return self.confirmation_address_max_speech_frames
        return self.confirmation_max_speech_frames

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


NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/admin")
async def admin_dashboard() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "index.html", headers=NO_CACHE_HEADERS)


@app.get("/admin/products")
async def admin_products() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "products.html", headers=NO_CACHE_HEADERS)


@app.get("/admin/recordings")
async def admin_recordings() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "recordings.html", headers=NO_CACHE_HEADERS)


@app.get("/admin/orders")
async def admin_orders() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "orders.html", headers=NO_CACHE_HEADERS)


app.include_router(admin_router)


def _call_counts(product_id: int | None = None) -> dict[str, int]:
    calls = call_history.list_calls(limit=500, product_id=product_id)
    return {
        "all": len(calls),
        "inbound": sum(1 for call in calls if call["direction"] == "inbound"),
        "outbound": sum(1 for call in calls if call["direction"] == "outbound"),
    }


def _interest_counts(product_id: int | None = None) -> dict[str, int]:
    stats = call_history.sales_statistics(product_id=product_id)
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
    if bridge and getattr(bridge, "campaign_confirmation_mode", False):
        await asyncio.to_thread(
            target_store.finish_call,
            call_id,
            confirmed_delivery_facts=bridge.delivery_state.confirmed_facts(),
            require_confirmed_delivery=True,
        )
    else:
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
    product_id: int | None = None,
    limit: int = 100,
) -> dict[str, object]:
    return {
        "calls": call_history.list_calls(
            direction=direction,
            query=q,
            interest_status=interest_status,
            product_id=product_id,
            limit=limit,
        ),
        "counts": _call_counts(product_id),
        "interest_counts": _interest_counts(product_id),
    }


@app.get("/api/orders")
async def api_orders(
    status: str | None = None,
    product_id: int | None = None,
    q: str = "",
    limit: int = 100,
) -> dict[str, object]:
    all_orders = call_history.list_orders(limit=limit, product_id=product_id)
    if status:
        all_orders = [o for o in all_orders if o.get("status") == status]
    if q.strip():
        needle = q.strip().casefold()
        all_orders = [
            o for o in all_orders
            if needle in str(o.get("customer_name") or "").casefold()
            or needle in str(o.get("customer_phone") or "").casefold()
            or needle in str(o.get("shipping_address") or "").casefold()
            or needle in str(o.get("product_name") or "").casefold()
        ]
    return {
        "ok": True,
        "count": len(all_orders),
        "orders": all_orders,
    }


@app.put("/api/orders/{order_id}")
async def api_update_order(order_id: int, payload: dict) -> dict[str, object]:
    updated = call_history.update_order(order_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"ok": True, "order": updated}


@app.get("/api/orders/export")
async def api_export_orders(status: str | None = None, product_id: int | None = None) -> Response:
    orders = call_history.list_orders(limit=500, product_id=product_id)
    if status:
        orders = [o for o in orders if o.get("status") == status]
    
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Mã Đơn", "Ngày tạo", "Họ tên khách", "SĐT", "Sản phẩm / Combo",
        "Số lượng", "Đơn giá (MMK)", "Tổng tiền (MMK)", "Địa chỉ giao hàng",
        "Trạng thái đóng gói", "Ghi chú"
    ])
    for o in orders:
        writer.writerow([
            o.get("id"),
            o.get("created_at"),
            o.get("customer_name"),
            o.get("customer_phone"),
            o.get("product_name"),
            o.get("quantity"),
            o.get("unit_price"),
            o.get("total_price"),
            o.get("shipping_address"),
            o.get("status"),
            o.get("missing_fields"),
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="orders-packing-manifest.csv"'},
    )


@app.get("/api/products")
async def api_products(active_only: bool = False) -> dict[str, object]:
    return {"products": call_history.list_products(active_only=active_only)}


@app.post("/api/products", status_code=201)
async def api_create_product(payload: dict) -> dict[str, object]:
    try:
        product = call_history.create_product(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"product": product}


@app.put("/api/products/{product_id}")
async def api_update_product(product_id: int, payload: dict) -> dict[str, object]:
    try:
        product = call_history.update_product(product_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"product": product}


@app.post("/api/products/{product_id}/default")
async def api_set_default_product(product_id: int) -> dict[str, object]:
    try:
        product = call_history.set_default_product(product_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"product": product}


@app.get("/api/calls/{call_id}")
async def api_call_detail(call_id: str) -> dict[str, object]:
    call = call_history.get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    call["recording"] = _call_recording_summary(call_id)
    return call


@app.get("/api/calls/{call_id}/recording/{file_kind}")
async def api_call_recording(call_id: str, file_kind: str) -> FileResponse:
    try:
        path = recording_path_for_call(call_id, file_kind)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Recording file not found")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


def _call_recording_summary(call_id: str) -> dict[str, object] | None:
    recording = latest_recording_for_call(call_id)
    if not recording:
        return None
    encoded_call_id = quote(call_id, safe="")
    files = {}
    for kind in ("mixed", "inbound", "outbound"):
        file_info = (recording.get("files") or {}).get(kind)
        if not file_info:
            files[kind] = None
            continue
        files[kind] = {
            "name": file_info.get("name", ""),
            "bytes": file_info.get("bytes", 0),
            "url": f"/api/calls/{encoded_call_id}/recording/{kind}",
        }
    return {
        "id": recording.get("id", ""),
        "status": recording.get("status", ""),
        "started_at": recording.get("started_at", ""),
        "ended_at": recording.get("ended_at", ""),
        "sample_rate": recording.get("sample_rate"),
        "files": files,
    }


@app.get("/api/admin/summary")
async def api_admin_summary(product_id: int | None = None) -> dict[str, object]:
    recent_leads = call_history.list_calls(
        interest_status="needs_consultation",
        product_id=product_id,
        limit=12,
    )
    recent_calls = call_history.list_calls(limit=12, product_id=product_id)
    return {
        "stats": call_history.sales_statistics(product_id=product_id),
        "recent_leads": recent_leads,
        "recent_calls": recent_calls,
    }


@app.get("/api/orders")
async def api_orders(
    limit: int = 100, product_id: int | None = None
) -> dict[str, object]:
    return {"orders": call_history.list_orders(limit=limit, product_id=product_id)}


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
    return normalize_phone_number(number)


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
        try:
            product_id = int(payload.get("product_id")) if payload.get("product_id") else None
        except (TypeError, ValueError):
            product_id = None
        call_history.update_outbound_request_by_call_sid(
            call_sid,
            call_status,
            dialed_phone=_normalize_phone_number(
                str(payload.get("To") or payload.get("to") or "")
            ),
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
            product_id=product_id,
        )
    return {"ok": True}


@app.api_route("/telnyx/answer", methods=["GET", "POST"])
async def telnyx_answer(request: Request) -> Response:
    payload = await _request_payload(request)
    requested_product = None
    if payload.get("product_id"):
        try:
            requested_product = call_history.get_product(int(payload["product_id"]))
        except (TypeError, ValueError):
            requested_product = None
    product = (
        requested_product
        or call_history.resolve_product_by_phone(str(payload.get("To") or payload.get("to") or ""))
        or call_history.get_default_product()
    )
    stream_params = {}
    if product:
        stream_params["product_id"] = product["id"]
    stream_url = _public_ws_url(
        f"/telnyx/ws?{urlencode(stream_params)}" if stream_params else "/telnyx/ws"
    )
    status_url = _public_http_url("/telnyx/status")
    stream_track = getattr(config.telnyx, "stream_track", "inbound_track")
    pause_length_seconds = getattr(config.telnyx, "pause_length_seconds", 600)
    if config.telnyx.stream_token:
        separator = "&" if "?" in stream_url else "?"
        stream_url = f"{stream_url}{separator}{urlencode({'token': config.telnyx.stream_token})}"

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
async def telnyx_outbound_answer(request: Request) -> Response:
    payload = await _request_payload(request)
    try:
        product_id = int(payload.get("product_id")) if payload.get("product_id") else None
    except (TypeError, ValueError):
        product_id = None
    request_id = payload.get("request_id") or request.query_params.get("request_id") or ""
    product = call_history.get_product(product_id) if product_id is not None else None
    product = product or call_history.get_default_product()
    
    query_params = {}
    if product:
        query_params["product_id"] = product["id"]
    if request_id:
        query_params["request_id"] = str(request_id)
        
    product_query = urlencode(query_params) if query_params else ""
    stream_url = _public_ws_url(
        f"/telnyx/outbound/ws?{product_query}" if product_query else "/telnyx/outbound/ws"
    )
    status_url = _public_http_url(
        f"/telnyx/outbound/status?{product_query}" if product_query else "/telnyx/outbound/status"
    )
    stream_track = getattr(config.telnyx, "stream_track", "inbound_track")
    pause_length_seconds = getattr(config.telnyx, "pause_length_seconds", 600)
    greeting_delay_seconds = max(
        0,
        int(getattr(config.telnyx, "outbound_greeting_delay_seconds", 2)),
    )
    if config.telnyx.stream_token:
        separator = "&" if "?" in stream_url else "?"
        stream_url = f"{stream_url}{separator}{urlencode({'token': config.telnyx.stream_token})}"

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


async def _send_queued_outbound_request(
    outbound_request: dict[str, object],
    product: dict[str, object],
) -> dict[str, object]:
    """Send one already-persisted outbound request to Telnyx."""
    request_id = int(outbound_request["id"])
    to_number = _normalize_phone_number(str(outbound_request.get("to_number") or ""))
    from_number = _normalize_phone_number(str(
        outbound_request.get("from_number")
        or product.get("phone_number")
        or config.telnyx.outbound_from_number
        or ""
    ))
    if not to_number:
        detail = "Missing to_number"
        call_history.mark_outbound_request_failed(request_id, detail)
        raise HTTPException(status_code=400, detail=detail)
    if not from_number:
        detail = "Missing from_number or TELNYX_OUTBOUND_FROM_NUMBER"
        call_history.mark_outbound_request_failed(request_id, detail)
        raise HTTPException(status_code=400, detail=detail)

    missing = [
        name
        for name, value in {
            "TELNYX_API_KEY": config.telnyx.api_key,
            "TELNYX_ACCOUNT_SID": config.telnyx.account_sid,
            "TELNYX_TEXML_APP_ID": product.get("texml_app_id") or config.telnyx.texml_app_id,
            "PUBLIC_BASE_URL": config.public_base_url,
        }.items()
        if not value
    ]
    if missing:
        detail = f"Missing config: {', '.join(missing)}"
        call_history.mark_outbound_request_failed(request_id, detail)
        raise HTTPException(status_code=500, detail=detail)

    product_query = urlencode({"product_id": product["id"], "request_id": request_id})
    body = {
        "ApplicationSid": product.get("texml_app_id") or config.telnyx.texml_app_id,
        "To": to_number,
        "From": from_number,
        "Url": _public_http_url(f"/telnyx/outbound/answer?{product_query}"),
        "UrlMethod": "POST",
        "StatusCallback": _public_http_url(f"/telnyx/outbound/status?{product_query}"),
        "StatusCallbackMethod": "POST",
    }
    url = f"https://api.telnyx.com/v2/texml/Accounts/{config.telnyx.account_sid}/Calls"
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
        call_history.mark_outbound_request_failed(request_id, detail)
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        detail = f"Telnyx request failed: {exc}"
        call_history.mark_outbound_request_failed(request_id, detail)
        raise HTTPException(status_code=502, detail=detail) from exc

    data = response.json()
    call_sid = data.get("sid") or data.get("call_sid") or (data.get("data") or {}).get("sid")
    started = call_history.mark_outbound_request_started_if_queued(
        request_id,
        call_sid or "",
    )
    if not started:
        call_history.mark_outbound_request_canceled(request_id, call_sid or "")
        if call_sid:
            try:
                await _hangup_telnyx_call(call_sid)
            except HTTPException as exc:
                log(
                    f"Canceled Sheet request {request_id} was accepted by Telnyx, "
                    f"but hangup failed: {exc.detail}"
                )
        return {
            "ok": False,
            "canceled": True,
            "call_sid": call_sid,
            "request": call_history.get_outbound_request(request_id),
        }
    log(
        f"Telnyx outbound call requested: request={request_id} "
        f"to={to_number} from={from_number} sid={call_sid}"
    )
    return {
        "ok": True,
        "call_sid": call_sid,
        "request": call_history.get_outbound_request(request_id),
        "product": {"id": product["id"], "name": product["name"]},
        "telnyx": data,
    }


CAMPAIGN_TERMINAL_REQUEST_STATUSES = {
    "completed",
    "no_answer",
    "busy",
    "canceled",
    "timed_out",
    "failed",
}


async def _wait_for_campaign_request_terminal(
    request_id: int,
    campaign_run_id: str,
    timeout_seconds: int,
) -> str:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        request = call_history.get_outbound_request(request_id)
        if not request:
            return "failed"
        request_status = str(request.get("status") or "")
        if request_status in CAMPAIGN_TERMINAL_REQUEST_STATUSES:
            return request_status
        run = call_history.get_campaign_run(campaign_run_id) if campaign_run_id else None
        if run and run.get("status") == "canceled":
            return "canceled"
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            call_sid = str(request.get("call_sid") or "")
            call_history.mark_outbound_request_timed_out(request_id)
            if call_sid:
                try:
                    await _hangup_telnyx_call(call_sid)
                except HTTPException as exc:
                    log(
                        f"Campaign request {request_id} timed out and hangup failed: "
                        f"{exc.detail}"
                    )
                    return "timeout_hangup_failed"
            return "timed_out"
        await asyncio.sleep(min(1.0, remaining))


async def _wait_campaign_gap(campaign_run_id: str, delay_seconds: int) -> bool:
    deadline = asyncio.get_running_loop().time() + delay_seconds
    while True:
        run = call_history.get_campaign_run(campaign_run_id) if campaign_run_id else None
        if run and run.get("status") == "canceled":
            return False
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return True
        await asyncio.sleep(min(1.0, remaining))


async def _dispatch_sheet_campaign(
    request_ids: list[int],
    delay_seconds: int,
    campaign_run_id: str = "",
    call_timeout_seconds: int = 480,
) -> None:
    """Call one Sheet lead at a time, then wait for its terminal callback."""
    if campaign_run_id:
        run = call_history.get_campaign_run(campaign_run_id)
        if run and run.get("status") == "canceled":
            return
        call_history.update_campaign_run_status(campaign_run_id, "running")
    for index, request_id in enumerate(request_ids):
        outbound_request = call_history.get_outbound_request(request_id)
        if not outbound_request or outbound_request.get("status") != "queued":
            continue
        product_id = outbound_request.get("product_id")
        product = call_history.get_product(int(product_id)) if product_id else None
        if not product or not product.get("active"):
            call_history.mark_outbound_request_failed(
                request_id,
                "Selected product is missing or inactive",
            )
        else:
            try:
                await _send_queued_outbound_request(outbound_request, product)
            except HTTPException as exc:
                log(
                    f"Sheet campaign request {request_id} failed: "
                    f"{exc.status_code} {exc.detail}"
                )

        terminal_status = await _wait_for_campaign_request_terminal(
            request_id,
            campaign_run_id,
            call_timeout_seconds,
        )
        if terminal_status == "timeout_hangup_failed":
            if campaign_run_id:
                call_history.cancel_campaign_run(campaign_run_id)
                call_history.update_campaign_run_status(campaign_run_id, "failed")
            return
        if terminal_status == "canceled":
            return
        if index < len(request_ids) - 1 and delay_seconds:
            should_continue = await _wait_campaign_gap(
                campaign_run_id,
                delay_seconds,
            )
            if not should_continue:
                return
    if campaign_run_id:
        run = call_history.get_campaign_run(campaign_run_id)
        if run and run.get("status") != "canceled":
            call_history.update_campaign_run_status(campaign_run_id, "completed")


def _sheet_campaign_phone_sets() -> tuple[set[str], set[str], set[str]]:
    """Separate active, campaign-called, and unrelated historical phones."""
    active: set[str] = set()
    campaign_called: set[str] = set()
    historical: set[str] = set()
    retry_resets = call_history.list_campaign_retry_resets()
    for request in call_history.list_outbound_requests(limit=2000):
        phone = normalize_phone_number(str(request.get("to_number") or ""))
        if not phone:
            continue
        if request.get("status") in {"queued", "started"}:
            active.add(phone)
        elif request.get("campaign_run_id") and request.get("call_sid"):
            if int(request.get("id") or 0) > int(retry_resets.get(phone, 0)):
                campaign_called.add(phone)
            else:
                historical.add(phone)
        elif request.get("campaign_run_id"):
            continue
        elif request.get("status") != "failed":
            historical.add(phone)
    for call in call_history.list_calls(direction="outbound", limit=500):
        phone = normalize_phone_number(
            str(call.get("dialed_phone") or call.get("customer_phone") or "")
        )
        if phone:
            historical.add(phone)
    return active, campaign_called, historical


def _classify_sheet_leads(
    leads: list[dict[str, object]],
    *,
    skip_sheet_called: bool,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    active_phones, campaign_called_phones, historical_phones = _sheet_campaign_phone_sets()
    counts = {
        "ready_count": 0,
        "duplicate_count": 0,
        "called_count": 0,
        "campaign_called_count": 0,
        "in_progress_count": 0,
        "historical_count": 0,
        "invalid_count": 0,
    }
    processed: list[dict[str, object]] = []
    for source in leads:
        lead = dict(source)
        clean_phone = normalize_phone_number(str(lead.get("phone") or ""))
        if lead.get("is_valid_phone") is False or not clean_phone:
            lead["status_tag"] = "invalid"
            lead["status_label"] = "SĐT không hợp lệ"
            counts["invalid_count"] += 1
        elif lead.get("is_duplicate"):
            lead["status_tag"] = "duplicate"
            lead["status_label"] = "Trùng lặp trong Sheet"
            counts["duplicate_count"] += 1
        elif clean_phone in active_phones:
            lead["status_tag"] = "in_progress"
            lead["status_label"] = "Đang chờ hoặc đang gọi"
            counts["in_progress_count"] += 1
        elif lead.get("called") and skip_sheet_called:
            lead["status_tag"] = "already_called"
            lead["status_label"] = "Sheet đã đánh dấu đã gọi"
            counts["called_count"] += 1
        elif clean_phone in campaign_called_phones:
            lead["status_tag"] = "campaign_called"
            lead["status_label"] = "Đã gọi trong chiến dịch"
            counts["campaign_called_count"] += 1
        elif clean_phone in historical_phones or lead.get("called"):
            lead["status_tag"] = "ready_previously_called"
            lead["status_label"] = "Sẵn sàng · Đã từng gọi"
            counts["ready_count"] += 1
            counts["historical_count"] += 1
        else:
            lead["status_tag"] = "ready"
            lead["status_label"] = "Sẵn sàng gọi"
            counts["ready_count"] += 1
        processed.append(lead)
    return processed, counts


def _campaign_status_summary(run_id: str) -> dict[str, object] | None:
    run = call_history.get_campaign_run(run_id)
    if not run:
        return None
    requests = call_history.list_campaign_run_requests(run_id)
    status_counts: dict[str, int] = {}
    for request in requests:
        request_status = str(request.get("status") or "unknown")
        status_counts[request_status] = status_counts.get(request_status, 0) + 1
    errors = [
        str(request.get("error") or "")
        for request in requests
        if request.get("error")
    ]
    return {
        "id": run_id,
        "status": run.get("status") or "preparing",
        "product_id": run.get("product_id"),
        "delay_seconds": int(run.get("delay_seconds") or 0),
        "call_timeout_seconds": int(run.get("call_timeout_seconds") or 480),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "total_count": len(requests),
        "status_counts": status_counts,
        "called_count": sum(1 for request in requests if request.get("call_sid")),
        "can_cancel": any(
            request.get("status") in {"queued", "started"} for request in requests
        ),
        "last_error": errors[-1] if errors else "",
    }


@app.post("/api/sheets/preview")
async def api_sheets_preview(payload: dict) -> dict:
    sheet_url = str(payload.get("sheet_url") or "").strip()
    if not sheet_url:
        raise HTTPException(status_code=400, detail="Missing sheet_url")
    raw_product_id = payload.get("product_id")
    try:
        product = (
            call_history.get_product(int(raw_product_id))
            if raw_product_id not in (None, "")
            else call_history.get_default_product()
        )
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid product_id")
    if not product or not product.get("active"):
        raise HTTPException(status_code=400, detail="Select an active product")
    skip_already_called = bool(payload.get("skip_already_called", True))
    try:
        leads = await fetch_and_parse_google_sheet(sheet_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    processed_leads, counts = _classify_sheet_leads(
        leads,
        skip_sheet_called=skip_already_called,
    )

    return {
        "ok": True,
        "campaign_run_id": uuid4().hex,
        "count": len(processed_leads),
        **counts,
        "product": {"id": product["id"], "name": product["name"]},
        "leads": processed_leads,
    }


@app.post("/api/sheets/launch-campaign")
async def api_sheets_launch_campaign(
    payload: dict,
    background_tasks: BackgroundTasks,
) -> dict:
    sheet_url = str(payload.get("sheet_url") or "").strip()
    leads = payload.get("leads") or []
    product_id = payload.get("product_id")
    from_number = str(payload.get("from_number") or "").strip()
    skip_already_called = bool(payload.get("skip_already_called", True))
    requested_run_id = str(payload.get("campaign_run_id") or "").strip()
    if requested_run_id and not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", requested_run_id):
        raise HTTPException(status_code=400, detail="Invalid campaign_run_id")
    campaign_run_id = requested_run_id or uuid4().hex
    try:
        delay_seconds = max(0, min(1800, int(payload.get("delay_seconds", 0) or 0)))
        call_timeout_seconds = max(
            60,
            min(1800, int(payload.get("call_timeout_seconds", 480) or 480)),
        )
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid campaign timing")

    if not leads and sheet_url:
        try:
            leads = await fetch_and_parse_google_sheet(sheet_url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not isinstance(leads, list) or not leads:
        raise HTTPException(status_code=400, detail="No valid leads found in Google Sheet")

    try:
        product = (
            call_history.get_product(int(product_id))
            if product_id not in (None, "")
            else call_history.get_default_product()
        )
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid product_id")
    if not product:
        raise HTTPException(status_code=400, detail="Product not found")
    if not product.get("active"):
        raise HTTPException(status_code=400, detail="Selected product is inactive")
    campaign_from_num = normalize_phone_number(
        from_number
        or product.get("phone_number")
        or config.telnyx.outbound_from_number
        or ""
    )
    if not campaign_from_num:
        raise HTTPException(
            status_code=400,
            detail="Selected product has no outbound phone number",
        )

    run, run_created = call_history.create_campaign_run(
        campaign_run_id,
        sheet_url=sheet_url,
        product_id=int(product["id"]),
        delay_seconds=delay_seconds,
        call_timeout_seconds=call_timeout_seconds,
    )
    if not run_created:
        if int(run.get("product_id") or 0) != int(product["id"]) or str(
            run.get("sheet_url") or ""
        ) != sheet_url:
            raise HTTPException(
                status_code=409,
                detail="campaign_run_id already belongs to another campaign",
            )
        existing_requests = call_history.list_campaign_run_requests(campaign_run_id)
        if not existing_requests:
            raise HTTPException(
                status_code=409,
                detail="Campaign run was not queued; preview the Sheet again",
            )
        return {
            "ok": True,
            "reused": True,
            "campaign_run_id": campaign_run_id,
            "count": len(existing_requests),
            "queued_count": len(existing_requests),
            "skipped_count": 0,
            "delay_seconds": int(run.get("delay_seconds") or 0),
            "call_timeout_seconds": int(run.get("call_timeout_seconds") or 480),
            "requests": existing_requests,
        }

    malformed_count = sum(1 for lead in leads if not isinstance(lead, dict))
    leads, _lead_counts = _classify_sheet_leads(
        [dict(lead) for lead in leads if isinstance(lead, dict)],
        skip_sheet_called=skip_already_called,
    )

    created_requests = []
    skipped_count = malformed_count + max(0, len(leads) - 500)
    campaign_leads = leads[:500]
    latest_phone_index: dict[str, int] = {}
    for index, lead in enumerate(campaign_leads):
        if isinstance(lead, dict):
            normalized = normalize_phone_number(str(lead.get("phone") or ""))
            if normalized:
                latest_phone_index[normalized] = index

    for index, lead in enumerate(campaign_leads):
        if not isinstance(lead, dict):
            skipped_count += 1
            continue
        to_number = normalize_phone_number(str(lead.get("phone") or ""))
        if not to_number or lead.get("status_tag") == "invalid":
            skipped_count += 1
            continue

        if latest_phone_index.get(to_number) != index:
            skipped_count += 1
            continue

        status_tag = lead.get("status_tag", "ready")
        if status_tag in {
            "invalid",
            "duplicate",
            "in_progress",
            "already_called",
            "campaign_called",
        }:
            skipped_count += 1
            continue

        prompt_override = build_outbound_sheet_prompt(lead, product)
        cust_name = str(lead.get("name") or "").strip()
        raw_row = lead.get("raw_row")
        customer_payload = dict(raw_row) if isinstance(raw_row, dict) else {}
        customer_payload["lead"] = {
            key: lead.get(key) or ""
            for key in (
                "name",
                "phone",
                "product",
                "offer",
                "quantity",
                "address",
                "notes",
            )
        }
        cust_json = json.dumps(
            customer_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        outbound_req = call_history.create_outbound_request(
            to_number=to_number,
            from_number=campaign_from_num,
            product_id=product["id"],
            prompt_override=prompt_override,
            customer_name=cust_name,
            customer_data_json=str(cust_json),
            campaign_run_id=campaign_run_id,
        )
        created_requests.append(outbound_req)

    if not created_requests:
        call_history.update_campaign_run_status(campaign_run_id, "failed")
        raise HTTPException(
            status_code=400,
            detail="No ready leads remain after validation and duplicate filtering",
        )

    background_tasks.add_task(
        _dispatch_sheet_campaign,
        [int(item["id"]) for item in created_requests],
        delay_seconds,
        campaign_run_id,
        call_timeout_seconds,
    )

    return {
        "ok": True,
        "reused": False,
        "campaign_run_id": campaign_run_id,
        "count": len(created_requests),
        "queued_count": len(created_requests),
        "skipped_count": skipped_count,
        "delay_seconds": delay_seconds,
        "call_timeout_seconds": call_timeout_seconds,
        "requests": created_requests,
    }


@app.get("/api/sheets/campaigns/active")
async def api_active_sheet_campaign() -> dict[str, object]:
    for run in call_history.list_campaign_runs(limit=50):
        summary = _campaign_status_summary(str(run["id"]))
        if summary and summary["can_cancel"]:
            return {"campaign": summary}
    return {"campaign": None}


@app.post("/api/sheets/campaigns/allow-retry")
async def api_allow_sheet_campaign_retry(payload: dict) -> dict[str, object]:
    raw_numbers = payload.get("phone_numbers")
    if not isinstance(raw_numbers, list):
        raw_numbers = [payload.get("phone_number")]
    phone_numbers: list[str] = []
    for raw_number in raw_numbers[:500]:
        phone = normalize_phone_number(str(raw_number or ""))
        if phone and phone not in phone_numbers:
            phone_numbers.append(phone)
    if not phone_numbers:
        raise HTTPException(status_code=400, detail="No valid phone numbers")
    resets = [
        call_history.allow_campaign_phone_retry(phone) for phone in phone_numbers
    ]
    return {
        "ok": True,
        "reset_count": len(resets),
        "resets": resets,
    }


@app.get("/api/sheets/campaigns/{run_id}")
async def api_sheet_campaign_status(run_id: str) -> dict[str, object]:
    summary = _campaign_status_summary(run_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Campaign run not found")
    return {"campaign": summary}


@app.post("/api/sheets/campaigns/{run_id}/cancel")
async def api_cancel_sheet_campaign(run_id: str) -> dict[str, object]:
    if not call_history.get_campaign_run(run_id):
        raise HTTPException(status_code=404, detail="Campaign run not found")
    canceled = call_history.cancel_campaign_run(run_id)
    hangup_errors: list[dict[str, str]] = []
    semaphore = asyncio.Semaphore(5)

    async def hangup(call_sid: str) -> None:
        async with semaphore:
            try:
                await _hangup_telnyx_call(call_sid)
            except HTTPException as exc:
                hangup_errors.append({"call_sid": call_sid, "error": str(exc.detail)})

    await asyncio.gather(
        *(hangup(call_sid) for call_sid in canceled["call_sids"]),
    )
    summary = _campaign_status_summary(run_id)
    return {
        "ok": True,
        "canceled_count": canceled["canceled_count"],
        "hangup_requested_count": len(canceled["call_sids"]),
        "hangup_errors": hangup_errors,
        "campaign": summary,
    }


@app.post("/telnyx/outbound/call")
async def telnyx_outbound_call(request: Request) -> dict[str, object]:
    payload = await request.json()
    raw_product_id = payload.get("product_id")
    try:
        product_id = int(raw_product_id) if raw_product_id not in (None, "") else None
    except (TypeError, ValueError):
        product_id = None
    product = (
        call_history.get_product(product_id)
        if product_id is not None
        else call_history.get_default_product()
    )
    if not product or not product["active"]:
        raise HTTPException(status_code=400, detail="Select an active product")
    to_number = _normalize_phone_number(str(payload.get("to_number") or ""))
    from_number = _normalize_phone_number(str(
        product.get("phone_number")
        or payload.get("from_number")
        or config.telnyx.outbound_from_number
        or ""
    ))
    prompt_override = str(payload.get("prompt_override") or "")
    customer_name = str(payload.get("customer_name") or "")
    customer_data_json = str(payload.get("customer_data_json") or "")

    if not to_number:
        raise HTTPException(status_code=400, detail="Missing to_number")
    if not from_number:
        outbound_request = call_history.create_outbound_request(
            to_number=to_number,
            product_id=product["id"],
            prompt_override=prompt_override,
            customer_name=customer_name,
            customer_data_json=customer_data_json,
        )
        call_history.mark_outbound_request_failed(
            outbound_request["id"],
            "Missing from_number or TELNYX_OUTBOUND_FROM_NUMBER",
        )
        raise HTTPException(status_code=400, detail="Missing from_number or TELNYX_OUTBOUND_FROM_NUMBER")

    outbound_request = call_history.create_outbound_request(
        to_number=to_number,
        from_number=from_number,
        product_id=product["id"],
        prompt_override=prompt_override,
        customer_name=customer_name,
        customer_data_json=customer_data_json,
    )

    missing = [
        name
        for name, value in {
            "TELNYX_API_KEY": config.telnyx.api_key,
            "TELNYX_ACCOUNT_SID": config.telnyx.account_sid,
            "TELNYX_TEXML_APP_ID": product.get("texml_app_id") or config.telnyx.texml_app_id,
            "PUBLIC_BASE_URL": config.public_base_url,
        }.items()
        if not value
    ]
    if missing:
        detail = f"Missing config: {', '.join(missing)}"
        call_history.mark_outbound_request_failed(outbound_request["id"], detail)
        raise HTTPException(status_code=500, detail=detail)

    url = f"https://api.telnyx.com/v2/texml/Accounts/{config.telnyx.account_sid}/Calls"
    product_query = urlencode({"product_id": product["id"], "request_id": outbound_request["id"]})
    texml_url = _public_http_url(f"/telnyx/outbound/answer?{product_query}")
    status_callback = _public_http_url(f"/telnyx/outbound/status?{product_query}")
    body = {
        "ApplicationSid": product.get("texml_app_id") or config.telnyx.texml_app_id,
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
        "product": {
            "id": product["id"],
            "name": product["name"],
        },
        "telnyx": data,
    }


async def _hangup_telnyx_call(call_sid: str) -> dict[str, object]:
    missing = [
        name
        for name, value in {
            "TELNYX_API_KEY": config.telnyx.api_key,
            "TELNYX_ACCOUNT_SID": config.telnyx.account_sid,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing config: {', '.join(missing)}")

    url = (
        f"https://api.telnyx.com/v2/texml/Accounts/{config.telnyx.account_sid}"
        f"/Calls/{quote(call_sid, safe='')}"
    )
    headers = {
        "Authorization": f"Bearer {config.telnyx.api_key}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=config.telnyx.outbound_call_timeout_seconds) as client:
            response = await client.post(url, data={"Status": "completed"}, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=_telnyx_error_detail(exc.response)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Telnyx request failed: {exc}") from exc

    data = response.json()
    log(f"Telnyx outbound call hangup requested: sid={call_sid}")
    return {"ok": True, "call_sid": call_sid, "telnyx": data}


@app.post("/telnyx/outbound/call/{call_sid}/hangup")
async def telnyx_hangup_outbound_call(call_sid: str) -> dict[str, object]:
    return await _hangup_telnyx_call(call_sid)


@app.get("/telnyx/greeting.wav")
async def telnyx_greeting() -> FileResponse:
    return FileResponse(_telnyx_greeting_audio_path(), media_type="audio/wav")


@app.websocket("/telnyx/outbound/ws")
async def telnyx_outbound_ws(websocket: WebSocket) -> None:
    await _telnyx_ws(websocket, mode="outbound")


@app.websocket("/telnyx/ws")
async def telnyx_ws(websocket: WebSocket) -> None:
    await _telnyx_ws(websocket, mode="inbound")


def _telnyx_bridge_options(
    mode: str,
    product: dict[str, object] | None = None,
    prompt_override: str | None = None,
    customer_name: str = "",
) -> dict[str, object]:
    system_instruction = gemini_system_instruction(mode, product=product)
    is_sheet_campaign = bool(prompt_override and prompt_override.strip())
    if is_sheet_campaign:
        system_instruction = (
            f"{system_instruction}\n\n"
            "The Sheet campaign workflow below specializes the generic outbound "
            "conversation for a pre-qualified order. It never overrides product "
            "facts, safety, phone, address, or final order-confirmation rules.\n"
            f"{prompt_override.strip()}"
        )
    initial_greeting = (
        build_outbound_sheet_greeting(customer_name, product)
        if mode == "outbound" and is_sheet_campaign
        else gemini_initial_greeting(mode, product=product)
    )
    initial_greeting = initial_greeting.replace(
        "{customer_name}",
        customer_name.strip(),
    )
    return {
        "send_initial_greeting": True,
        "initial_greeting": initial_greeting,
        "system_instruction": system_instruction,
        "language_code": product.get("language_code") if product else None,
        "voice_name": product.get("voice_name") if product else None,
    }


def _sheet_delivery_seed(
    outbound_request: dict[str, object] | None,
) -> dict[str, str]:
    if not outbound_request or not str(outbound_request.get("prompt_override") or "").strip():
        return {}

    raw_data: dict[str, object] = {}
    serialized = str(outbound_request.get("customer_data_json") or "").strip()
    if serialized:
        try:
            parsed = json.loads(serialized)
            if isinstance(parsed, dict):
                raw_data = parsed
        except (TypeError, ValueError):
            raw_data = {}

    normalized: dict[str, object] = {}
    embedded_lead = raw_data.get("lead")
    if isinstance(embedded_lead, dict):
        normalized = embedded_lead
    elif raw_data:
        normalized = map_sheet_row(
            {
                str(key): "" if value is None else str(value)
                for key, value in raw_data.items()
            }
        )

    raw_name = str(
        normalized.get("name")
        or outbound_request.get("customer_name")
        or ""
    ).strip()
    return {
        "customer_name": clean_recipient_name(raw_name),
        "phone": str(
            normalized.get("phone")
            or outbound_request.get("to_number")
            or ""
        ).strip(),
        "shipping_address": str(normalized.get("address") or "").strip(),
    }


def _telnyx_input_gate_options(mode: str) -> dict[str, object]:
    return {
        "speech_threshold": config.telnyx.speech_threshold,
        "speech_start_frames": getattr(config.telnyx, "speech_start_frames", 2),
        "speech_end_silence_frames": getattr(config.telnyx, "speech_end_silence_frames", 30),
        "phone_speech_end_silence_frames": getattr(
            config.telnyx,
            "phone_speech_end_silence_frames",
            getattr(config.telnyx, "speech_end_silence_frames", 30),
        ),
        "address_speech_end_silence_frames": getattr(
            config.telnyx,
            "address_speech_end_silence_frames",
            getattr(config.telnyx, "speech_end_silence_frames", 30),
        ),
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

    try:
        product_id = int(websocket.query_params.get("product_id") or 0) or None
    except ValueError:
        product_id = None
    product = call_history.get_product(product_id) if product_id is not None else None
    product = product or call_history.get_default_product()

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
                cust_phone = _normalize_phone_number(cust_phone)
                call_history.start_call(
                    call_id=call_id,
                    direction="outbound" if mode == "outbound" else "inbound",
                    provider="telnyx",
                    customer_phone=cust_phone if mode != "outbound" else "",
                    dialed_phone=cust_phone if mode == "outbound" else "",
                    product_id=product["id"] if product else None,
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
                to_phone = _normalize_phone_number(to_phone)
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

                request_id_str = websocket.query_params.get("request_id")
                outbound_req = None
                if request_id_str:
                    try:
                        outbound_req = call_history.get_outbound_request(int(request_id_str))
                    except (TypeError, ValueError):
                        outbound_req = None

                prompt_override = (outbound_req.get("prompt_override") or None) if outbound_req else None
                campaign_confirmation_mode = bool(
                    prompt_override and str(prompt_override).strip()
                )
                sheet_seed = _sheet_delivery_seed(outbound_req)
                campaign_customer_name = sheet_seed.get("customer_name", "")
                bridge_options = _telnyx_bridge_options(
                    mode,
                    product,
                    prompt_override=prompt_override,
                    customer_name=(
                        campaign_customer_name
                        if campaign_confirmation_mode
                        else (
                            (outbound_req.get("customer_name") or "")
                            if outbound_req
                            else ""
                        )
                    ),
                )
                bridge = GeminiCallBridge(
                    call_id=call_id,
                    call_sample_rate=sample_rate,
                    send_audio=send_audio,
                    clear_audio=clear_audio,
                    explicit_vad=True,
                    send_initial_greeting=bridge_options["send_initial_greeting"],
                    initial_greeting=bridge_options["initial_greeting"],
                    realtime_input=True,
                    system_instruction=bridge_options["system_instruction"],
                    language_code=bridge_options["language_code"],
                    voice_name=bridge_options["voice_name"],
                    on_transcript=_store_transcript(call_id),
                    on_audio_turn=_telnyx_audio_turn_handler(call_id),
                    connected_phone=cust_phone,
                    initial_customer_name=sheet_seed.get("customer_name", ""),
                    initial_phone=sheet_seed.get("phone", ""),
                    initial_shipping_address=sheet_seed.get("shipping_address", ""),
                    require_customer_name=campaign_confirmation_mode,
                    campaign_confirmation_mode=campaign_confirmation_mode,
                )
                input_gate = RealtimeInputGate(
                    bridge,
                    call_id,
                    speech_threshold=input_gate_options["speech_threshold"],
                    speech_start_frames=speech_start_frames,
                    speech_end_silence_frames=speech_end_silence_frames,
                    phone_speech_end_silence_frames=input_gate_options["phone_speech_end_silence_frames"],
                    address_speech_end_silence_frames=input_gate_options["address_speech_end_silence_frames"],
                    require_initial_turn=input_gate_options["require_initial_turn"],
                    wait_for_turn_before_commit=input_gate_options["wait_for_turn_before_commit"],
                    adaptive_threshold=input_gate_options["adaptive_threshold"],
                    noise_multiplier=input_gate_options["noise_multiplier"],
                    noise_margin=input_gate_options["noise_margin"],
                    barge_in_threshold=input_gate_options["barge_in_threshold"],
                    echo_suppression_ms=input_gate_options["echo_suppression_ms"],
                    campaign_confirmation_mode=campaign_confirmation_mode,
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
                if bridge:
                    dtmf = event.get("dtmf")
                    digit = dtmf.get("digit") if isinstance(dtmf, dict) else dtmf
                    if input_gate and hasattr(input_gate, "handle_dtmf"):
                        await input_gate.handle_dtmf(str(digit or ""))
                    await bridge.handle_dtmf(str(digit or ""))

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
                    customer_phone=_normalize_phone_number(str(start.get("from") or "")),
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
                    initial_greeting=gemini_initial_greeting("inbound"),
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
                if bridge:
                    dtmf = event.get("dtmf")
                    digit = dtmf.get("digit") if isinstance(dtmf, dict) else dtmf
                    if input_gate and hasattr(input_gate, "handle_dtmf"):
                        await input_gate.handle_dtmf(str(digit or ""))
                    await bridge.handle_dtmf(str(digit or ""))

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
                        customer_phone=_normalize_phone_number(
                            str(event.get("from") or event.get("caller") or "")
                        ),
                    )
                    sample_rate = extract_sample_rate(event.get("content-type"), sample_rate)
                    print(f"[{call_id}] Infobip WebSocket connected at {sample_rate}Hz", flush=True)

                    bridge = GeminiCallBridge(
                        call_id=call_id,
                        call_sample_rate=sample_rate,
                        send_audio=send_audio,
                        initial_greeting=gemini_initial_greeting("inbound"),
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
