"""
"""

from __future__ import annotations

import logging
import re

from ds_tools.utils.soup import soupify

from ..base import LyricFetcher

__all__ = ['KlyricsLyricFetcher']
log = logging.getLogger(__name__)


class KlyricsLyricFetcher(LyricFetcher, site='https://klyrics.net', display_name='klyrics'):
    _search_result_tag = 'h3'
    _search_result_class = 'entry-title'

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None):
        lyrics = {'Korean': [], 'English': [], 'title': title}
        html = soupify(self.get_page(song), 'lxml')
        content = html.find('div', class_='td-post-content')
        for h2 in content.find_all('h2'):
            if h2.text.endswith('Hangul'):
                lang = 'Korean'
                if title is None:
                    lyrics['title'] = re.match(f'^(.*?)\s+Hangul$', h2.text).group(1)
            elif h2.text.endswith('English Translation'):
                lang = 'English'
            else:
                continue

            log.debug('Found {} section'.format(lang))

            ele = h2.next_sibling
            while ele.name in (None, 'p'):
                log.log(9, 'Processing element: <{0}>{1}</{0}>'.format(ele.name, ele))
                if ele.name == 'p':
                    lines = [l for l in ele.text.replace('<br/>', '\n').splitlines() if l]
                    log.log(19, '{}: found stanza with {} lines'.format(lang, len(lines)))
                    lines.append('<br/>')
                    lyrics[lang].extend(lines)
                ele = ele.next_sibling
        return lyrics
