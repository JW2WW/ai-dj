"""Fetch artist images from Wikipedia as fallback for missing album art."""
import re
import requests
from io import BytesIO
from pathlib import Path
import os


def find_local_cover_art(track_path: Path) -> bytes | None:
    """Look for cover art files in the same directory as the track."""
    album_dir = track_path.parent
    # Common cover art file names
    cover_names = ["cover.jpg", "cover.png", "album.jpg", "album.png",
                   "folder.jpg", "folder.png", "front.jpg", "front.png",
                   "artwork.jpg", "artwork.png"]

    for name in cover_names:
        cover_path = album_dir / name
        if cover_path.exists():
            try:
                return cover_path.read_bytes()
            except Exception:
                pass
    return None


def fetch_wikipedia_artist_image(artist_name: str, cache_dir: Path | None = None, verbose: bool = False) -> bytes | None:
    """Fetch an artist's image from Wikipedia.

    Tries multiple search patterns (artist + "band", artist + "music group", plain artist)
    to avoid generic results. Returns image bytes (JPEG/PNG) or None if not found.
    Optionally caches images locally.
    """
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        headers = {
            "User-Agent": "AI-DJ/1.0 (Music Player; +https://github.com/anthropics/ai-dj)"
        }

        # Try search patterns in order: more specific first, fallback to generic
        search_patterns = [
            f'{artist_name} band',
            f'{artist_name} music group',
            f'{artist_name} singer',
            f'{artist_name} musician',
            artist_name,  # fallback to plain name
        ]

        for search_query in search_patterns:
            search_params = {
                "action": "query",
                "format": "json",
                "srsearch": search_query,
                "list": "search",
                "srlimit": 5,
            }

            if verbose:
                print(f"[Wikipedia] Searching for: {search_query}")

            search_response = requests.get(search_url, params=search_params, headers=headers, timeout=5)
            search_response.raise_for_status()
            search_data = search_response.json()
            search_results = search_data.get("query", {}).get("search", [])

            if not search_results:
                if verbose:
                    print(f"[Wikipedia] No results for: {search_query}")
                continue

            # Filter and rank results: strongly prefer pages with band/artist/musician/singer indicators
            scored_results = []
            for result in search_results:
                title = result["title"]
                # Skip disambiguation pages and obviously irrelevant results
                if "(disambiguation)" in title.lower():
                    continue

                title_lower = title.lower()
                artist_lower = artist_name.lower()

                # Strongly prefer pages with band/musician/artist keywords
                has_music_keyword = any(keyword in title_lower for keyword in [
                    "band", "musician", "singer", "artist", "group",
                    "musical group", "rock band", "pop singer"
                ])
                if has_music_keyword:
                    if re.search(r'\b' + re.escape(artist_lower) + r'\b', title_lower):
                        score = 100  # Artist with music keyword (e.g., "Kiss (band)")
                    else:
                        score = 50
                elif title_lower == artist_lower:
                    score = 70   # Exact match but no band indicator (might be disambiguation or concept)
                elif re.search(r'\b' + re.escape(artist_lower) + r'\b', title_lower):
                    score = 60   # Contains artist as whole word without band indicator
                elif artist_lower in title_lower and len(artist_lower) > 3:
                    score = 30   # Substring match (only for longer names)
                else:
                    score = 0    # generic result
                scored_results.append((score, result))

            # Sort by score (highest first), then by original search ranking
            scored_results.sort(key=lambda x: -x[0])
            filtered_results = [r for _, r in scored_results]

            if not filtered_results:
                if verbose:
                    print(f"[Wikipedia] No relevant results after filtering: {search_query}")
                continue

            # Try each filtered search result until we find one with an image
            for result in filtered_results:
                page_title = result["title"]
                if verbose:
                    print(f"[Wikipedia] Trying page: {page_title}")

                page_params = {
                    "action": "query",
                    "format": "json",
                    "titles": page_title,
                    "prop": "pageimages",
                    "pithumbsize": 300,
                }

                page_response = requests.get(search_url, params=page_params, headers=headers, timeout=5)
                page_response.raise_for_status()
                page_data = page_response.json()
                pages = page_data.get("query", {}).get("pages", {})

                if not pages:
                    continue

                page_info = next(iter(pages.values()))
                image_url = page_info.get("thumbnail", {}).get("source")

                if not image_url:
                    if verbose:
                        print(f"[Wikipedia] No image for {page_title}")
                    continue

                if verbose:
                    print(f"[Wikipedia] Found image URL: {image_url}")

                # Download the image
                img_response = requests.get(image_url, headers=headers, timeout=5)
                img_response.raise_for_status()
                image_bytes = img_response.content

                if verbose:
                    print(f"[Wikipedia] Downloaded {len(image_bytes)} bytes")

                # Cache if cache_dir provided
                if cache_dir:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = "".join(c if c.isalnum() else "_" for c in artist_name)
                    cache_path = cache_dir / f"{safe_name}.jpg"
                    try:
                        cache_path.write_bytes(image_bytes)
                        if verbose:
                            print(f"[Wikipedia] Cached to {cache_path}")
                    except Exception as e:
                        if verbose:
                            print(f"[Wikipedia] Cache write failed: {e}")

                return image_bytes

            # This search pattern didn't yield an image, try the next pattern
            if verbose:
                print(f"[Wikipedia] No image found for pattern: {search_query}")

        # Tried all patterns, no image found
        if verbose:
            print(f"[Wikipedia] No images found for any pattern for {artist_name}")
        return None
    except Exception as e:
        if verbose:
            print(f"[Wikipedia] Error: {e}")
        return None


def get_artist_image(artist_name: str, track_path: Path | None = None, cache_dir: Path | None = None, verbose: bool = False) -> bytes | None:
    """Get artist image: try local cover art first, then cache, then Wikipedia."""
    if verbose:
        print(f"[Images] Getting art for: {artist_name}")

    # 1. Try local cover art in track's album directory
    if track_path:
        local_art = find_local_cover_art(track_path)
        if local_art:
            if verbose:
                print(f"[Images] Found local cover art")
            return local_art

    # 2. Check cache
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "_" for c in artist_name)
        cache_path = cache_dir / f"{safe_name}.jpg"
        if cache_path.exists():
            try:
                image_bytes = cache_path.read_bytes()
                if verbose:
                    print(f"[Images] Found cached image")
                return image_bytes
            except Exception:
                pass

    # 3. Fetch from Wikipedia
    if verbose:
        print(f"[Images] Fetching from Wikipedia...")
    return fetch_wikipedia_artist_image(artist_name, cache_dir, verbose)
