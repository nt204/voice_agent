import asyncio
import base64
from contextlib import suppress
from typing import Awaitable, Callable

from google import genai
from google.genai import types

from app.audio import PcmFrameBuffer, extract_sample_rate, frame_bytes_for_pcm16, resample_pcm16_mono
from app.config import config, gemini_system_instruction, require_env
from app.logging_utils import log

SendAudio = Callable[[bytes], Awaitable[None]]


class GeminiCallBridge:
    def __init__(self, call_id: str, call_sample_rate: int, send_audio: SendAudio):
        self.call_id = call_id
        self.call_sample_rate = call_sample_rate
        self.gemini_input_sample_rate = config.gemini.input_sample_rate
        self.send_audio = send_audio
        self.client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
        self.session = None
        self.receiver_task: asyncio.Task | None = None
        self.output_frames = PcmFrameBuffer(frame_bytes_for_pcm16(call_sample_rate))
        self.output_frame_count = 0
        self.first_audio_sent = asyncio.Event()
        self.turn_complete = asyncio.Event()

    async def start(self) -> None:
        live = self.client.aio.live.connect(
            model=config.gemini.model,
            config=types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=config.gemini.voice_name,
                        )
                    )
                ),
                system_instruction=types.Content(
                    parts=[types.Part(text=gemini_system_instruction())]
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
                realtime_input_config=types.RealtimeInputConfig(
                    automatic_activity_detection=types.AutomaticActivityDetection(
                        disabled=False,
                        start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                        prefix_padding_ms=300,
                        silence_duration_ms=500,
                    ),
                    activity_handling=types.ActivityHandling.NO_INTERRUPTION,
                    turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
                ),
            ),
        )
        self.session = await live.__aenter__()
        self._live_context = live
        self.receiver_task = asyncio.create_task(self._receive_loop())
        log(f"[{self.call_id}] Gemini Live connected")
        await self.session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text=config.gemini.initial_greeting)],
            ),
            turn_complete=True,
        )
        try:
            await asyncio.wait_for(self.turn_complete.wait(), timeout=12)
        except asyncio.TimeoutError:
            log(f"[{self.call_id}] Initial greeting turn timeout")

    async def send_input_audio(self, pcm: bytes) -> None:
        if not self.session:
            return
        gemini_pcm = resample_pcm16_mono(
            pcm,
            self.call_sample_rate,
            self.gemini_input_sample_rate,
        )
        await self.session.send_realtime_input(
            media=types.Blob(
                data=gemini_pcm,
                mime_type=f"audio/pcm;rate={self.gemini_input_sample_rate}",
            )
        )

    async def end_input_audio(self) -> None:
        if not self.session:
            return
        await self.session.send_realtime_input(audio_stream_end=True)

    async def close(self) -> None:
        if self.receiver_task:
            self.receiver_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.receiver_task
        if getattr(self, "_live_context", None):
            await self._live_context.__aexit__(None, None, None)
        self.output_frames.clear()
        log(f"[{self.call_id}] Gemini Live closed")

    async def _receive_loop(self) -> None:
        assert self.session is not None

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
                        call_pcm = resample_pcm16_mono(pcm, gemini_rate, self.call_sample_rate)

                        for frame in self.output_frames.push(call_pcm):
                            await self.send_audio(frame)
                            self.output_frame_count += 1
                            self.first_audio_sent.set()
                            if self.output_frame_count <= 3 or self.output_frame_count % 50 == 0:
                                log(
                                    f"[{self.call_id}] Sent audio frame "
                                    f"{self.output_frame_count} ({len(frame)} bytes PCM)"
                                )

                if content.turn_complete:
                    log(f"[{self.call_id}] Gemini turn complete")
                    self.turn_complete.set()


def _inline_bytes(data: bytes | str) -> bytes:
    if isinstance(data, bytes):
        return data
    return base64.b64decode(data)
