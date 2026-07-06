import argparse
import asyncio
import json
import wave

import websockets


async def run(url: str, wav_path: str, out_path: str) -> None:
    with wave.open(wav_path, "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise RuntimeError("WAV must be mono PCM16")
        sample_rate = wav.getframerate()
        frame_bytes = round(sample_rate * 0.02) * 2
        pcm = wav.readframes(wav.getnframes())

    received = bytearray()

    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(
            json.dumps(
                {
                    "event": "websocket:connected",
                    "callId": "mock-call",
                    "content-type": f"audio/l16;rate={sample_rate}",
                }
            )
        )

        async def receive_audio() -> None:
            async for message in ws:
                if isinstance(message, bytes):
                    received.extend(message)
                    print(f"received {len(received)} bytes from bridge")

        receiver = asyncio.create_task(receive_audio())

        for offset in range(0, len(pcm), frame_bytes):
            await ws.send(pcm[offset : offset + frame_bytes])
            await asyncio.sleep(0.02)

        await ws.send(json.dumps({"event": "mock:audio_end"}))
        await asyncio.sleep(12)
        receiver.cancel()

    with open(out_path, "wb") as file:
        file.write(received)

    print(f"Saved Gemini/bridge output PCM to {out_path}")
    print("If this file has bytes, the Infobip WebSocket -> Gemini -> WebSocket path works.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="ws://localhost:3000/infobip/ws?token=...")
    parser.add_argument("--wav", required=True, help="Mono PCM16 WAV containing spoken input")
    parser.add_argument("--out", default="gemini-response.pcm")
    args = parser.parse_args()

    asyncio.run(run(args.url, args.wav, args.out))


if __name__ == "__main__":
    main()
