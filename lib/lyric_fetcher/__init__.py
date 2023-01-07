"""
Fetch Korean lyrics and fix the html to make them easier to print

:author: Doug Skrypa
"""

from .base import LyricFetcher, HybridLyricFetcher, TextFileLyricFetcher
from .sites import LyricsTranslateLyricFetcher, KlyricsLyricFetcher, ColorCodedLyricFetcher, MusixMatchLyricFetcher

SITE_CLASS_MAPPING = {lf.display_name: lf for lf in LyricFetcher._site_class_map.values() if lf.display_name}

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
