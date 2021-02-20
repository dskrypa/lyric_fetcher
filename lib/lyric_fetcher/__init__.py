"""
Fetch Korean lyrics and fix the html to make them easier to print

:author: Doug Skrypa
"""

from .base import LyricFetcher, HybridLyricFetcher, TextFileLyricFetcher
from .sites import LyricsTranslateLyricFetcher, KlyricsLyricFetcher, ColorCodedLyricFetcher, MusixMatchLyricFetcher

__all__ = [
    'LyricFetcher',
    'HybridLyricFetcher',
    'TextFileLyricFetcher',
    'LyricsTranslateLyricFetcher',
    'KlyricsLyricFetcher',
    'ColorCodedLyricFetcher',
    'MusixMatchLyricFetcher',
    'SITE_CLASS_MAPPING',
]

SITE_CLASS_MAPPING = {
    'colorcodedlyrics': ColorCodedLyricFetcher,
    'klyrics': KlyricsLyricFetcher,
    'lyricstranslate': LyricsTranslateLyricFetcher,
    'file': TextFileLyricFetcher,
    'musixmatch': MusixMatchLyricFetcher,
}
