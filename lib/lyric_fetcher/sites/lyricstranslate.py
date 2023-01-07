"""
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit
from typing import Any

from ds_tools.utils.soup import soupify

from ..base import LyricFetcher

__all__ = ['LyricsTranslateLyricFetcher']
log = logging.getLogger(__name__)


class LyricsTranslateLyricFetcher(LyricFetcher, site='https://lyricstranslate.com', display_name='lyricstranslate'):
    def search_path_and_params(self, artist, song=None) -> tuple[str, dict[str, Any]]:
        if song is None:
            song = 'none'
        return f'en/translations/0/328/{artist}/{song}/none/0/0/0/0', {}

    def get_search_results(self, *args, **kwargs):
        results = []
        for row in self.search(*args, **kwargs).find('div', class_='ltsearch-results-line').find_all('tr'):
            lang = row.find('td', class_='ltsearch-translatelanguages')
            if lang and ('English' in lang.text):
                a = row.find_all('td', class_='ltsearch-translatenameoriginal')[1].find('a')
                link = a.get('href')
                text = a.get_text()
                results.append({'Song': text, 'Link': urlsplit(link).path[1:]})
        return results

    def get_english_translation(self, song):
        html = soupify(self.get_page(song), 'lxml')
        artist_ele = html.find('li', class_='song-node-info-artist')
        artist = artist_ele.text.replace('Artist:', '').strip()
        title = html.find('h2', class_='title-h2').text
        full_title = '{} - {}'.format(artist, title)

        content = html.find('div', class_='ltf')
        lines = []
        for par in content.find_all('div', class_='par'):
            stanza = par.get_text().splitlines()
            log.log(19, '{}: found stanza with {} lines'.format('English', len(stanza)))
            lines.extend(stanza)
            lines.append('<br/>')

        return lines, full_title
