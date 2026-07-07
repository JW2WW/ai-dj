"""Edge TTS voice catalog, aliases for retired voices, and fallback selection."""

# Voices confirmed working with the current edge-tts / Microsoft endpoint.
AVAILABLE_VOICES = [
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-US-AnaNeural",
    "en-US-AvaNeural",
    "en-US-EmmaNeural",
    "en-US-MichelleNeural",
    "en-US-GuyNeural",
    "en-US-BrianNeural",
    "en-US-ChristopherNeural",
    "en-US-RogerNeural",
    "en-US-EricNeural",
    "en-US-AndrewNeural",
]

DEFAULT_VOICE = "en-US-AriaNeural"

# Retired or unavailable ShortNames still stored in older DJ profiles.
VOICE_ALIASES: dict[str, str] = {
    "en-US-ArthurNeural": "en-US-ChristopherNeural",
    "en-US-JacobNeural": "en-US-EricNeural",
    "en-US-CoraNeural": "en-US-AvaNeural",
    "en-US-AmberNeural": "en-US-MichelleNeural",
    "en-US-AshleyNeural": "en-US-EmmaNeural",
    "en-US-ElizabethNeural": "en-US-AvaNeural",
    "en-US-MonicaNeural": "en-US-MichelleNeural",
}

MALE_VOICES = frozenset({
    "en-US-GuyNeural",
    "en-US-BrianNeural",
    "en-US-ChristopherNeural",
    "en-US-RogerNeural",
    "en-US-EricNeural",
    "en-US-AndrewNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-AndrewMultilingualNeural",
})

FEMALE_VOICES = frozenset({
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-US-AnaNeural",
    "en-US-AvaNeural",
    "en-US-EmmaNeural",
    "en-US-MichelleNeural",
    "en-US-AvaMultilingualNeural",
    "en-US-EmmaMultilingualNeural",
})

MALE_FALLBACKS = [
    "en-US-GuyNeural",
    "en-US-BrianNeural",
    "en-US-ChristopherNeural",
    "en-US-RogerNeural",
    "en-US-EricNeural",
]

FEMALE_FALLBACKS = [
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-US-AvaNeural",
    "en-US-EmmaNeural",
    "en-US-MichelleNeural",
]


def normalize_voice(voice: str | None) -> str:
    """Map retired voice names to a working replacement."""
    if not voice:
        return DEFAULT_VOICE
    return VOICE_ALIASES.get(voice, voice)


def fallback_voices(voice: str) -> list[str]:
    """Same-gender fallbacks only — never swap male DJ audio to a female voice."""
    if voice in MALE_VOICES:
        pool = MALE_FALLBACKS
    elif voice in FEMALE_VOICES:
        pool = FEMALE_FALLBACKS
    else:
        pool = [DEFAULT_VOICE, "en-US-GuyNeural"]

    seen = {voice}
    result: list[str] = []
    for candidate in pool:
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def synthesis_candidates(voice: str | None, rate: float) -> list[tuple[str, float]]:
    """Ordered voice/rate pairs to try for one TTS request."""
    primary = normalize_voice(voice)
    candidates: list[tuple[str, float]] = [(primary, rate)]
    if rate != 1.0:
        candidates.append((primary, 1.0))

    for fallback in fallback_voices(primary):
        candidates.append((fallback, rate))
        if rate != 1.0:
            candidates.append((fallback, 1.0))

    seen: set[tuple[str, float]] = set()
    ordered: list[tuple[str, float]] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered
