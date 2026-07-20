import asyncio
import audioop
import base64
import re
import wave
from contextlib import suppress
from typing import Awaitable, Callable

from google import genai
from google.genai import types

from app.audio import PcmFrameBuffer, extract_sample_rate, frame_bytes_for_pcm16
from app.config import config, gemini_system_instruction, require_env
from app.live_order_state import (
    DELIVERY_STATE_FUNCTION,
    LiveDeliveryState,
    delivery_state_tool,
)
from app.logging_utils import log
from app.phone_readback import phone_readback_frames
from app.sales_analysis import (
    _extract_phone_precise,
    _phone_comparison_digits,
    _turn_confirms_phone,
    _turn_rejects_latest_phone,
)

SendAudio = Callable[[bytes], Awaitable[None]]
TranscriptHandler = Callable[[str, str], Awaitable[None] | None]
PHONE_REPLACEMENT_RE = re.compile(
    r"(?:ဖုန်းနံပါတ်အသစ်|နံပါတ်အသစ်|ဖုန်းအသစ်|အသစ်ပေး|အသစ်ပြော|"
    r"new\s+(?:phone|number)|different\s+(?:phone|number)|another\s+(?:phone|number))",
    flags=re.IGNORECASE,
)


def _automatic_activity_detection(explicit_vad: bool) -> types.AutomaticActivityDetection:
    if explicit_vad:
        return types.AutomaticActivityDetection(disabled=True)
    return types.AutomaticActivityDetection(
        disabled=False,
        start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
        prefix_padding_ms=200,
        silence_duration_ms=350,
    )


def _activity_handling(allow_barge_in: bool) -> types.ActivityHandling:
    if allow_barge_in:
        return types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
    return types.ActivityHandling.NO_INTERRUPTION


def _speech_config() -> types.SpeechConfig:
    return types.SpeechConfig(
        language_code=config.gemini.language_code,
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=config.gemini.voice_name,
            )
        ),
    )


def _audio_transcription_config() -> types.AudioTranscriptionConfig:
    return types.AudioTranscriptionConfig()


class GeminiCallBridge:
    def __init__(
        self,
        call_id: str,
        call_sample_rate: int,
        send_audio: SendAudio,
        explicit_vad: bool = False,
        send_initial_greeting: bool = True,
        realtime_input: bool = False,
        clear_audio: Callable[[], Awaitable[None]] | None = None,
        system_instruction: str | None = None,
        initial_greeting: str | None = None,
        on_transcript: TranscriptHandler | None = None,
        on_audio_turn: Callable[[bytes, int, int, str], Awaitable[str]] | None = None,
    ):
        self.call_id = call_id
        self.call_sample_rate = call_sample_rate
        self.gemini_input_sample_rate = config.gemini.input_sample_rate
        self.send_audio = send_audio
        self.clear_audio = clear_audio
        self.explicit_vad = explicit_vad
        self.send_initial_greeting = send_initial_greeting
        self.system_instruction = system_instruction
        self.initial_greeting = initial_greeting
        self.on_transcript = on_transcript
        self.on_audio_turn = on_audio_turn
        self.current_turn_audio = bytearray()
        self.completed_turns_audio = []
        self.realtime_live_transcript_parts = []
        self.asr_tasks = []
        self.secondary_asr_results: dict[int, str] = {}
        self.transcript_finalized = False
        self.realtime_input = realtime_input
        self.input_activity_active = False
        self.client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
        self.session = None
        self.receiver_task: asyncio.Task | None = None
        self.output_frames = PcmFrameBuffer(frame_bytes_for_pcm16(call_sample_rate))
        self.output_frame_count = 0
        self.first_audio_sent = asyncio.Event()
        self.turn_complete = asyncio.Event()
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.playback_task: asyncio.Task | None = None
        self.input_resample_state = None
        self.output_resample_state_by_rate: dict[int, object] = {}
        self.input_turn_buffer = bytearray()
        self.output_muted = False
        self.completed_turn_count = 0
        self.last_output_at = 0.0
        self.last_model_activity_at = 0.0
        self.delivery_state = LiveDeliveryState()
        self.dtmf_digits = ""
        self.recorded_confirmed_facts: set[tuple[str, str]] = set()
        self.collection_focus = ""
        self.collection_focus_until = 0.0
        self.authoritative_phone = ""
        self.authoritative_phone_source = ""
        self.last_phone_capture_conflicted = False
        self.pending_authoritative_phone_readback = ""
        self.suppress_model_output_for_phone_readback = False

    async def start(self) -> None:
        live = self.client.aio.live.connect(
            model=config.gemini.model,
            config=types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                temperature=config.gemini.temperature,
                top_p=config.gemini.top_p,
                max_output_tokens=config.gemini.max_output_tokens,
                speech_config=_speech_config(),
                system_instruction=types.Content(
                    parts=[types.Part(text=self.system_instruction or gemini_system_instruction())]
                ),
                tools=[delivery_state_tool()],
                input_audio_transcription=_audio_transcription_config(),
                output_audio_transcription=_audio_transcription_config(),
                realtime_input_config=types.RealtimeInputConfig(
                    automatic_activity_detection=_automatic_activity_detection(self.explicit_vad),
                    activity_handling=_activity_handling(False),
                    turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
                ),
            ),
        )
        self.session = await live.__aenter__()
        self._live_context = live
        self.receiver_task = asyncio.create_task(self._receive_loop())
        self.playback_task = asyncio.create_task(self._playback_loop())
        log(f"[{self.call_id}] Gemini Live connected")
        if not self.send_initial_greeting:
            return
        await self.session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "အောက်ပါစာကြောင်းကို အတိအကျသာ ပြောပါ။ အခြားအကြောင်းအရာ မထည့်ပါနှင့်: "
                            f"{self.initial_greeting or config.gemini.initial_greeting}"
                        )
                    )
                ],
            ),
            turn_complete=True,
        )

    async def send_input_audio(self, pcm: bytes) -> None:
        if not self.session:
            return
        gemini_pcm = self._resample_input(pcm)
        if not gemini_pcm:
            return
        self.current_turn_audio.extend(gemini_pcm)
        if self.realtime_input:
            await self.session.send_realtime_input(
                audio=types.Blob(
                    data=gemini_pcm,
                    mime_type=f"audio/pcm;rate={self.gemini_input_sample_rate}",
                )
            )
            return
        self.input_turn_buffer.extend(gemini_pcm)

    async def commit_input_audio_turn(self) -> None:
        if self.realtime_input:
            return
        if not self.session or not self.input_turn_buffer:
            return
        audio = bytes(self.input_turn_buffer)
        self.input_turn_buffer.clear()
        self.input_resample_state = None
        self.turn_complete.clear()
        
        live_candidate = " ".join(self.realtime_live_transcript_parts).strip()
        turn_no = len(self.completed_turns_audio)
        self.completed_turns_audio.append((
            turn_no,
            audio,
            live_candidate
        ))
        
        if self.on_audio_turn and audio and self._needs_in_call_phone_asr(live_candidate):
            task = asyncio.create_task(
                self._process_audio_turn_correction(turn_no, audio, live_candidate)
            )
            self.asr_tasks.append(task)
            
        self.current_turn_audio.clear()
        self.realtime_live_transcript_parts.clear()
        
        await self._stop_receiver()
        await self.session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[
                    types.Part(
                        inline_data=types.Blob(
                            data=audio,
                            mime_type=f"audio/pcm;rate={self.gemini_input_sample_rate}",
                        )
                    )
                ],
            ),
            turn_complete=True,
        )
        self.receiver_task = asyncio.create_task(self._receive_loop())
        log(f"[{self.call_id}] Committed input audio turn ({len(audio)} bytes PCM)")

    async def set_output_muted(self, muted: bool) -> None:
        if self.output_muted == muted:
            return
        self.output_muted = muted
        if muted:
            await self._clear_pending_output_audio()
        log(f"[{self.call_id}] Gemini output {'muted' if muted else 'unmuted'}")

    async def _clear_pending_output_audio(self) -> None:
        self.output_frames.clear()
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except asyncio.QueueEmpty:
                break
        if self.clear_audio:
            await self.clear_audio()

    def output_recent(self, seconds: float = 1.0) -> bool:
        if not self.last_output_at:
            return False
        return asyncio.get_running_loop().time() - self.last_output_at < seconds

    def collection_focus_recent(self, focus: str, seconds: float = 20.0) -> bool:
        if self.collection_focus != focus or not self.collection_focus_until:
            return False
        now = asyncio.get_running_loop().time()
        return now <= self.collection_focus_until + seconds

    async def start_input_activity(self) -> None:
        if not self.session or not self.explicit_vad or self.input_activity_active:
            return
        self.suppress_model_output_for_phone_readback = False
        self.current_turn_audio.clear()
        self.realtime_live_transcript_parts.clear()
        self.turn_complete.clear()
        self.input_resample_state = None
        await self.session.send_realtime_input(activity_start=types.ActivityStart())
        self.input_activity_active = True
        log(f"[{self.call_id}] Gemini input activity started")

    async def end_input_activity(self) -> None:
        if not self.session or not self.explicit_vad or not self.input_activity_active:
            return
        await self.session.send_realtime_input(activity_end=types.ActivityEnd())
        self.input_activity_active = False
        log(f"[{self.call_id}] Gemini input activity ended")
        
        audio_bytes = bytes(self.current_turn_audio)
        live_candidate = " ".join(self.realtime_live_transcript_parts).strip()
        self._capture_authoritative_phone(
            live_candidate,
            source="Gemini Live transcript",
        )
        await self._flush_authoritative_phone_readback()
        if audio_bytes:
            turn_no = len(self.completed_turns_audio)
            self.completed_turns_audio.append((
                turn_no,
                audio_bytes,
                live_candidate
            ))
            
            if self.on_audio_turn and self._needs_in_call_phone_asr(live_candidate):
                # Phone ASR must finish before the call accepts the next customer
                # turn, otherwise a late Gemini correction can overlap later audio.
                await self._process_audio_turn_correction(
                    turn_no,
                    audio_bytes,
                    live_candidate,
                )
                
        self.current_turn_audio.clear()
        self.realtime_live_transcript_parts.clear()

    async def end_input_audio(self) -> None:
        if not self.session:
            return
        if self.realtime_input and self.explicit_vad and self.input_activity_active:
            await self.end_input_activity()
            return
        if self.realtime_input:
            await self.session.send_realtime_input(audio_stream_end=True)
            log(f"[{self.call_id}] Gemini realtime audio stream ended")
            return
        await self.commit_input_audio_turn()

    async def close(self) -> None:
        if self.playback_task:
            self.playback_task.cancel()
        await self._stop_receiver()
        if getattr(self, "_live_context", None):
            with suppress(Exception):
                await self._live_context.__aexit__(None, None, None)
        self.output_frames.clear()
        log(f"[{self.call_id}] Gemini Live closed")

    async def _stop_receiver(self) -> None:
        if not self.receiver_task:
            return
        self.receiver_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await self.receiver_task
        self.receiver_task = None

    async def _playback_loop(self) -> None:
        try:
            while True:
                frame = await self.audio_queue.get()
                if self.output_muted:
                    self.audio_queue.task_done()
                    continue

                self.last_output_at = asyncio.get_running_loop().time()
                await self.send_audio(frame)
                self.output_frame_count += 1
                self.first_audio_sent.set()
                if self.output_frame_count <= 3 or self.output_frame_count % 50 == 0:
                    log(
                        f"[{self.call_id}] Sent audio frame "
                        f"{self.output_frame_count} ({len(frame)} bytes PCM)"
                    )
                
                # frame length is 20ms
                await asyncio.sleep(0.019)
                self.audio_queue.task_done()
        except asyncio.CancelledError:
            pass

    def _resample_input(self, pcm: bytes) -> bytes:
        if self.call_sample_rate == self.gemini_input_sample_rate:
            return pcm
        if len(pcm) < 2:
            return b""
        converted, self.input_resample_state = audioop.ratecv(
            pcm,
            2,
            1,
            self.call_sample_rate,
            self.gemini_input_sample_rate,
            self.input_resample_state,
        )
        return converted

    def _resample_output(self, pcm: bytes, gemini_rate: int) -> bytes:
        if gemini_rate == self.call_sample_rate:
            return pcm
        if len(pcm) < 2:
            return b""
        state = self.output_resample_state_by_rate.get(gemini_rate)
        converted, state = audioop.ratecv(
            pcm,
            2,
            1,
            gemini_rate,
            self.call_sample_rate,
            state,
        )
        self.output_resample_state_by_rate[gemini_rate] = state
        return converted

    async def _receive_loop(self) -> None:
        assert self.session is not None

        try:
            while True:
                async for response in self.session.receive():
                    if response.tool_call:
                        await self._handle_tool_call(response.tool_call)
                    content = response.server_content
                    if content:
                        if content.input_transcription and content.input_transcription.text:
                            input_text = content.input_transcription.text
                            log(f"[{self.call_id}] User: {input_text}")
                            self.realtime_live_transcript_parts.append(input_text)
                            if (
                                self.on_audio_turn
                                and not self.delivery_state.phone_confirmed
                                and re.search(
                                    r"(?:ဖုန်းနံပါတ်|ဖုန်း|phone|mobile)",
                                    input_text,
                                    flags=re.IGNORECASE,
                                )
                            ):
                                self.suppress_model_output_for_phone_readback = True
                            await self._record_transcript("customer", input_text)
                            live_customer_text = " ".join(
                                self.realtime_live_transcript_parts
                            ).strip()
                            phone_changed = self._capture_authoritative_phone(
                                live_customer_text,
                                source="Gemini Live transcript",
                            )
                            if not self.last_phone_capture_conflicted:
                                await self._confirm_authoritative_phone_from_text(
                                    live_customer_text
                                )
                            if phone_changed and not self.input_activity_active:
                                await self._flush_authoritative_phone_readback()
                        if content.output_transcription and content.output_transcription.text:
                            self.last_model_activity_at = asyncio.get_running_loop().time()
                            log(f"[{self.call_id}] Gemini: {content.output_transcription.text}")
                            self._track_collection_focus(content.output_transcription.text)
                            if not self.suppress_model_output_for_phone_readback:
                                await self._record_transcript(
                                    "agent",
                                    content.output_transcription.text,
                                )

                         # model_turn = content.model_turn (note: keep standard block)
                        model_turn = content.model_turn
                        if model_turn and model_turn.parts:
                            for part in model_turn.parts:
                                inline = part.inline_data
                                if not inline or not inline.data:
                                    continue

                                self.last_model_activity_at = asyncio.get_running_loop().time()

                                gemini_rate = extract_sample_rate(inline.mime_type, 24000)
                                pcm = _inline_bytes(inline.data)
                                call_pcm = self._resample_output(pcm, gemini_rate)

                                for frame in self.output_frames.push(call_pcm):
                                    if (
                                        not self.output_muted
                                        and not self.suppress_model_output_for_phone_readback
                                    ):
                                        self.audio_queue.put_nowait(frame)

                        if content.turn_complete:
                            self.completed_turn_count += 1
                            log(f"[{self.call_id}] Gemini turn complete")
                            self.turn_complete.set()
                
                # Sleep briefly before restarting the receive loop to prevent tight loops
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log(f"[{self.call_id}] Gemini receive loop error: {type(exc).__name__}: {exc}")

    async def _record_transcript(self, speaker: str, text: str) -> None:
        if not self.on_transcript:
            return
        result = self.on_transcript(speaker, text)
        if asyncio.iscoroutine(result):
            await result

    async def _handle_tool_call(self, tool_call: types.LiveServerToolCall) -> None:
        if not self.session:
            return

        function_responses = []
        for function_call in tool_call.function_calls or []:
            if function_call.name != DELIVERY_STATE_FUNCTION:
                result = {"ok": False, "message": "Unsupported tool."}
            else:
                args = dict(function_call.args or {})
                field = str(args.get("field") or "")
                action = str(args.get("action") or "")
                value = str(args.get("value") or "")
                model_phone = (
                    _phone_comparison_digits(_extract_phone_precise(value))
                    if field == "phone"
                    else ""
                )
                authoritative_phone = _phone_comparison_digits(self.authoritative_phone)
                if (
                    field == "phone"
                    and action == "set"
                    and self.authoritative_phone
                    and model_phone != authoritative_phone
                ):
                    result = self.delivery_state.status_response(
                        ok=True,
                        message=(
                            "Ignored the model-heard phone number. The server ASR phone "
                            f"{self.authoritative_phone} is authoritative."
                        ),
                    )
                    log(
                        f"[{self.call_id}] Ignored model phone '{model_phone or value}'; "
                        f"server ASR phone is '{self.authoritative_phone}'"
                    )
                elif (
                    field == "phone"
                    and action == "set"
                    and self.authoritative_phone
                    and self.delivery_state.phone_confirmed
                ):
                    result = self.delivery_state.status_response(
                        ok=True,
                        message="The authoritative phone is already confirmed.",
                    )
                else:
                    if field == "phone" and action == "reject":
                        self.authoritative_phone = ""
                        self.authoritative_phone_source = ""
                        self.pending_authoritative_phone_readback = ""
                    result = self.delivery_state.apply(
                        field=field,
                        action=action,
                        value=value,
                    )
                if result["ok"] and action == "confirm":
                    await self._record_confirmed_fact(field)

            function_responses.append(
                types.FunctionResponse(
                    id=function_call.id,
                    name=function_call.name,
                    response=result,
                )
            )

        if function_responses:
            await self.session.send_tool_response(
                function_responses=function_responses,
            )

    def _track_collection_focus(self, text: str) -> None:
        clean_text = str(text or "").strip()
        if not clean_text:
            return
        now = asyncio.get_running_loop().time()
        if re.search(r"(?:ဖုန်းနံပါတ်|ဖုန်း|phone|mobile|keypad|ခလုတ်|#|hash)", clean_text, flags=re.IGNORECASE):
            self.collection_focus = "phone"
            self.collection_focus_until = now + 20.0
            return
        if re.search(r"(?:လိပ်စာ|ပို့ရမယ့်|ပို့ရန်|address|delivery|ship)", clean_text, flags=re.IGNORECASE):
            self.collection_focus = "address"
            self.collection_focus_until = now + 20.0

    def _needs_in_call_phone_asr(self, live_candidate: str) -> bool:
        if self.authoritative_phone and not self.delivery_state.phone_confirmed:
            return True
        if self.collection_focus_recent("phone"):
            return True
        return bool(
            _extract_phone_precise(live_candidate)
            or re.search(
                r"(?:ဖုန်းနံပါတ်|ဖုန်း|phone|mobile)",
                live_candidate,
                flags=re.IGNORECASE,
            )
        )

    async def _record_confirmed_fact(self, field: str) -> None:
        facts = self.delivery_state.confirmed_facts()
        value = facts.get(field, "")
        marker = (field, value)
        if not value or marker in self.recorded_confirmed_facts:
            return
        self.recorded_confirmed_facts.add(marker)
        label = "ဖုန်းနံပါတ်" if field == "phone" else "လိပ်စာ"
        await self._record_transcript("customer", f"{label} {value} မှန်ပါတယ်")

    async def handle_dtmf(self, digit: str) -> None:
        digit = str(digit or "").strip()
        if digit == "*":
            self.dtmf_digits = ""
            return
        if digit in "0123456789":
            if len(self.dtmf_digits) < 15:
                self.dtmf_digits += digit
            return
        if digit != "#" or not self.dtmf_digits:
            return

        phone = self.dtmf_digits
        self.dtmf_digits = ""
        result = self.delivery_state.apply(
            field="phone",
            action="set",
            value=phone,
        )
        if not result["ok"]:
            return
        self.authoritative_phone = self.delivery_state.phone
        self.authoritative_phone_source = "keypad"
        self.pending_authoritative_phone_readback = self.authoritative_phone

        text = f"ဖုန်းနံပါတ် {self.delivery_state.phone}"
        await self._record_transcript("customer", text)
        await self._flush_authoritative_phone_readback()

    async def _process_audio_turn_correction(
        self,
        turn_no: int,
        audio_bytes: bytes,
        live_candidate: str,
    ) -> None:
        try:
            corrected_text = await self.on_audio_turn(
                audio_bytes,
                self.gemini_input_sample_rate,
                turn_no,
                live_candidate
            )
            self.secondary_asr_results[turn_no] = corrected_text
            if corrected_text:
                was_confirmed = self.delivery_state.phone_confirmed
                phone_synced = await self._sync_phone_from_customer_text(corrected_text)
                phone_confirmed = False
                if not self.last_phone_capture_conflicted:
                    phone_confirmed = await self._confirm_authoritative_phone_from_text(
                        corrected_text
                    )
                if phone_confirmed and not was_confirmed:
                    if self.clear_audio:
                        await self.clear_audio()
                    if self.session:
                        await self.session.send_client_content(
                            turns=types.Content(
                                role="user",
                                parts=[
                                    types.Part(
                                        text=(
                                            "Server ASR confirms that the previously played phone "
                                            "number is correct. Never speak any phone digits. "
                                            "Acknowledge briefly and ask only for the shipping address."
                                        )
                                    )
                                ],
                            ),
                            turn_complete=True,
                        )
                    return
                if phone_synced:
                    return
            if corrected_text and corrected_text != live_candidate:
                log(f"[{self.call_id}] In-call corrected turn {turn_no}: '{live_candidate}' -> '{corrected_text}'")
                if self.clear_audio:
                    await self.clear_audio()
                if self.session:
                    await self.session.send_client_content(
                        turns=types.Content(
                            role="user",
                            parts=[types.Part(text=corrected_text)]
                        ),
                        turn_complete=True
                    )
        except Exception as e:
            log(f"[{self.call_id}] In-call turn ASR error: {e}")

    async def _sync_phone_from_customer_text(self, text: str) -> bool:
        phone = self._capture_authoritative_phone(
            text,
            source="secondary ASR",
        )
        if not phone:
            return False
        await self._flush_authoritative_phone_readback()
        return True

    async def _confirm_authoritative_phone_from_text(self, text: str) -> bool:
        if (
            not self.authoritative_phone
            or self.delivery_state.phone_confirmed
            or _turn_rejects_latest_phone(text)
            or not _turn_confirms_phone(text)
        ):
            return False
        has_phone_context = bool(
            re.search(r"(?:ဖုန်းနံပါတ်|ဖုန်း|phone|mobile)", text, flags=re.IGNORECASE)
            or _extract_phone_precise(text)
            or self.collection_focus_recent("phone", seconds=10.0)
        )
        if not has_phone_context:
            return False

        result = self.delivery_state.apply(field="phone", action="confirm")
        if not result["ok"]:
            return False
        await self._record_confirmed_fact("phone")
        self.suppress_model_output_for_phone_readback = False
        log(
            f"[{self.call_id}] Customer transcript confirmed authoritative phone "
            f"'{self.authoritative_phone}'"
        )
        return True

    def _capture_authoritative_phone(self, text: str, *, source: str) -> str:
        self.last_phone_capture_conflicted = False
        phone = _extract_phone_precise(text)
        if not phone:
            return ""

        comparison_phone = _phone_comparison_digits(phone)
        authoritative_phone = _phone_comparison_digits(self.authoritative_phone)
        if (
            authoritative_phone
            and comparison_phone != authoritative_phone
            and source == "Gemini Live transcript"
            and self.authoritative_phone_source in {"secondary ASR", "keypad"}
        ):
            self.last_phone_capture_conflicted = bool(
                _turn_rejects_latest_phone(text)
                or PHONE_REPLACEMENT_RE.search(text)
            )
            log(
                f"[{self.call_id}] Ignored lower-priority {source} phone "
                f"'{comparison_phone}'; {self.authoritative_phone_source} phone remains "
                f"'{self.authoritative_phone}'"
            )
            return self.authoritative_phone
        if (
            authoritative_phone
            and comparison_phone != authoritative_phone
            and not _turn_rejects_latest_phone(text)
            and not PHONE_REPLACEMENT_RE.search(text)
        ):
            self.last_phone_capture_conflicted = True
            log(
                f"[{self.call_id}] Ignored unconfirmed {source} phone "
                f"'{comparison_phone}'; authoritative phone remains "
                f"'{self.authoritative_phone}'"
            )
            return self.authoritative_phone
        if (
            comparison_phone == authoritative_phone
            and comparison_phone == _phone_comparison_digits(self.delivery_state.phone)
        ):
            if source == "secondary ASR":
                self.authoritative_phone_source = source
            return self.authoritative_phone

        result = self.delivery_state.apply(
            field="phone",
            action="set",
            value=phone,
        )
        if not result["ok"] or not self.delivery_state.phone:
            return ""

        self.authoritative_phone = self.delivery_state.phone
        self.authoritative_phone_source = source
        self.pending_authoritative_phone_readback = self.authoritative_phone
        log(
            f"[{self.call_id}] {source} set authoritative phone "
            f"'{self.authoritative_phone}'"
        )
        return self.authoritative_phone

    async def _flush_authoritative_phone_readback(self) -> None:
        phone = self.pending_authoritative_phone_readback
        if not phone:
            return
        self.pending_authoritative_phone_readback = ""
        digits = " ".join(phone)
        await self._clear_pending_output_audio()
        frames = []
        try:
            frames = phone_readback_frames(phone, self.call_sample_rate)
        except (FileNotFoundError, ValueError, wave.Error) as exc:
            log(f"[{self.call_id}] Deterministic phone readback unavailable: {exc}")
        self.suppress_model_output_for_phone_readback = bool(frames)
        if self.session and not frames:
            await self.session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=(
                                "System correction for the customer's latest speech: "
                                f"server ASR extracted the complete phone as {phone}. "
                                "This server value is authoritative. Discard every different phone "
                                "number inferred from audio or conversation memory. Call "
                                f"{DELIVERY_STATE_FUNCTION} with field=phone, action=set, and "
                                f"value={phone}. "
                                + (
                                    f"Then read exactly these digits one by one: {digits}. "
                                    "Ask only whether this exact number is correct."
                                )
                            )
                        )
                    ],
                ),
                turn_complete=True,
            )
        if frames:
            await self._record_transcript(
                "agent",
                f"ဖုန်းနံပါတ် {phone} မှန်ပါသလားရှင်။",
            )
            for frame in frames:
                await self.send_audio(frame)

    async def wait_for_audio_turns(self) -> None:
        if self.asr_tasks:
            await asyncio.gather(*self.asr_tasks, return_exceptions=True)
            self.asr_tasks.clear()

    async def run_post_call_asr(self, store) -> None:
        if not config.gemini.secondary_asr_enabled:
            return
        if not self.completed_turns_audio:
            return

        await self.wait_for_audio_turns()
        log(f"[{self.call_id}] Running post-call secondary ASR on {len(self.completed_turns_audio)} turns...")
        from app.secondary_asr import SecondaryAsrTranscriber

        missing_turns = [
            (turn_index, audio_bytes, self.gemini_input_sample_rate, live_candidate)
            for turn_index, audio_bytes, live_candidate in self.completed_turns_audio
            if turn_index not in self.secondary_asr_results
        ]
        if missing_turns:
            try:
                transcriber = SecondaryAsrTranscriber()
                self.secondary_asr_results.update(
                    await transcriber.transcribe_many(missing_turns)
                )
            except Exception as exc:
                log(f"[{self.call_id}] Post-call ASR batch failed: {type(exc).__name__}: {exc}")

        for turn_index, _, live_candidate in self.completed_turns_audio:
            if turn_index not in self.secondary_asr_results:
                continue
            corrected_text = self.secondary_asr_results[turn_index]
            if corrected_text != live_candidate:
                shown = corrected_text or "[unclear]"
                log(
                    f"[{self.call_id}] Post-call ASR finalized turn {turn_index}: "
                    f"'{live_candidate}' -> '{shown}'"
                )
            store.update_customer_transcript_by_index(
                self.call_id,
                turn_index,
                corrected_text,
            )

        log(
            f"[{self.call_id}] Final ASR transcript ready: "
            f"{len(self.secondary_asr_results)}/{len(self.completed_turns_audio)} turns"
        )

    async def finalize_transcript(self, store) -> None:
        if self.transcript_finalized:
            return
        await self.wait_for_audio_turns()
        # Freeze Live transcription before replacing customer turns with final ASR.
        await self._stop_receiver()
        await self.run_post_call_asr(store)
        self.transcript_finalized = True


def _inline_bytes(data: bytes | str) -> bytes:
    if isinstance(data, bytes):
        return data
    return base64.b64decode(data)
