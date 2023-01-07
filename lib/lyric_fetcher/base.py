"""
Fetch Korean lyrics and fix the html to make them easier to print

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import os
import re
from difflib import SequenceMatcher
from urllib.parse import urlsplit
from typing import Union, Optional, Any

from jinja2 import Environment as JinjaEnv, FileSystemLoader as JinjaFSLoader

from ds_tools.caching.caches import FSCache
from ds_tools.caching.decorate import cached
from ds_tools.fs.paths import validate_or_make_dir, get_user_cache_dir
from ds_tools.output.table import Table, SimpleColumn
from ds_tools.utils.soup import soupify, fix_html_prettify
from requests_client import RequestsClient
from .utils import TMPL_DIR, normalize_lyrics, url_for_file, fix_links

__all__ = ['LyricFetcher', 'HybridLyricFetcher', 'TextFileLyricFetcher']
log = logging.getLogger(__name__)


class LyricFetcher(RequestsClient):
    _site_class_map = {}
    _site = None
    _search_result_tag = None
    _search_result_class = None

    def __init_subclass__(cls, site: Optional[str] = None):  # noqa
        if site:
            cls._site_class_map[site] = cls
            cls._site = site

    def __init__(self, *args, **kwargs):
        pos_args = [self._site, *args] if self._site else args
        super().__init__(*pos_args, rate_limit=1, **kwargs)
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

    def get_song_url(self, song: str) -> str:
        return self.url_for(song)

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None) -> dict[str, Union[str, list[str]]]:
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

    def process_lyrics(
        self,
        song,
        title=None,
        size=12,
        ignore_len=False,
        output_dir=None,
        extra_linebreaks=None,
        extra_lines=None,
        replace_lb=False,
        **kwargs
    ):
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

    def search_path_and_params(self, query_0, query_1=None) -> tuple[str, dict[str, Any]]:
        return '/', {'s': query_0}

    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='search__', ext='html'), lock=True, key=FSCache.dated_html_key)
    def _search(self, query_0, query_1=None):
        path, params = self.search_path_and_params(query_0, query_1)
        return self.get(path, params=params).text

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
