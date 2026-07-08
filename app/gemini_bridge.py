import asyncio
import audioop
import base64
from contextlib import suppress
from typing import Awaitable, Callable

from google import genai
from google.genai import types

from app.audio import PcmFrameBuffer, extract_sample_rate, frame_bytes_for_pcm16
from app.config import config, gemini_system_instruction, require_env
from app.logging_utils import log

SendAudio = Callable[[bytes], Awaitable[None]]


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


def _speech_config() -> types.SpeechConfig:
    return types.SpeechConfig(
        language_code=config.gemini.language_code,
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=config.gemini.voice_name,
            )
        ),
    )


class GeminiCallBridge:
    def __init__(
        self,
        call_id: str,
        call_sample_rate: int,
        send_audio: SendAudio,
        explicit_vad: bool = False,
        send_initial_greeting: bool = True,
        realtime_input: bool = False,
    ):
        self.call_id = call_id
        self.call_sample_rate = call_sample_rate
        self.gemini_input_sample_rate = config.gemini.input_sample_rate
        self.send_audio = send_audio
        self.explicit_vad = explicit_vad
        self.send_initial_greeting = send_initial_greeting
        self.realtime_input = realtime_input
        self.input_activity_active = False
        self.client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
        self.session = None
        self.receiver_task: asyncio.Task | None = None
        self.output_frames = PcmFrameBuffer(frame_bytes_for_pcm16(call_sample_rate))
        self.output_frame_count = 0
        self.first_audio_sent = asyncio.Event()
        self.turn_complete = asyncio.Event()
        self.input_resample_state = None
        self.output_resample_state_by_rate: dict[int, object] = {}
        self.input_turn_buffer = bytearray()
        self.output_muted = False
        self.completed_turn_count = 0
        self.last_output_at = 0.0

    async def start(self) -> None:
        live = self.client.aio.live.connect(
            model=config.gemini.model,
            config=types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                temperature=0.35,
                max_output_tokens=180,
                speech_config=_speech_config(),
                system_instruction=types.Content(
                    parts=[types.Part(text=gemini_system_instruction())]
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
                realtime_input_config=types.RealtimeInputConfig(
                    automatic_activity_detection=_automatic_activity_detection(self.explicit_vad),
                    activity_handling=types.ActivityHandling.NO_INTERRUPTION,
                    turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
                ),
            ),
        )
        self.session = await live.__aenter__()
        self._live_context = live
        self.receiver_task = asyncio.create_task(self._receive_loop())
        log(f"[{self.call_id}] Gemini Live connected")
        if not self.send_initial_greeting:
            return
        await self.session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "Hãy nói đúng nguyên văn câu sau, không thêm nội dung khác: "
                            f"{config.gemini.initial_greeting}"
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

    def set_output_muted(self, muted: bool) -> None:
        if self.output_muted == muted:
            return
        self.output_muted = muted
        if muted:
            self.output_frames.clear()
        log(f"[{self.call_id}] Gemini output {'muted' if muted else 'unmuted'}")

    def output_recent(self, seconds: float = 1.0) -> bool:
        if not self.last_output_at:
            return False
        return asyncio.get_running_loop().time() - self.last_output_at < seconds

    async def start_input_activity(self) -> None:
        if not self.session or not self.explicit_vad or self.input_activity_active:
            return
        await self.session.send_realtime_input(activity_start=types.ActivityStart())
        self.input_activity_active = True
        log(f"[{self.call_id}] Gemini input activity started")

    async def end_input_activity(self) -> None:
        if not self.session or not self.explicit_vad or not self.input_activity_active:
            return
        await self.session.send_realtime_input(activity_end=types.ActivityEnd())
        self.input_activity_active = False
        log(f"[{self.call_id}] Gemini input activity ended")

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
        await self._stop_receiver()
        if getattr(self, "_live_context", None):
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
            async for response in self.session.receive():
                content = response.server_content
                if content:
                    if content.input_transcription and content.input_transcription.text:
                        log(f"[{self.call_id}] User: {content.input_transcription.text}")
                    if content.output_transcription and content.output_transcription.text:
                        log(f"[{self.call_id}] Gemini: {content.output_transcription.text}")

                    model_turn = content.model_turn
                    if model_turn and model_turn.parts:
                        for part in model_turn.parts:
                            inline = part.inline_data
                            if not inline or not inline.data:
                                continue

                            gemini_rate = extract_sample_rate(inline.mime_type, 24000)
                            pcm = _inline_bytes(inline.data)
                            call_pcm = self._resample_output(pcm, gemini_rate)

                            for frame in self.output_frames.push(call_pcm):
                                if self.output_muted:
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

                    if content.turn_complete:
                        self.completed_turn_count += 1
                        log(f"[{self.call_id}] Gemini turn complete")
                        self.turn_complete.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log(f"[{self.call_id}] Gemini receive loop error: {type(exc).__name__}: {exc}")


def _inline_bytes(data: bytes | str) -> bytes:
    if isinstance(data, bytes):
        return data
    return base64.b64decode(data)
