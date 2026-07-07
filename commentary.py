"""Artist commentary: fetch facts (Wikipedia/MusicBrainz), condense via LLM, cache.

The raw source fact is pulled from a real page so the LLM is *summarizing*
rather than recalling trivia from memory (lower hallucination risk). Blurbs are
cached in SQLite keyed by artist so repeat plays don't re-hit the network or
burn LLM quota.
"""
import sqlite3
import threading
import time
from pathlib import Path

import requests

import logging
from llm_client import get_llm_client
from playlist import Track
from sqlite_db import open_db

# MusicBrainz requires a descriptive User-Agent; Wikipedia appreciates one too.
USER_AGENT = "AI-DJ/0.1 (personal radio project)"
WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/artist"
MB_RECORDING_URL = "https://musicbrainz.org/ws/2/recording"
MB_ARTIST_LOOKUP_URL = "https://musicbrainz.org/ws/2/artist/"
WIKIDATA_URL = "https://www.wikidata.org/w/api.php"

# MusicBrainz asks for <=1 request/second; keep a small gap between MB calls.
MB_MIN_INTERVAL = 1.1
_mb_last_call = 0.0
_mb_lock = threading.Lock()

# Below this many characters, a Wikipedia extract is treated as too thin and we
# fall back to MusicBrainz for structured info.
THIN_EXTRACT_CHARS = 120

# Spoken pace ~2.3 words/sec; used to turn a target duration into a word budget.
WORDS_PER_SECOND = 2.3

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS commentary_cache (
    artist TEXT PRIMARY KEY,
    blurb TEXT NOT NULL,
    source TEXT NOT NULL,
    artist_type TEXT,
    artist_gender TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


# Words that signal a Wikipedia page is about a musical act (person or group)
# rather than a place, song, or something else sharing the artist's name.
MUSIC_KEYWORDS = (
    "singer", "songwriter", "band", "musician", "rapper", "duo", "group",
    "guitarist", "vocalist", "drummer", "dj", "record producer", "pianist",
    "girl group", "boy band", "recording artist", "music",
)


def _wiki_summary(session: requests.Session, title: str) -> tuple[str, str] | None:
    """Return (extract, description) for a title, or None if missing/ambiguous."""
    try:
        r = session.get(WIKI_SUMMARY_URL + title.replace(" ", "_"), timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("type") == "disambiguation":
            return None
        extract = data.get("extract")
        if not extract:
            return None
        return extract, (data.get("description") or "")
    except (requests.RequestException, ValueError):
        return None


def _looks_musical(extract: str, description: str) -> bool:
    blob = f"{description} {extract[:200]}".lower()
    return any(kw in blob for kw in MUSIC_KEYWORDS)


def _wiki_artist_extract(session: requests.Session, artist: str) -> str | None:
    """Resolve an artist to a Wikipedia extract, trying the plain name first,
    then musical disambiguation suffixes so 'Alabama' -> the band, not the
    state, and 'Daft Punk' -> the duo, not the 'Get Lucky' single."""
    # 1. Plain name — accept only if it actually reads as a musical act.
    direct = _wiki_summary(session, artist)
    if direct and _looks_musical(*direct):
        return direct[0]

    # 2. Disambiguation suffixes for names shared with places/other things.
    for suffix in ("(band)", "(musician)", "(singer)", "(group)"):
        result = _wiki_summary(session, f"{artist} {suffix}")
        if result and _looks_musical(*result):
            return result[0]

    # 3. Fall back to the plain-name extract even if unconfirmed, so a real
    #    (if imperfect) page still beats nothing.
    return direct[0] if direct else None


def _musicbrainz_facts(session: requests.Session, artist: str) -> tuple[str, str | None, str | None] | None:
    """Structured fallback: type, country, active years, tags/genres."""
    params = {"query": f'artist:"{artist}"', "fmt": "json", "limit": 1}
    try:
        r = session.get(MUSICBRAINZ_URL, params=params, timeout=10)
        r.raise_for_status()
        artists = r.json().get("artists", [])
        if not artists:
            return None
        a = artists[0]
        bits = [a.get("name", artist)]
        artist_type = a.get("type")
        artist_gender = a.get("gender")

        if artist_type:
            bits.append(f"({artist_type})")
        if a.get("country"):
            bits.append(f"from {a['country']}")
        life = a.get("life-span", {})
        if life.get("begin"):
            span = f"active since {life['begin']}"
            if life.get("end"):
                span = f"active {life['begin']}–{life['end']}"
            bits.append(span)
        tags = [t["name"] for t in a.get("tags", [])[:3]] if a.get("tags") else []
        if tags:
            bits.append("genres: " + ", ".join(tags))
        return " ".join(bits), artist_type, artist_gender
    except (requests.RequestException, KeyError, ValueError):
        return None


def _mb_get(session: requests.Session, url: str, params: dict) -> dict | None:
    """Rate-limited MusicBrainz GET returning parsed JSON, or None."""
    global _mb_last_call
    with _mb_lock:
        wait = MB_MIN_INTERVAL - (time.monotonic() - _mb_last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            r = session.get(url, params={**params, "fmt": "json"}, timeout=10)
            _mb_last_call = time.monotonic()
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            _mb_last_call = time.monotonic()
            return None


def _mb_resolve_artist_mbid(session, artist: str, title: str | None) -> str | None:
    """Find the canonical MusicBrainz artist MBID. When a song title is known,
    disambiguate via the recording so 'Sylvia' + 'Nobody' resolves to the
    country singer, not an unrelated band sharing the name."""
    if title:
        data = _mb_get(session, MB_RECORDING_URL,
                       {"query": f'recording:"{title}" AND artist:"{artist}"', "limit": 3})
        for rec in (data or {}).get("recordings", []):
            for credit in rec.get("artist-credit", []):
                a = credit.get("artist") if isinstance(credit, dict) else None
                if a and a.get("id"):
                    return a["id"]
    data = _mb_get(session, MUSICBRAINZ_URL, {"query": f'artist:"{artist}"', "limit": 1})
    artists = (data or {}).get("artists", [])
    return artists[0]["id"] if artists else None


def _mb_wikipedia_title(session: requests.Session, mbid: str) -> str | None:
    """Follow an artist's MusicBrainz URL relations to an English Wikipedia
    title, resolving through Wikidata when only a Wikidata link is present."""
    data = _mb_get(session, MB_ARTIST_LOOKUP_URL + mbid, {"inc": "url-rels"})
    if not data:
        return None
    wikidata_id = None
    for rel in data.get("relations", []):
        rtype = rel.get("type")
        resource = rel.get("url", {}).get("resource", "")
        if rtype == "wikipedia" and "en.wikipedia.org/wiki/" in resource:
            return resource.rsplit("/wiki/", 1)[1].replace("_", " ")
        if rtype == "wikidata" and "wikidata.org/wiki/" in resource:
            wikidata_id = resource.rsplit("/wiki/", 1)[1]
    if wikidata_id:
        return _wikidata_enwiki_title(session, wikidata_id)
    return None


def _wikidata_enwiki_title(session: requests.Session, qid: str) -> str | None:
    params = {"action": "wbgetentities", "ids": qid, "props": "sitelinks",
              "sitefilter": "enwiki", "format": "json"}
    try:
        r = session.get(WIKIDATA_URL, params=params, timeout=10)
        r.raise_for_status()
        entity = r.json().get("entities", {}).get(qid, {})
        return entity.get("sitelinks", {}).get("enwiki", {}).get("title")
    except (requests.RequestException, ValueError, KeyError):
        return None


def fetch_artist_source(artist: str, title: str | None = None) -> tuple[str | None, str | None, str | None]:
    """Best available factual source text for an artist, or None.
    Also returns artist_type and artist_gender if available.
    """
    session = _session()
    artist_type = None
    artist_gender = None
    source_blurb = None

    # Gold path: let the song title pin down the exact artist, then follow the
    # canonical link to Wikipedia.
    mbid = _mb_resolve_artist_mbid(session, artist, title)
    if mbid:
        mb_data = _mb_get(session, MB_ARTIST_LOOKUP_URL + mbid, {"inc": "url-rels"})
        if mb_data:
            artist_type = mb_data.get("type")
            artist_gender = mb_data.get("gender")

        wiki_title = _mb_wikipedia_title(session, mbid)
        if wiki_title:
            result = _wiki_summary(session, wiki_title)
            if result and len(result[0]) >= THIN_EXTRACT_CHARS:
                source_blurb = result[0]
                return source_blurb, artist_type, artist_gender

    # Heuristic path: plain name + musical disambiguation suffixes.
    extract = _wiki_artist_extract(session, artist)
    if extract and len(extract) >= THIN_EXTRACT_CHARS:
        source_blurb = extract
        return source_blurb, artist_type, artist_gender

    # MusicBrainz structured facts as a last resort.
    mb_facts_result = _musicbrainz_facts(session, artist) # This now returns a tuple (facts_string, type, gender)
    if mb_facts_result:
        mb_facts_string, mb_type, mb_gender = mb_facts_result
        if mb_type:
            artist_type = mb_type
        if mb_gender:
            artist_gender = mb_gender

        if extract and mb_facts_string:  # Wikipedia was thin — enrich with structured facts.
            source_blurb = f"{extract} ({mb_facts_string})"
        elif mb_facts_string:
            source_blurb = mb_facts_string
        else:
            source_blurb = extract # Keep the extract if no MB facts.
    else:
        source_blurb = extract # No MB facts, just use extract if available.

    return source_blurb, artist_type, artist_gender


class CommentaryGenerator:
    def __init__(self, db_path: Path, llm=None, target_seconds: int = 18):
        self.conn, self._db_lock = open_db(db_path, check_same_thread=False)
        with self._db_lock:
            self.conn.executescript(CACHE_SCHEMA)
            self.conn.commit()
        self.llm = llm or get_llm_client()
        self.target_seconds = target_seconds

    def _cached(self, artist: str) -> tuple[str, str | None, str | None] | None:
        """Return (blurb, artist_type, artist_gender) from cache, or None if not found."""
        with self._db_lock:
            # Check if artist_type/gender columns exist; if not, return only blurb
            cursor = self.conn.execute("PRAGMA table_info(commentary_cache)")
            columns = [col[1] for col in cursor.fetchall()]
            has_type_gender = "artist_type" in columns and "artist_gender" in columns

            if has_type_gender:
                row = self.conn.execute(
                    "SELECT blurb, artist_type, artist_gender FROM commentary_cache WHERE artist = ?", (artist,)
                ).fetchone()
                if row:
                    return row["blurb"], row["artist_type"], row["artist_gender"]
            else:
                row = self.conn.execute(
                    "SELECT blurb FROM commentary_cache WHERE artist = ?", (artist,)
                ).fetchone()
                if row:
                    return row["blurb"], None, None # If columns don't exist, return None for type/gender
        return None

    def _store(self, artist: str, blurb: str, source: str, artist_type: str | None, artist_gender: str | None) -> None:
        with self._db_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO commentary_cache (artist, blurb, source, artist_type, artist_gender) "
                "VALUES (?, ?, ?, ?, ?)",
                (artist, blurb, source, artist_type, artist_gender),
            )
            self.conn.commit()

    def _condense(self, artist: str, source: str) -> str:
        word_budget = int(self.target_seconds * WORDS_PER_SECOND)
        # The blurb is cached per artist and reused across all of that artist's
        # songs, so it must NOT name a specific track — it's pure artist
        # trivia. The player announces the actual song separately.
        prompt = (
            f"You are an upbeat radio DJ. Using ONLY the facts below, write a "
            f"single spoken blurb of about {word_budget} words about the "
            f"artist {artist} to say on air as a lead-in to one of their "
            f"songs. Work in one genuinely interesting fact. Do NOT name any "
            f"specific song or album, since this intro is reused for several "
            f"of their tracks. Do NOT add a generic lead-in like 'here they "
            f"are' — the song title is announced separately right after. End "
            f"on the interesting fact. Sound natural and warm, no stage "
            f"directions, no quotation marks.\n\nFACTS:\n{source}"
        )
        max_tokens = max(80, int(word_budget * 2.2))
        return self.llm.generate(prompt, max_tokens=max_tokens).strip().strip('"')

    def get_commentary(self, track: Track, use_cache: bool = True) -> tuple[str | None, str | None, str | None]:
        """Return (blurb, artist_type, artist_gender) for the track's artist, or (None, None, None) if we
        have no facts (e.g. 'Unknown Artist' clips)."""
        artist = track.artist
        if artist.lower().startswith("unknown"):
            return None, None, None

        if use_cache:
            cached_result = self._cached(artist)
            if cached_result:
                logging.debug(f"[Commentary] Returning cached blurb for {artist}.")
                return cached_result

        source, artist_type, artist_gender = fetch_artist_source(artist, track.title)
        if not source:
            logging.debug(f"[Commentary] No source facts found for {artist}.")
            return None, artist_type, artist_gender # Still return type/gender if available

        logging.debug(f"[Commentary] Condensing new blurb for {artist} from source ({len(source)} chars).")
        blurb = self._condense(artist, source)
        if blurb:
            self._store(artist, blurb, source, artist_type, artist_gender)
            logging.debug(f"[Commentary] New blurb stored for {artist} (length: {len(blurb)}).")
        else:
            logging.debug(f"[Commentary] No blurb condensed for {artist}.")
        return blurb, artist_type, artist_gender


if __name__ == "__main__":
    from playlist import Track as T

    gen = CommentaryGenerator(Path(__file__).parent / "data" / "ai_dj.db")
    demo = T(path=Path("x"), artist="Kenny Rogers", title="The Gambler",
             album=None, duration=None)
    print(gen.get_commentary(demo))
