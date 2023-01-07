"""
Utils for processing lyrics.

:author: Doug Skrypa
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from hashlib import sha256
from itertools import chain, zip_longest
from os.path import dirname
from pathlib import Path
from typing import TYPE_CHECKING, Collection
from urllib.parse import urlencode, quote as url_quote

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from .base import LyricFetcher

__all__ = [
    'TMPL_DIR', 'url_for_file', 'fix_links', 'normalize_lyrics', 'lyric_part_match', 'StanzaMismatch', 'soupify',
    'dated_html_key', 'html_key',
]
log = logging.getLogger(__name__)

TMPL_DIR = Path(__file__).resolve().parents[2].joinpath('templates').as_posix()

LangLyrics = dict[str, list[str]]
LineNums = dict[str, Collection[int]]


def soupify(html, mode: str = 'html.parser', *args, **kwargs) -> BeautifulSoup:
    if not isinstance(html, str):
        try:
            html = html.text
        except AttributeError as e:
            raise TypeError('Only strings or Requests library response objects are supported') from e
    return BeautifulSoup(html, mode, *args, **kwargs)


def url_for_file(rel_path, filename=None):
    file_path = os.path.join(dirname(TMPL_DIR), rel_path, filename)
    return 'file:///{}'.format(file_path)


def fix_links(results):
    for result in results:
        if (link := result['Link']) and link.startswith('/'):
            result['Link'] = link[1:]
    return results


def lyric_part_match(ele):
    return ele.name == 'div' and not ele.get('class') and str(ele).startswith('<div class=')


class StanzaMismatch(Exception):
    def __init__(self, msg: str, all_stanzas: dict[str, list[str]]):
        super().__init__(msg)
        self.stanzas = {
            lang: '\n\n'.join('\n'.join(stanza) for stanza in stanza_lists) for lang, stanza_lists in all_stanzas.items()
        }
        self.max_lines = max(stanza.count('\n') for stanza in self.stanzas.values())


class LyricNormalizer:
    __slots__ = ('lang_lyrics_map', 'replace_line_breaks', 'line_breaks', 'extra_lyrics')

    def __init__(
        self,
        lang_lyrics_map: dict[str, list[str | list[str]]],
        add_linebreaks: LineNums = None,
        add_lines: LangLyrics = None,
        replace_line_breaks: bool = False,
    ):
        self.lang_lyrics_map = lang_lyrics_map
        self.replace_line_breaks = replace_line_breaks
        if add_linebreaks:
            self.line_breaks = {lang: set(lang_lb) for lang, lang_lb in add_linebreaks.items()}
        else:
            self.line_breaks = {}
        if add_lines:
            self.extra_lyrics = {lang: lang_lines for lang, lang_lines in add_lines.items()}
        else:
            self.extra_lyrics = {}

    def normalize(self, ignore_len: bool = False) -> dict[str, list[list[str]]]:
        stanzas = {
            lang: [stanza for stanza in self._iter_stanzas(lang, lang_lyrics)]
            for lang, lang_lyrics in self.lang_lyrics_map.items()
        }

        stanza_lengths = {lang: len(lang_stanzas) for lang, lang_stanzas in stanzas.items()}
        if len(set(stanza_lengths.values())) == 1:
            return stanzas

        error_msg = f'Stanza lengths do not match: {stanza_lengths}'
        log.warning(error_msg)

        (lang_a, stanzas_a), (lang_b, stanzas_b) = sorted(stanzas.items())
        for i, (a, b) in enumerate(zip_longest(map(len, stanzas_a), map(len, stanzas_b), fillvalue=0)):
            log.log(19, f'Stanza {i:3d}: {lang_a}={a:3d}, {lang_b}={b:3d}')

        # for lang, lang_lines in sorted(self.lang_lyrics_map.items()):
        #     log.log(19, f'{lang}:')
        #     for line in lang_lines:
        #         log.log(19, line)
        #     log.log(19, '')

        if not ignore_len:
            raise StanzaMismatch(error_msg, stanzas)

        return stanzas

    def _iter_stanzas(self, lang: str, lang_lyrics: list[str | list[str]]):
        lb_set = self.line_breaks.get(lang, set())
        if self.replace_line_breaks:
            lang_lyrics = [line for line in lang_lyrics if line != '<br/>']

        lyric_len = len(lang_lyrics)
        for lb in list(lb_set):
            if lb < 0:
                lb_set.add(lyric_len + lb)

        lines = chain(lang_lyrics, self.extra_lyrics.get(lang, []))
        stanza = []
        for i, line in enumerate(lines):
            if isinstance(line, list):
                if stanza:
                    yield stanza
                    stanza = []
                yield line
            elif line := line.strip():
                if ((is_br := line == '<br/>') or i in lb_set) and stanza:
                    yield stanza
                    stanza = []
                if not is_br:
                    stanza.append(line)

        if stanza:
            yield stanza


def normalize_lyrics(
    lyrics_by_lang: LangLyrics,
    extra_linebreaks: LineNums = None,
    extra_lines: LangLyrics = None,
    replace_lb: bool = False,
    ignore_len: bool = False,
) -> dict[str, list[list[str]]]:
    return LyricNormalizer(lyrics_by_lang, extra_linebreaks, extra_lines, replace_lb).normalize(ignore_len)


def dated_html_key(fetcher: LyricFetcher, endpoint: str, *args, **kwargs) -> str:
    date_str = datetime.now().strftime('%Y-%m-%d')
    uri_path_str = url_quote(endpoint, '')
    return f'{fetcher.client.host}__{date_str}__{uri_path_str}'


def html_key(fetcher: LyricFetcher, endpoint: str, *args, **kwargs) -> str:
    key_parts = [fetcher.client.host, endpoint.replace('/', '_')]
    extras = {}
    for arg, name in (('params', 'query'), ('data', 'data'), ('json', 'json')):
        if value := kwargs.get(arg):
            try:
                value = sorted(value.items())
            except AttributeError:
                pass
            extras[name] = urlencode(value, True)
    if extras:  # Without the below hash, the extras could result in filenames that were too large
        key_parts.append(sha256(json.dumps(extras, sort_keys=True).encode('utf-8')).hexdigest())
    return '__'.join(key_parts)
