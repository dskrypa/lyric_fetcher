"""
"""

from __future__ import annotations

import logging
import re
from typing import Union, Any

from ds_tools.http.imitate import IMITATE_HEADERS
from ds_tools.utils.soup import soupify
from requests_client import RequestsClient

from ..base import LyricFetcher
from ..utils import lyric_part_match

__all__ = ['MusixMatchLyricFetcher']
log = logging.getLogger(__name__)

LyricResults = dict[str, Union[str, list[str]]]


class MusixMatchLyricFetcher(LyricFetcher, site='https://musixmatch.com', display_name='musixmatch'):
    def _init_client(self, *args, **kwargs) -> RequestsClient:
        kwargs['headers'] = IMITATE_HEADERS['firefox108@win10']
        return super()._init_client(*args, **kwargs)

    def _normalize_title(self, song: str) -> str:
        song = song[:-1] if song.endswith('/') else song
        if not song.endswith('/translation/english'):
            song += '/translation/english'
        return song

    def get_song_url(self, song: str) -> str:
        return self.client.url_for(self._normalize_title(song))

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None) -> LyricResults:
        html = soupify(self.get_page(self._normalize_title(song)), 'lxml')

        title_header = html.find('div', class_='mxm-track-title')
        track_title = list(title_header.find('h1').children)[-1]
        track_artist = title_header.find('h2').get_text()

        lyrics = {'Korean': [], 'English': [], 'title': title or '{} - {}'.format(track_artist, track_title)}
        lang_names = {0: 'Korean', 1: 'English'}

        container = html.find('div', class_='mxm-track-lyrics-container')
        for row in container.find_all('div', class_='mxm-translatable-line-readonly'):
            # log.debug(f'Found {row=}')
            last_i = -1
            for i, div in enumerate(row.find_all(lyric_part_match)):
                # TODO: Need to add newlines between stanzas
                lang = lang_names[i]
                text = div.get_text() or '<br/>'
                # log.debug(f'Found {lang=} {text=}')
                lyrics[lang].append(text)
                last_i = i

            if (last_i == 0) and (len(lyrics['Korean']) != len(lyrics['English'])):
                lyrics['English'].append('<br/>')

        return lyrics

    def search_path_and_params(self, query_0, query_1=None) -> tuple[str, dict[str, Any]]:
        return f'search/{query_0}/tracks', {}

    def get_search_results(self, *args, **kwargs):
        results = []
        for a in self.search(*args, **kwargs).find_all('a', href=re.compile('/lyrics/.*')):
            link = a.get('href')
            if not link.endswith(('/edit', '/add')):
                title = a.get_text()
                results.append({'Song': title, 'Link': link})
        return results

    def _format_index(self, query):
        return 'artist/{}/albums'.format(query)

    def get_index_results(self, query):
        album_soup = self.get_index(query)
        results = []
        for a in album_soup.find_all('a', href=re.compile('/album/.*')):
            year = a.parent.next_sibling.get_text()
            album = '[{}] {}'.format(year, a.get_text())
            link = a.get('href')

            album_page = soupify(self.get_page(link))
            for track_a in album_page.find_all('a', href=re.compile('/lyrics/.*(?<!/edit)$')):
                track_link = track_a.get('href')
                track_name = track_a.find('h2', class_=re.compile('.*title$')).get_text()
                results.append({'Album': album, 'Song': track_name, 'Link': track_link})

                # print(album, link)
        return results
