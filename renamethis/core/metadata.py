"""Leitura de metadados opcionais (EXIF de fotos e tags de música).

Pillow e mutagen são dependências opcionais: se não estiverem instaladas, as
funções retornam ``None`` e as regras emitem um aviso em vez de falhar.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from typing import Any

from .models import FileEntry

IMAGE_EXTS = {".jpg", ".jpeg", ".tif", ".tiff", ".png", ".webp", ".heic", ".heif"}
AUDIO_EXTS = {
    ".mp3",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".m4a",
    ".mp4",
    ".aac",
    ".wma",
    ".wav",
    ".aiff",
    ".aif",
    ".ape",
    ".wv",
}

_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 36867
_DATETIME_DIGITIZED = 36868
_DATETIME = 306


def has_pillow() -> bool:
    return importlib.util.find_spec("PIL") is not None


def has_mutagen() -> bool:
    return importlib.util.find_spec("mutagen") is not None


def _parse_exif_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    value = str(value).strip().rstrip("\x00")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def exif_datetime(entry: FileEntry) -> datetime | None:
    """Data em que a foto foi tirada (EXIF DateTimeOriginal), se disponível."""
    if "exif_dt" in entry.meta:
        return entry.meta["exif_dt"]
    result = None
    if not entry.is_dir and entry.ext.lower() in IMAGE_EXTS and has_pillow():
        try:
            from PIL import Image

            with Image.open(entry.path) as img:
                exif = img.getexif()
                sub = exif.get_ifd(_EXIF_IFD) if exif else {}
                result = (
                    _parse_exif_date(sub.get(_DATETIME_ORIGINAL))
                    or _parse_exif_date(sub.get(_DATETIME_DIGITIZED))
                    or _parse_exif_date(exif.get(_DATETIME))
                )
        except Exception:  # arquivo corrompido, formato não suportado etc.
            result = None
    entry.meta["exif_dt"] = result
    return result


def music_tags(entry: FileEntry) -> dict[str, str] | None:
    """Tags de áudio normalizadas: artist, title, album, track, year, genre."""
    if "music" in entry.meta:
        return entry.meta["music"]
    result: dict[str, str] | None = None
    if not entry.is_dir and entry.ext.lower() in AUDIO_EXTS and has_mutagen():
        try:
            import mutagen

            audio = mutagen.File(entry.path, easy=True)
            if audio is not None and audio.tags is not None:

                def first(key: str) -> str:
                    val = audio.tags.get(key)
                    if isinstance(val, list):
                        val = val[0] if val else ""
                    return str(val or "").strip()

                track = first("tracknumber").split("/")[0].strip()
                result = {
                    "artist": first("artist") or first("albumartist"),
                    "title": first("title"),
                    "album": first("album"),
                    "track": track,
                    "year": first("date")[:4],
                    "genre": first("genre"),
                }
        except Exception:
            result = None
    entry.meta["music"] = result
    return result
