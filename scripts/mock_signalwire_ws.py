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
    bearer_token: str | None,
    pre_silence_ms: int,
    post_silence_ms: int,
    encoding: str,
) -> None:
    with wave.open(wav_path, "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise RuntimeError("WAV must be mono PCM16")
        source_sample_rate = wav.getframerate()
        pcm = wav.readframes(wav.getnframes())
        sample_rate = 8000 if encoding == "audio/x-mulaw" else source_sample_rate
        if source_sample_rate != sample_rate:
            pcm, _ = audioop.ratecv(pcm, 2, 1, source_sample_rate, sample_rate, None)
        frame_bytes = round(sample_rate * 0.02) * 2

    def encode_payload(pcm_frame: bytes) -> bytes:
        if encoding == "audio/x-mulaw":
            return audioop.lin2ulaw(pcm_frame, 2)
        if encoding == "audio/x-L16":
            return audioop.byteswap(pcm_frame, 2)
        return pcm_frame

    headers = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    received = bytearray()
    stream_sid = "mock-stream"

    async with websockets.connect(url, additional_headers=headers, max_size=None) as ws:
        await ws.send(json.dumps({"event": "connected", "protocol": "Call", "version": "0.2.0"}))
        await ws.send(
            json.dumps(
                {
                    "event": "start",
                    "sequenceNumber": "1",
                    "start": {
                        "streamSid": stream_sid,
                        "callSid": "mock-signalwire-call",
                        "tracks": ["inbound"],
                        "mediaFormat": {
                            "encoding": encoding,
                            "sampleRate": sample_rate,
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
            await ws.send(
                json.dumps(
                    {
                        "event": "media",
                        "sequenceNumber": str(index + 1),
                        "media": {
                            "track": "inbound",
                            "chunk": str(index),
                            "timestamp": str((index - 1) * 20),
                            "payload": base64.b64encode(silence_payload).decode("ascii"),
                        },
                    }
                )
            )
            index += 1
            await asyncio.sleep(0.02)

        for offset in range(0, len(pcm), frame_bytes):
            await ws.send(
                json.dumps(
                    {
                        "event": "media",
                        "sequenceNumber": str(index + 1),
                        "media": {
                            "track": "inbound",
                            "chunk": str(index),
                            "timestamp": str((index - 1) * 20),
                            "payload": base64.b64encode(
                                encode_payload(pcm[offset : offset + frame_bytes])
                            ).decode("ascii"),
                        },
                    }
                )
            )
            index += 1
            await asyncio.sleep(0.02)

        for _ in range(max(0, post_silence_ms // 20)):
            await ws.send(
                json.dumps(
                    {
                        "event": "media",
                        "sequenceNumber": str(index + 1),
                        "media": {
                            "track": "inbound",
                            "chunk": str(index),
                            "timestamp": str((index - 1) * 20),
                            "payload": base64.b64encode(silence_payload).decode("ascii"),
                        },
                    }
                )
            )
            index += 1
            await asyncio.sleep(0.02)

        await asyncio.sleep(12)
        await ws.send(json.dumps({"event": "stop", "sequenceNumber": "999"}))
        receiver.cancel()

    with open(out_path, "wb") as file:
        file.write(received)

    print(f"Saved Gemini/bridge output PCM to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="ws://localhost:3000/signalwire/ws")
    parser.add_argument("--wav", required=True, help="Mono PCM16 WAV containing spoken input")
    parser.add_argument("--out", default="gemini-response-signalwire.pcm")
    parser.add_argument("--bearer-token", default=None)
    parser.add_argument("--pre-silence-ms", type=int, default=10000)
    parser.add_argument("--post-silence-ms", type=int, default=3000)
    parser.add_argument("--encoding", default="audio/x-mulaw")
    args = parser.parse_args()

    asyncio.run(
        run(
            args.url,
            args.wav,
            args.out,
            args.bearer_token,
            args.pre_silence_ms,
            args.post_silence_ms,
            args.encoding,
        )
    )


if __name__ == "__main__":
    main()
