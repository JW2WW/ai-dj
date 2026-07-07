"""Quick check: which Edge TTS voices actually synthesize."""
import asyncio
from pathlib import Path

import edge_tts

TEST_VOICES = [
    "en-US-ArthurNeural",
    "en-US-JacobNeural",
    "en-US-CoraNeural",
    "en-US-AmberNeural",
    "en-US-ChristopherNeural",
    "en-US-RogerNeural",
    "en-US-EricNeural",
    "en-US-AndrewNeural",
    "en-US-BrianNeural",
    "en-US-GuyNeural",
    "en-US-AriaNeural",
    "en-US-JennyNeural",
]

OUT = Path(__file__).resolve().parent.parent / "data" / "voice_test"
OUT.mkdir(parents=True, exist_ok=True)


async def main() -> None:
    for voice in TEST_VOICES:
        path = OUT / f"{voice}.mp3"
        try:
            await edge_tts.Communicate("Hello, this is a voice test.", voice=voice).save(str(path))
            size = path.stat().st_size if path.exists() else 0
            status = "OK" if size > 0 else "EMPTY"
        except Exception as exc:
            status = f"FAIL ({exc})"
            size = 0
        print(f"{voice}: {status} ({size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
