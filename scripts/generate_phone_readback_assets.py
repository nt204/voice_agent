import argparse
import asyncio
import subprocess
from pathlib import Path

import edge_tts


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "assets" / "phone_readback"
CLIPS = {
    "prefix": "ဖုန်းနံပါတ်က",
    "0": "သုည",
    "1": "တစ်",
    "2": "နှစ်",
    "3": "သုံး",
    "4": "လေး",
    "5": "ငါး",
    "6": "ခြောက်",
    "7": "ခုနစ်",
    "8": "ရှစ်",
    "9": "ကိုး",
    "confirm": "ဖြစ်ပါတယ်ရှင်။ နံပါတ် မှန်ပါသလားရှင်။",
}


async def _generate_clip(name: str, text: str, output_dir: Path, voice: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = output_dir / f".{name}.mp3"
    wav_path = output_dir / f"{name}.wav"
    await edge_tts.Communicate(text=text, voice=voice, rate="-8%").save(str(mp3_path))
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(mp3_path),
    ]
    if name != "confirm":
        command.extend(
            [
                "-af",
                (
                    "silenceremove=start_periods=1:start_silence=0.03:"
                    "start_threshold=-45dB:stop_periods=1:stop_silence=0.08:"
                    "stop_threshold=-45dB"
                ),
            ]
        )
    command.extend(
        [
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(wav_path),
        ]
    )
    subprocess.run(command, check=True)
    mp3_path.unlink(missing_ok=True)


async def generate(output_dir: Path, voice: str) -> None:
    for name, text in CLIPS.items():
        await _generate_clip(name, text, output_dir, voice)
        print(f"Generated {name}.wav", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic Burmese phone readback clips."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--voice", default="my-MM-NilarNeural")
    args = parser.parse_args()
    asyncio.run(generate(args.output_dir, args.voice))


if __name__ == "__main__":
    main()
