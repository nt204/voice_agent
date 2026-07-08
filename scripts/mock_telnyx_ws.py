import argparse
import asyncio
import audioop
import base64
import json
import wave

import websockets


async def run(
    url: str,
    wav_path: str,
    out_path: str,
    stream_token: str | None,
    pre_silence_ms: int,
    post_silence_ms: int,
    encoding: str,
) -> None:
    with wave.open(wav_path, "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise RuntimeError("WAV must be mono PCM16")
        source_sample_rate = wav.getframerate()
        pcm = wav.readframes(wav.getnframes())
        sample_rate = 8000 if encoding in {"PCMU", "PCMA"} else source_sample_rate
        if source_sample_rate != sample_rate:
            pcm, _ = audioop.ratecv(pcm, 2, 1, source_sample_rate, sample_rate, None)
        frame_bytes = round(sample_rate * 0.02) * 2

    def encode_payload(pcm_frame: bytes) -> bytes:
        if encoding == "PCMU":
            return audioop.lin2ulaw(pcm_frame, 2)
        if encoding == "PCMA":
            return audioop.lin2alaw(pcm_frame, 2)
        if encoding == "L16":
            return audioop.byteswap(pcm_frame, 2)
        return pcm_frame

    headers = {}
    if stream_token:
        headers["x-telnyx-streaming-auth-token"] = stream_token

    received = bytearray()
    stream_id = "mock-telnyx-stream"

    async with websockets.connect(url, additional_headers=headers, max_size=None) as ws:
        connected = {"event": "connected", "version": "1.0.0"}
        if stream_token:
            connected["x-telnyx-streaming-auth-token"] = stream_token
        await ws.send(json.dumps(connected))
        await ws.send(
            json.dumps(
                {
                    "event": "start",
                    "sequence_number": "1",
                    "stream_id": stream_id,
                    "start": {
                        "call_control_id": "mock-telnyx-call",
                        "call_session_id": "mock-telnyx-session",
                        "from": "+13122010094",
                        "to": "+13122123456",
                        "media_format": {
                            "encoding": encoding,
                            "sample_rate": sample_rate,
                            "channels": 1,
                        },
                    },
                }
            )
        )

        async def receive_audio() -> None:
            async for message in ws:
                event = json.loads(message)
                if event.get("event") == "media":
                    payload = base64.b64decode(event["media"]["payload"])
                    received.extend(payload)
                    print(f"received {len(received)} bytes from bridge")

        receiver = asyncio.create_task(receive_audio())

        index = 1
        silence_payload = encode_payload(b"\x00" * frame_bytes)
        for _ in range(max(0, pre_silence_ms // 20)):
            await send_media(ws, stream_id, index, silence_payload)
            index += 1
            await asyncio.sleep(0.02)

        for offset in range(0, len(pcm), frame_bytes):
            await send_media(ws, stream_id, index, encode_payload(pcm[offset : offset + frame_bytes]))
            index += 1
            await asyncio.sleep(0.02)

        for _ in range(max(0, post_silence_ms // 20)):
            await send_media(ws, stream_id, index, silence_payload)
            index += 1
            await asyncio.sleep(0.02)

        await asyncio.sleep(12)
        await ws.send(
            json.dumps(
                {
                    "event": "stop",
                    "sequence_number": "999",
                    "stream_id": stream_id,
                    "stop": {"call_control_id": "mock-telnyx-call"},
                }
            )
        )
        receiver.cancel()

    with open(out_path, "wb") as file:
        file.write(received)

    print(f"Saved Gemini/bridge output RTP payloads to {out_path}")


async def send_media(ws, stream_id: str, index: int, payload: bytes) -> None:
    await ws.send(
        json.dumps(
            {
                "event": "media",
                "sequence_number": str(index + 1),
                "stream_id": stream_id,
                "media": {
                    "track": "inbound",
                    "chunk": str(index),
                    "timestamp": str((index - 1) * 20),
                    "payload": base64.b64encode(payload).decode("ascii"),
                },
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="ws://localhost:3000/telnyx/ws?token=change_me")
    parser.add_argument("--wav", required=True, help="Mono PCM16 WAV containing spoken input")
    parser.add_argument("--out", default="gemini-response-telnyx.pcm")
    parser.add_argument("--stream-token", default=None)
    parser.add_argument("--pre-silence-ms", type=int, default=10000)
    parser.add_argument("--post-silence-ms", type=int, default=3000)
    parser.add_argument("--encoding", default="PCMU", choices=["PCMU", "PCMA", "L16"])
    args = parser.parse_args()

    asyncio.run(
        run(
            args.url,
            args.wav,
            args.out,
            args.stream_token,
            args.pre_silence_ms,
            args.post_silence_ms,
            args.encoding,
        )
    )


if __name__ == "__main__":
    main()
