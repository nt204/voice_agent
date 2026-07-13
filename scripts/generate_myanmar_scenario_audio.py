import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import edge_tts


BASE_DIR = Path(__file__).resolve().parent.parent
SCENARIO_TEST_PATH = BASE_DIR / "tests" / "test_myanmar_call_scenarios.py"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _load_scenarios() -> list[dict]:
    spec = importlib.util.spec_from_file_location("myanmar_call_scenarios", SCENARIO_TEST_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load scenarios from {SCENARIO_TEST_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SCENARIOS


async def _synthesize(text: str, output_path: Path, voice: str, rate: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(output_path))


async def generate_audio(output_dir: Path, voice: str, rate: str) -> list[dict]:
    manifest: list[dict] = []
    for scenario in _load_scenarios():
        scenario_dir = output_dir / scenario["id"]
        for index, (speaker, text) in enumerate(scenario["turns"], start=1):
            if speaker != "customer":
                continue
            filename = f"{index:02d}-{speaker}.mp3"
            output_path = scenario_dir / filename
            await _synthesize(text, output_path, voice, rate)
            manifest.append(
                {
                    "scenario_id": scenario["id"],
                    "turn_index": index,
                    "speaker": speaker,
                    "text": text,
                    "voice": voice,
                    "path": str(output_path.relative_to(BASE_DIR)),
                }
            )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Myanmar customer audio fixtures for sales call scenarios."
    )
    parser.add_argument(
        "--output-dir",
        default=str(BASE_DIR / "test_artifacts" / "myanmar_audio"),
        help="Directory for generated MP3 files and manifest.",
    )
    parser.add_argument("--voice", default="my-MM-NilarNeural")
    parser.add_argument("--rate", default="+0%")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = asyncio.run(
        generate_audio(
            output_dir=Path(args.output_dir),
            voice=args.voice,
            rate=args.rate,
        )
    )
    print(f"Generated {len(manifest)} audio files in {args.output_dir}")


if __name__ == "__main__":
    main()
