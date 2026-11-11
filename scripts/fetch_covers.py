#!/usr/bin/env python3
"""
Fetch album cover art for entries in ``_data/albums.yml``.

Usage (from the repo root):

    python3 scripts/fetch_covers.py            # fetch covers that are missing
    python3 scripts/fetch_covers.py --all      # re-fetch every cover
    python3 scripts/fetch_covers.py --dry-run  # list entries, fetch nothing

Workflow for an agent or human adding albums:

1. Append an entry to ``_data/albums.yml`` with ``title:`` and ``artist:``
   (the ``cover:`` line may be omitted or left as the placeholder).
2. Run this script. For each album it downloads a JPG into
   ``assets/img/albums/`` and rewrites the entry's ``cover:`` path.
3. Commit both the YAML change and the new image files.

Artwork sources are tried in order:

- iTunes Search API (no auth required; the returned 100px artwork URL is
  rewritten to request the 600px variant).
- MusicBrainz + Cover Art Archive (first a ``release + artist`` query,
  then a title-only fallback). Used for releases iTunes doesn't carry —
  e.g. small-label Bandcamp albums.

Only the Python standard library is used. Network requests are throttled
to ~1/sec because MusicBrainz requires it; the Cover Art Archive and
iTunes are more permissive. A descriptive ``User-Agent`` header is sent
with every request, as required by MusicBrainz policy.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALBUMS_YML = REPO_ROOT / "_data" / "albums.yml"
ALBUMS_DIR = REPO_ROOT / "assets" / "img" / "albums"
PLACEHOLDER = "/assets/img/albums/placeholder.svg"
MIN_IMAGE_BYTES = 5000  # smaller responses are error pages, not covers

USER_AGENT = {
    "User-Agent": "csnbritt-github-io-cover-fetch/1.0 "
                  "(contact: carson.s.britt@gmail.com)"
}

REQUEST_DELAY = 1.0  # seconds between requests; MusicBrainz allows 1 req/sec


def fetch(url: str) -> bytes:
    """
    Perform an HTTP GET and return the raw response body.

    Args:
        url (str): The URL to request. A ``User-Agent`` header is always sent.

    Returns:
        bytes: The response body, following redirects.

    Raises:
        urllib.error.URLError: On network failures, timeouts, or non-2xx
            responses (redirects are followed automatically).
    """
    req = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def norm(text: str) -> str:
    """
    Reduce a string to lowercase alphanumerics for fuzzy comparison.

    Args:
        text (str): Arbitrary title or artist text.

    Returns:
        str: ``text`` with case folded and every non ``[a-z0-9]`` character
            removed, so e.g. "The Moon & Antarctica" -> "themoonantarctica".
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


def slugify(title: str) -> str:
    """
    Convert an album title into a filename-safe slug.

    Args:
        title (str): Album title, e.g. "The Moon & Antarctica".

    Returns:
        str: Lowercase hyphen-separated slug, e.g. "the-moon-antarctica".
            Used as ``<slug>.jpg`` inside ``assets/img/albums/``.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "album"


def load_entries(path: Path) -> tuple[list[str], list[dict]]:
    """
    Parse the album list from a minimal-subset YAML file.

    Args:
        path (Path): Path to ``_data/albums.yml``.

    Returns:
        tuple[list[str], list[dict]]:
            - First element: the file's lines, so callers can rewrite the
              ``cover:`` line in place and write the file back.
            - Second element: one dict per album with keys ``title``,
              ``artist``, ``cover`` (str or None), ``title_idx``,
              ``artist_idx``, ``cover_idx`` (line numbers, or None).

    Note:
        This is a hand-rolled parser, not a YAML library (PyYAML is not a
        site dependency). It assumes entries look like::

            - title: "Some Album"
              artist: "Some Artist"
            cover: /assets/img/albums/foo.jpg

        i.e. ``- title:`` starts an entry and ``artist:``/``cover:`` are
        scalar keys on the following lines. Reordering keys or adding
        nested structure will confuse it — keep the established format.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict] = []
    current: dict | None = None
    for idx, line in enumerate(lines):
        title_m = re.match(r'^- title:\s*"(.+)"\s*$', line)
        artist_m = re.match(r'^\s+artist:\s*"(.+)"\s*$', line)
        cover_m = re.match(r'^\s+cover:\s*(\S+)\s*$', line)
        if title_m:
            current = {
                "title": title_m.group(1),
                "artist": None,
                "cover": None,
                "title_idx": idx,
                "artist_idx": None,
                "cover_idx": None,
            }
            entries.append(current)
        elif current is not None and artist_m:
            current["artist"] = artist_m.group(1)
            current["artist_idx"] = idx
        elif current is not None and cover_m:
            current["cover"] = cover_m.group(1)
            current["cover_idx"] = idx
    return lines, entries


def itunes_artwork(title: str, artist: str) -> bytes | None:
    """
    Look up cover art via the iTunes Search API.

    Args:
        title (str): Album title to search for.
        artist (str): Artist name; used both in the query and to filter
            loosely matched results.

    Returns:
        bytes | None: JPEG data of the 600px artwork if a plausible
            album match with artwork was found, else None.

    Note:
        iTunes fuzzy-matches aggressively, so results are accepted only
        when the normalized artist appears in ``artistName`` or the
        normalized title appears in ``collectionName``. Wrong-album art
        is still possible for common titles — spot-check results.
    """
    term = urllib.parse.quote(f"{title} {artist}")
    url = ("https://itunes.apple.com/search"
           f"?term={term}&entity=album&limit=10&country=US")
    try:
        results = json.loads(fetch(url)).get("results", [])
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        print(f"    itunes lookup failed: {exc}")
        return None
    for res in results:
        if (norm(artist or "") in norm(res.get("artistName", ""))
                or norm(title) in norm(res.get("collectionName", ""))):
            art_url = res.get("artworkUrl100")
            if art_url:
                try:
                    data = fetch(art_url.replace("100x100bb", "600x600bb"))
                    if len(data) > MIN_IMAGE_BYTES:
                        return data
                except (urllib.error.URLError, OSError):
                    continue
    return None


def _releases_from_musicbrainz(query: str) -> list[dict]:
    """
    Query the MusicBrainz release search API.

    Args:
        query (str): A Lucene query string such as
            ``release:"X" AND artist:"Y"`` (unquoted; quoting is added here).

    Returns:
        list[dict]: The ``releases`` array from the JSON response,
            possibly empty.

    Raises:
        urllib.error.URLError: If the request fails.
    """
    url = ("https://musicbrainz.org/ws/2/release/"
           f"?query={urllib.parse.quote(query)}&fmt=json&limit=5")
    return json.loads(fetch(url)).get("releases", [])


def _caa_front(mbid: str) -> bytes | None:
    """
    Fetch front cover art for one MusicBrainz release.

    Args:
        mbid (str): MusicBrainz release ID.

    Returns:
        bytes | None: JPEG data, trying the 500px thumbnail before the
            full-size ``front`` image; None if the release has no front
            art in the archive.
    """
    for size in ("front-500", "front"):
        try:
            data = fetch(f"https://coverartarchive.org/release/{mbid}/{size}")
            if len(data) > MIN_IMAGE_BYTES:
                return data
        except (urllib.error.URLError, OSError):
            continue
    return None


def caa_artwork(title: str, artist: str) -> bytes | None:
    """
    Look up cover art via MusicBrainz and the Cover Art Archive.

    Args:
        title (str): Album title.
        artist (str): Artist name.

    Returns:
        bytes | None: JPEG data of the front cover if found, else None.

    Note:
        Two passes: a strict ``release AND artist`` query, then a
        title-only fallback (needed for releases whose MusicBrainz
        artist-credit differs from the supplied name). In the fallback,
        releases whose ``artist-credit-phrase`` matches are preferred;
        otherwise the first release with front art wins, which can pick
        a different album with the same title — spot-check results.
        Sleeps between requests to respect the 1 req/sec rate limit.
    """
    try:
        strict = _releases_from_musicbrainz(
            f'release:"{title}" AND artist:"{artist}"')
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        strict = []
    time.sleep(REQUEST_DELAY)
    for rel in strict:
        data = _caa_front(rel["id"])
        if data:
            return data
        time.sleep(REQUEST_DELAY)

    # Fallback: title-only query, prefer releases with a matching artist.
    try:
        loose = _releases_from_musicbrainz(f'release:"{title}"')
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        loose = []
    loose.sort(key=lambda r: norm(artist or "")
               not in norm(r.get("artist-credit-phrase", "")))
    for rel in loose:
        time.sleep(REQUEST_DELAY)
        data = _caa_front(rel["id"])
        if data:
            return data
    return None


def cover_path_for(entry: dict) -> str:
    """
    Choose the site-relative cover path for an album entry.

    Args:
        entry (dict): One parsed album entry from ``load_entries``.

    Returns:
        str: Path like ``/assets/img/albums/<slug>.jpg``. If the entry
            already points at a local file under ``/assets/img/albums/``,
            that filename is reused so ``--all`` refreshes files in place
            instead of renaming them.
    """
    cover = entry.get("cover") or ""
    if cover.startswith("/assets/img/albums/") and cover != PLACEHOLDER:
        return cover
    return f"/assets/img/albums/{slugify(entry['title'])}.jpg"


def needs_cover(entry: dict, refetch_all: bool) -> bool:
    """
    Decide whether an album entry should have its cover (re)fetched.

    Args:
        entry (dict): One parsed album entry from ``load_entries``.
        refetch_all (bool): True when the user passed ``--all``.

    Returns:
        bool: True if ``--all`` was given, if the entry has no ``cover``
            line, if it still points at the placeholder SVG, or if its
            cover path is a local file that does not exist on disk.
    """
    cover = entry.get("cover")
    if refetch_all or not cover or cover == PLACEHOLDER:
        return True
    if cover.startswith("/"):
        return not (REPO_ROOT / cover.lstrip("/")).exists()
    return True


def set_cover_line(lines: list[str], entry: dict, new_path: str) -> None:
    """
    Rewrite an entry's ``cover:`` line in the YAML source lines.

    Args:
        lines (list[str]): Mutable list of file lines from ``load_entries``.
        entry (dict): The entry being updated; its ``cover_idx`` /
            ``artist_idx`` locate where to write.
        new_path (str): The site-relative path to store, e.g.
            ``/assets/img/albums/loveless.jpg``.

    Returns:
        None: ``lines`` and ``entry['cover']``/``entry['cover_idx']`` are
            updated in place.

    Note:
        If the entry has no ``cover:`` line yet, one is inserted directly
        after its ``artist:`` line. Because insertion shifts line numbers
        for later entries, callers must process entries from last to
        first when inserting, or re-load the file afterwards.
    """
    if entry["cover_idx"] is not None:
        lines[entry["cover_idx"]] = f'  cover: {new_path}'
    else:
        lines.insert(entry["artist_idx"] + 1, f'  cover: {new_path}')
        entry["cover_idx"] = entry["artist_idx"] + 1
    entry["cover"] = new_path


def main() -> int:
    """
    Fetch missing album covers and update ``_data/albums.yml`` in place.

    Args:
        None: Behaviour is controlled by command-line flags — ``--all``
            re-fetches every cover, ``--dry-run`` only prints what would
            happen.

    Returns:
        int: Process exit code; 0 on success (including partial failures,
            which are reported on stdout), 1 if the albums file is missing.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true",
                        help="re-fetch every cover, even ones that exist")
    parser.add_argument("--dry-run", action="store_true",
                        help="list albums and cover status; make no requests")
    args = parser.parse_args()

    if not ALBUMS_YML.exists():
        print(f"error: {ALBUMS_YML} not found", file=sys.stderr)
        return 1

    lines, entries = load_entries(ALBUMS_YML)
    ALBUMS_DIR.mkdir(parents=True, exist_ok=True)

    updates: list[tuple[dict, str]] = []
    for entry in entries:
        title, artist = entry["title"], entry["artist"] or ""
        if not needs_cover(entry, args.all):
            print(f"have    {title}")
            continue
        rel_path = cover_path_for(entry)
        if args.dry_run:
            print(f"would fetch  {title} -> {rel_path}")
            continue

        print(f"fetch   {title} ...", end=" ", flush=True)
        data = itunes_artwork(title, artist)
        time.sleep(REQUEST_DELAY)
        source = "itunes"
        if not data:
            data = caa_artwork(title, artist)
            source = "coverartarchive"
        if data:
            (REPO_ROOT / rel_path.lstrip("/")).write_bytes(data)
            updates.append((entry, rel_path))
            print(f"ok ({source})")
        else:
            print("FAILED")

    # Apply cover-line updates last-to-first so set_cover_line insertions
    # can't shift the recorded indices of entries not yet updated.
    for entry, rel_path in reversed(updates):
        set_cover_line(lines, entry, rel_path)
    if updates:
        ALBUMS_YML.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nupdated {ALBUMS_YML}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
