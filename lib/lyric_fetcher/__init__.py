"""
Fetch Korean lyrics and fix the html to make them easier to print

:author: Doug Skrypa
"""

import logging
import os
import re
from difflib import SequenceMatcher
from itertools import chain
from os.path import dirname
from urllib.parse import urlsplit
from pathlib import Path
from typing import TYPE_CHECKING, Union, List, Dict

from bs4 import NavigableString
from jinja2 import Environment as JinjaEnv, FileSystemLoader as JinjaFSLoader

from ds_tools.caching.caches import FSCache
from ds_tools.caching.decorate import cached
from ds_tools.fs.paths import validate_or_make_dir, get_user_cache_dir
from ds_tools.http.imitate import IMITATE_HEADERS
from ds_tools.output.formatting import to_str
from ds_tools.output.table import Table, SimpleColumn
from ds_tools.utils.soup import soupify, fix_html_prettify
from requests_client import RequestsClient

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

__all__ = [
    'normalize_lyrics', 'LyricFetcher', 'HybridLyricFetcher', 'TextFileLyricFetcher', 'LyricsTranslateLyricFetcher',
    'KlyricsLyricFetcher', 'ColorCodedLyricFetcher', 'MusixMatchLyricFetcher', 'SITE_CLASS_MAPPING', 'fix_links'
]
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


def normalize_lyrics(lyrics_by_lang, extra_linebreaks=None, extra_lines=None, replace_lb=False, ignore_len=False):
    linebreaks = {lang: set(lang_lb) for lang, lang_lb in extra_linebreaks.items()} if extra_linebreaks else {}
    extra_lyrics = {lang: lang_lines for lang, lang_lines in extra_lines.items()} if extra_lines else {}
    stanzas = {lang: [] for lang in lyrics_by_lang}

    for lang, lang_lyrics in lyrics_by_lang.items():
        lb_set = linebreaks.get(lang, set())
        if replace_lb:
            lang_lyrics = [l for l in lang_lyrics if l != '<br/>']
        lyric_len = len(lang_lyrics)
        for lb in list(lb_set):
            if lb < 0:
                lb_set.add(lyric_len + lb)

        stanza = []
        for i, line in enumerate(chain(lang_lyrics, extra_lyrics.get(lang, []))):
            is_br = line == '<br/>'
            if is_br or (i in lb_set):
                if stanza:
                    stanzas[lang].append(stanza)
                    stanza = []
                if not is_br:
                    stanza.append(line)
            elif line.strip():
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
            raise ValueError(msg)

    return stanzas


class LyricFetcher(RequestsClient):
    _search_result_tag = None
    _search_result_class = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, rate_limit=1, **kwargs)
        fix_html_prettify()
        self.song_tmpl = JinjaEnv(loader=JinjaFSLoader(TMPL_DIR)).get_template('song.html')

    def _format_index(self, query):
        raise TypeError('get_index() is not implemented for {}'.format(self.host))

    def get_index_results(self, *args, **kwargs):
        raise TypeError('get_index_results() is not implemented for {}'.format(self.host))

    def get_search_results(self, *args, **kwargs):
        if any(val is None for val in (self._search_result_tag, self._search_result_class)):
            raise TypeError('get_search_results() is not implemented for {}'.format(self.host))

        soup = self.search(*args, **kwargs)
        results = []
        for post in soup.find_all(self._search_result_tag, class_=self._search_result_class):
            link = post.find('a').get('href')
            text = post.get_text()
            results.append({'Song': text, 'Link': urlsplit(link).path[1:]})
        return results

    def print_search_results(self, *args):
        results = self.get_search_results(*args)
        tbl = Table(SimpleColumn('Link'), SimpleColumn('Song'), update_width=True)
        fix_links(results)
        tbl.print_rows(results)

    def print_index_results(self, query, album_filter=None, list_albums=False):
        alb_filter = re.compile(album_filter) if album_filter else None
        results = self.get_index_results(query)
        filtered = [r for r in results if r['Album'] and alb_filter.search(r['Album'])] if alb_filter else results
        if list_albums:
            albums = {r['Album'] for r in filtered if r['Album']}
            for album in sorted(albums):
                print(album)
        else:
            tbl = Table(SimpleColumn('Album'), SimpleColumn('Link'), SimpleColumn('Song'), update_width=True)
            fix_links(filtered)
            tbl.print_rows(filtered)

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None) -> Dict[str, Union[str, List[str]]]:
        """
        :param str|None song: Song endpoint for lyrics
        :param str title: Title to use (overrides automatically-extracted title is specified)
        :param str kor_endpoint: Endpoint from which Korean lyrics should be retrieved
        :param str eng_endpoint: Endpoint from which English lyrics should be retrieved
        :return dict: Mapping of {'Korean': list(lyrics), 'English': list(lyrics), 'title': title}
        """
        raise TypeError(f'get_lyrics() is not implemented for {self.host}')

    def get_korean_lyrics(self, song):
        lyrics = self.get_lyrics(song)
        return lyrics['Korean'], lyrics['title']

    def get_english_translation(self, song):
        lyrics = self.get_lyrics(song)
        return lyrics['English'], lyrics['title']

    def compare_lyrics(self, song_1, song_2):
        lyrics_1 = re.sub('\s+', ' ', ' '.join(l for l in self.get_lyrics(song_1)['Korean'] if l != '<br/>'))
        lyrics_2 = re.sub('\s+', ' ', ' '.join(l for l in self.get_lyrics(song_2)['Korean'] if l != '<br/>'))

        seqs = set()
        sm = SequenceMatcher(None, lyrics_1, lyrics_2)
        for block in sm.get_matching_blocks():
            seq = lyrics_1[block.a: block.a + block.size]
            if (' ' in seq) and (len(seq.strip()) >= 3):
                seqs.add(seq)

        for seq in sorted(seqs, key=lambda x: len(x), reverse=True):
            print(seq)

    def process_lyrics(self, song, title=None, size=12, ignore_len=False, output_dir=None, extra_linebreaks=None, extra_lines=None, replace_lb=False, **kwargs):
        """
        Process lyrics from the given song and write them to an html file

        :param str|None song: Song endpoint for lyrics
        :param str title: Title to use (overrides automatically-extracted title is specified)
        :param int size: Font size to use for output
        :param bool ignore_len: Ignore stanza length mismatches
        :param output_dir:
        :param extra_linebreaks:
        :param english_extra:
        :param korean_extra:
        :param replace_lb:
        :param kwargs: Keyword arguments to pass to :func:`LyricFetcher.get_lyrics`
        """
        if output_dir and (os.path.exists(output_dir) and not os.path.isdir(output_dir)):
            raise ValueError('Invalid output dir - it exists but is not a directory: {}'.format(output_dir))

        lyrics = self.get_lyrics(song, title, **kwargs)
        discovered_title = lyrics.pop('title', None)
        stanzas = normalize_lyrics(lyrics, extra_linebreaks, extra_lines, replace_lb=replace_lb, ignore_len=ignore_len)
        stanzas['Translation'] = stanzas.pop('English')

        max_stanzas = max(len(lang_stanzas) for lang_stanzas in stanzas.values())
        for lang, lang_stanzas in stanzas.items():
            add_stanzas = max_stanzas - len(lang_stanzas)
            if add_stanzas:
                for i in range(add_stanzas):
                    lang_stanzas.append([])

        final_title = title or discovered_title or song
        render_vars = {
            'title': final_title, 'lyrics': stanzas, 'lang_order': ['Korean', 'Translation'],
            'stanza_count': max_stanzas, 'url_for': url_for_file
        }
        prettified = self.song_tmpl.render(**render_vars)

        output_dir = output_dir or get_user_cache_dir('lyric_fetcher/lyrics')
        validate_or_make_dir(output_dir)
        output_filename = 'lyrics_{}.html'.format(final_title.replace(' ', '_').replace('?', ''))
        output_path = os.path.join(output_dir, output_filename)
        log.info('Saving lyrics to {}'.format(output_path))
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(prettified)

    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='get__', ext='html'), lock=True, key=FSCache.html_key)
    def get_page(self, endpoint, **kwargs):
        return self.get(endpoint, **kwargs).text

    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='search__', ext='html'), lock=True, key=FSCache.dated_html_key)
    def _search(self, query_0, query_1=None):
        return self.get('/', params={'s': query_0}).text

    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='index__', ext='html'), lock=True, key=FSCache.dated_html_key)
    def _index(self, endpoint, **kwargs):
        return self.get(self._format_index(endpoint), **kwargs).text

    def search(self, *args, **kwargs):
        return soupify(self._search(*args, **kwargs))

    def get_index(self, *args, **kwargs):
        return soupify(self._index(*args, **kwargs))


class HybridLyricFetcher(LyricFetcher):
    # noinspection PyMissingConstructor
    def __init__(self, kor_lf, eng_lf):
        self.kor_lf = kor_lf
        self.eng_lf = eng_lf
        fix_html_prettify()

    def get_lyrics(self, song=None, title=None, *, kor_endpoint=None, eng_endpoint=None):
        """
        :param str song: Song endpoint for lyrics
        :param str title: Title to use (overrides automatically-extracted title if specified)
        :param str kor_endpoint: Endpoint from which Korean lyrics should be retrieved
        :param str eng_endpoint: Endpoint from which English lyrics should be retrieved
        :return dict: Mapping of {'Korean': list(lyrics), 'English': list(lyrics), 'title': title}
        """
        kor_lyrics, kor_title = self.kor_lf.get_korean_lyrics(kor_endpoint)
        eng_lyrics, eng_title = self.eng_lf.get_english_translation(eng_endpoint)
        log.debug('Found Korean title: {!r}, English title: {!r}'.format(kor_title, eng_title))
        return {'Korean': kor_lyrics, 'English': eng_lyrics, 'title': title or kor_title or eng_title}


class TextFileLyricFetcher(LyricFetcher):
    # noinspection PyMissingConstructor
    def __init__(self):
        super().__init__(None)

    def get_lyrics(self, file_path, title=None, **kwargs):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().splitlines()

        lines = [line.strip() or '<br/>' for line in content]
        return {'Korean': lines, 'English': lines, 'title': title}


class LyricsTranslateLyricFetcher(LyricFetcher):
    def __init__(self):
        super().__init__('https://lyricstranslate.com')

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


class KlyricsLyricFetcher(LyricFetcher):
    _search_result_tag = 'h3'
    _search_result_class = 'entry-title'

    def __init__(self):
        super().__init__('https://klyrics.net')

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


class ColorCodedLyricFetcher(LyricFetcher):
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

    def __init__(self):
        super().__init__('https://colorcodedlyrics.com')

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


def lyric_part_match(ele):
    return ele.name == 'div' and not ele.get('class') and str(ele).startswith('<div class=')


class MusixMatchLyricFetcher(LyricFetcher):
    def __init__(self):
        super().__init__('https://musixmatch.com', headers=IMITATE_HEADERS['firefox72@win10'])

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None) -> Dict[str, Union[str, List[str]]]:
        song = song[:-1] if song.endswith('/') else song
        if not song.endswith('/translation/english'):
            song += '/translation/english'
        html = soupify(self.get_page(song), 'lxml')

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


SITE_CLASS_MAPPING = {
    'colorcodedlyrics': ColorCodedLyricFetcher,
    'klyrics': KlyricsLyricFetcher,
    'lyricstranslate': LyricsTranslateLyricFetcher,
    'file': TextFileLyricFetcher,
    'musixmatch': MusixMatchLyricFetcher,
}
