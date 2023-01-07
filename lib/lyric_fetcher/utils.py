"""
Utils for processing lyrics.

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import os
from itertools import chain
from os.path import dirname
from pathlib import Path
from typing import Optional, Collection

__all__ = ['TMPL_DIR', 'url_for_file', 'fix_links', 'normalize_lyrics', 'lyric_part_match', 'StanzaMismatch']
log = logging.getLogger(__name__)

TMPL_DIR = Path(__file__).resolve().parents[2].joinpath('templates').as_posix()


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


def normalize_lyrics(
    lyrics_by_lang: dict[str, list[str]],
    extra_linebreaks: Optional[dict[str, Collection[int]]] = None,
    extra_lines: Optional[dict[str, Collection[int]]] = None,
    replace_lb: bool = False,
    ignore_len: bool = False,
) -> dict[str, list[list[str]]]:
    linebreaks = {lang: set(lang_lb) for lang, lang_lb in extra_linebreaks.items()} if extra_linebreaks else {}
    extra_lyrics = {lang: lang_lines for lang, lang_lines in extra_lines.items()} if extra_lines else {}
    stanzas = {lang: [] for lang in lyrics_by_lang}

    for lang, lang_lyrics in lyrics_by_lang.items():
        lb_set = linebreaks.get(lang, set())
        if replace_lb:
            lang_lyrics = [line for line in lang_lyrics if line != '<br/>']
        lyric_len = len(lang_lyrics)
        for lb in list(lb_set):
            if lb < 0:
                lb_set.add(lyric_len + lb)

        stanza = []
        for i, line in enumerate(map(str.strip, chain(lang_lyrics, extra_lyrics.get(lang, [])))):
            is_br = line == '<br/>'
            if is_br or (i in lb_set):
                if stanza:
                    stanzas[lang].append(stanza)
                    stanza = []
                if not is_br:
                    stanza.append(line)
            elif line:
                stanza.append(line)

        if stanza:
            stanzas[lang].append(stanza)

    stanza_lengths = {lang: len(lang_stanzas) for lang, lang_stanzas in stanzas.items()}
    if len(set(stanza_lengths.values())) != 1:
        for lang, lang_lines in sorted(lyrics_by_lang.items()):
            log.log(19, '{}:'.format(lang))
            for line in lang_lines:
                log.log(19, line)
            log.log(19, '')

        msg = 'Stanza lengths don\'t match: {}'.format(stanza_lengths)
        if ignore_len:
            log.warning(msg)
        else:
            raise StanzaMismatch(msg, stanzas)

    return stanzas
