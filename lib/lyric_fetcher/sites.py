"""
Fetch Korean lyrics and fix the html to make them easier to print

:author: Doug Skrypa
"""

import logging
import re
from urllib.parse import urlsplit
from typing import TYPE_CHECKING, Union, List, Dict

from bs4 import NavigableString

from ds_tools.caching.caches import FSCache
from ds_tools.caching.decorate import cached
from ds_tools.http.imitate import IMITATE_HEADERS
from ds_tools.output.formatting import to_str
from ds_tools.utils.soup import soupify
from .base import LyricFetcher
from .utils import lyric_part_match

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

__all__ = ['LyricsTranslateLyricFetcher', 'KlyricsLyricFetcher', 'ColorCodedLyricFetcher', 'MusixMatchLyricFetcher']
log = logging.getLogger(__name__)


class LyricsTranslateLyricFetcher(LyricFetcher, site='https://lyricstranslate.com'):
    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='search__', ext='html'), lock=True, key=FSCache.dated_html_key)
    def _search(self, artist, song=None):
        return self.get('en/translations/0/328/{}/{}/none/0/0/0/0'.format(artist, song if song else 'none')).text

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


class KlyricsLyricFetcher(LyricFetcher, site='https://klyrics.net'):
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
                    lyrics['title'] = re.match('^(.*?)\s+Hangul$', h2.text).group(1)
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


class ColorCodedLyricFetcher(LyricFetcher, site='https://colorcodedlyrics.com'):
    _search_result_tag = 'h2'
    _search_result_class = 'entry-title'
    indexes = {
        'redvelvet': '2015/03/red-velvet-lyrics-index',
        'gidle': '2018/05/g-dle-lyrics-index',
        'wekimeki': '2017/09/weki-meki-wikimiki-lyrics-index',
        'blackpink': '2017/09/blackpink-beullaegpingkeu-lyrics-index',
        'ioi': '2016/05/ioi-lyrics-index',
        'twice': '2016/04/twice-lyrics-index',
        'mamamoo': '2016/04/mamamoo-lyric-index',
        'gfriend': '2016/02/gfriend-yeojachingu-lyrics-index',
        '2ne1': '2012/02/2ne1_lyrics_index',
        'snsd': '2012/02/snsd_lyrics_index',
        'missa': '2011/11/miss_a_lyrics_index',
        'apink': '2011/11/a_pink_index',
        'momoland': '2018/02/momoland-momolaendeu-lyrics-index'
    }

    def _format_index(self, query):
        endpoint = self.indexes.get(re.sub(r'[\[\]~!@#$%^&*(){}:;<>,.?/\\+= -]', '', query.lower()))
        if not endpoint:
            raise ValueError('No index is configured for {}'.format(query))
        return endpoint

    def get_index_results(self, query):
        results = []
        for td in self.get_index(query).find_all('td'):
            title = td.find('img').get('title')
            for a in td.find_all('a'):
                link = a.get('href')
                results.append({'Album': title, 'Song': a.text, 'Link': to_str(urlsplit(link).path[1:])})
        return results

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None) -> Dict[str, Union[str, List[str]]]:
        log.debug(f'Getting lyrics for {song=!r}')
        html = soupify(self.get_page(song), 'lxml')
        lyrics = {
            'Korean': [],
            'English': [],
            'title': title or html.find('h1', class_='entry-title').get_text(),
        }

        try:
            lang_row = html.find('th', text='Romanization').parent.next_sibling.next_sibling
        except AttributeError:
            self._process_lyrics_nontable(html, lyrics)
        else:
            self._process_lyrics_table(lang_row, lyrics)

        return lyrics

    def _process_lyrics_nontable(self, soup: 'BeautifulSoup', lyrics: Dict[str, List[str]]):
        columns = soup.find_all('div', class_='wp-block-column is-vertically-aligned-top')
        for lang, column in zip(('Korean', 'English'), columns[1:]):
            column_data = []
            container = column.find('div', class_='wp-block-group__inner-container')
            for p in container.find_all('p'):  # type: BeautifulSoup
                for ele in p.children:  # type: BeautifulSoup
                    if ele.name == 'span':
                        column_data.append(ele.get_text())
                    elif ele.name == 'br':
                        column_data.append('\n')
                    elif isinstance(ele, NavigableString):
                        column_data.append(ele)
                column_data.append('\n<br/>\n')
            lyric_str = ''.join(column_data)
            lyrics[lang] = lyric_str.splitlines()
            # log.debug(f'Lyrics for {lang=!r}:\n{lyric_str}')

    def _process_lyrics_table(self, lang_row, lyrics):
        for lang, td in zip(('Korean', 'English'), lang_row.find_all('td')[1:]):
            td_str = str(td)
            td_str = td_str[:4] + '<p>' + td_str[4:]
            fixed_td = soupify(re.sub('(?<!</p>|<td>)<p>', '</p><p>', td_str))
            log.log(5, 'Fixed td:\n{}\n\n'.format(fixed_td))
            for p in fixed_td.find_all('p'):
                lines = [l for l in p.get_text().replace('<br/>', '\n').splitlines() if l]
                for j, line in enumerate(lines):
                    if line.startswith('<span'):
                        lines[j] = soupify(line).find('span').get_text()

                log.log(9, '{}: found stanza with {} lines'.format(lang, len(lines)))
                lines.append('<br/>')
                lyrics[lang].extend(lines)


class MusixMatchLyricFetcher(LyricFetcher, site='https://musixmatch.com'):
    def __init__(self):
        super().__init__(headers=IMITATE_HEADERS['firefox72@win10'])

    def _normalize_title(self, song: str) -> str:
        song = song[:-1] if song.endswith('/') else song
        if not song.endswith('/translation/english'):
            song += '/translation/english'
        return song

    def get_song_url(self, song: str) -> str:
        return self.url_for(self._normalize_title(song))

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None) -> Dict[str, Union[str, List[str]]]:
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

    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='search__', ext='html'), lock=True, key=FSCache.dated_html_key)
    def _search(self, query_0, query_1=None):
        return self.get('search/{}/tracks'.format(query_0)).text

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
