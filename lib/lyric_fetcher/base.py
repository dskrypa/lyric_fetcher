"""
Fetch Korean lyrics and fix the html to make them easier to print

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import os
from abc import ABC
from urllib.parse import urlsplit
from typing import TYPE_CHECKING, Union, Any, Type

from jinja2 import Environment as JinjaEnv, FileSystemLoader as JinjaFSLoader

from ds_tools.caching.caches import FSCache
from ds_tools.caching.decorate import cached
from ds_tools.caching.decorators import cached_property
from ds_tools.fs.paths import validate_or_make_dir, get_user_cache_dir
# from ds_tools.utils.soup import fix_html_prettify
from requests_client import RequestsClient
from .utils import TMPL_DIR, normalize_lyrics, url_for_file, soupify, dated_html_key, html_key

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

__all__ = ['LyricFetcher', 'HybridLyricFetcher', 'TextFileLyricFetcher']
log = logging.getLogger(__name__)


class LyricFetcher(ABC):
    site: str = None
    display_name: str = None
    _site_class_map: dict[str, Type[LyricFetcher]] = {}
    _search_result_tag = None
    _search_result_class = None

    def __init_subclass__(cls, site: str = None, display_name: str = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if site:
            cls._site_class_map[site] = cls
            cls.site = site
        if display_name:
            cls.display_name = display_name

    def __init__(self, *args, **kwargs):
        # fix_html_prettify()
        self.song_tmpl = JinjaEnv(loader=JinjaFSLoader(TMPL_DIR)).get_template('song.html')

    @cached_property
    def client(self) -> RequestsClient:
        return self._init_client()

    def _init_client(self, *args, **kwargs) -> RequestsClient:
        pos_args = (self.site, *args) if self.site else args
        return RequestsClient(*pos_args, rate_limit=1, **kwargs)

    def _format_index(self, query):
        raise TypeError(f'get_index() is not implemented for {self.client.host}')

    def get_index_results(self, *args, **kwargs):
        raise TypeError(f'get_index_results() is not implemented for {self.client.host}')

    def get_search_results(self, *args, **kwargs):
        if any(val is None for val in (self._search_result_tag, self._search_result_class)):
            raise TypeError(f'get_search_results() is not implemented for {self.client.host}')

        soup = self.search(*args, **kwargs)
        results = []
        for post in soup.find_all(self._search_result_tag, class_=self._search_result_class):
            link = post.find('a').get('href')
            text = post.get_text()
            results.append({'Song': text, 'Link': urlsplit(link).path[1:]})
        return results

    def get_song_url(self, song: str) -> str:
        return self.client.url_for(song)

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None) -> dict[str, Union[str, list[str]]]:
        """
        :param str|None song: Song endpoint for lyrics
        :param str title: Title to use (overrides automatically-extracted title is specified)
        :param str kor_endpoint: Endpoint from which Korean lyrics should be retrieved
        :param str eng_endpoint: Endpoint from which English lyrics should be retrieved
        :return dict: Mapping of {'Korean': list(lyrics), 'English': list(lyrics), 'title': title}
        """
        raise TypeError(f'get_lyrics() is not implemented for {self.client.host}')

    def get_korean_lyrics(self, song):
        lyrics = self.get_lyrics(song)
        return lyrics['Korean'], lyrics['title']

    def get_english_translation(self, song):
        lyrics = self.get_lyrics(song)
        return lyrics['English'], lyrics['title']

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

    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='get__', ext='html'), lock=True, key=html_key)
    def get_page(self, endpoint, **kwargs):
        return self.client.get(endpoint, **kwargs).text

    def search_path_and_params(self, query_0, query_1=None) -> tuple[str, dict[str, Any]]:
        return '/', {'s': query_0}

    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='search__', ext='html'), lock=True, key=dated_html_key)
    def _search(self, query_0, query_1=None):
        path, params = self.search_path_and_params(query_0, query_1)
        return self.client.get(path, params=params).text

    @cached(FSCache(cache_subdir='lyric_fetcher', prefix='index__', ext='html'), lock=True, key=dated_html_key)
    def _index(self, endpoint, **kwargs):
        return self.client.get(self._format_index(endpoint), **kwargs).text

    def search(self, *args, **kwargs) -> BeautifulSoup:
        return soupify(self._search(*args, **kwargs))

    def get_index(self, *args, **kwargs) -> BeautifulSoup:
        return soupify(self._index(*args, **kwargs))


class HybridLyricFetcher(LyricFetcher):
    def __init__(self, kor_lf, eng_lf):
        super().__init__()
        self.kor_lf = kor_lf
        self.eng_lf = eng_lf

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
        log.debug(f'Found Korean title: {kor_title!r}, English title: {eng_title!r}')
        return {'Korean': kor_lyrics, 'English': eng_lyrics, 'title': title or kor_title or eng_title}


class TextFileLyricFetcher(LyricFetcher, display_name='file'):
    def get_lyrics(self, file_path, title=None, **kwargs):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().splitlines()

        lines = [line.strip() or '<br/>' for line in content]
        return {'Korean': lines, 'English': lines, 'title': title}
