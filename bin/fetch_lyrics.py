#!/usr/bin/env python
"""
Fetch Korean lyrics and fix the html to make them easier to print

:author: Doug Skrypa
"""

import logging
import sys
from abc import ABC
from dataclasses import dataclass
from pathlib import Path

from cli_command_parser import Command, Option, Positional, SubCommand, Flag, Counter, main
from ds_tools.caching.decorators import cached_property

sys.path.append(Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
from lyric_fetcher import SITE_CLASS_MAPPING, HybridLyricFetcher

log = logging.getLogger(__name__)

SITE_NAMES = sorted(SITE_CLASS_MAPPING)


class LyricFetcherCli(Command, description='Lyric Fetcher'):
    sub_cmd = SubCommand()
    verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')

    def _init_command_(self):
        from ds_tools.logging import init_logging

        init_logging(self.verbose, log_path=None, names=None)


class List(LyricFetcherCli, help='List available sites'):
    def main(self):
        for site in SITE_NAMES:
            print(site)


class SingleSiteCommand(LyricFetcherCli, ABC):
    site = Option('-s', choices=SITE_NAMES, default='colorcodedlyrics', help='Site to use')

    @cached_property
    def lyric_fetcher(self):
        try:
            return SITE_CLASS_MAPPING[self.site]()
        except KeyError as e:
            raise ValueError(f'Invalid site: {self.site}') from e


class Get(SingleSiteCommand, help='Retrieve lyrics from a particular page from a single site'):
    song = Positional(nargs='+', help='One or more endpoints that contain lyrics for particular songs')
    title = Option('-t', help='Page title to use (default: extracted from lyric page)')
    size: int = Option('-z', default=12, help='Font size to use for output')
    ignore_len = Flag('-i', help='Ignore stanza length match')
    output = Option('-o', help='Output directory to store the lyrics')
    linebreaks = Option('-lb', nargs='+', help='Additional linebreaks to use to split stanzas')
    replace_lb = Flag('-R', help='Replace existing linebreaks')

    def main(self):
        linebreaks = {int(str(val).strip()) for val in self.linebreaks or []}
        extra_linebreaks = {'English': linebreaks, 'Korean': linebreaks}
        for song in self.song:
            self.lyric_fetcher.process_lyrics(
                song, self.title, self.size, self.ignore_len, self.output,
                extra_linebreaks=extra_linebreaks, replace_lb=self.replace_lb
            )


class Search(SingleSiteCommand, help='Search for lyric pages'):
    query = Positional(help='Query to run')
    sub_query = Option('-q', help='Sub-query to run')

    def main(self):
        from ds_tools.output.table import Table, SimpleColumn
        from lyric_fetcher.utils import fix_links

        results = self.lyric_fetcher.get_search_results(self.query, self.sub_query)
        tbl = Table(SimpleColumn('Link'), SimpleColumn('Song'), update_width=True)
        fix_links(results)
        tbl.print_rows(results)


class Index(SingleSiteCommand, help='View lyric page endpoints from an artist\'s index page'):
    index = Positional(help='Name of the index to view')
    album_filter = Option('-af', help='Filter for albums to be displayed')
    list = Flag('-L', help='List albums instead of song links')

    def main(self):
        import re
        from ds_tools.output.table import Table, SimpleColumn as Column
        from lyric_fetcher.utils import fix_links

        results = self.lyric_fetcher.get_index_results(self.index)
        if album_filter := self.album_filter:
            alb_filter = re.compile(album_filter)
            results = [r for r in results if r['Album'] and alb_filter.search(r['Album'])]

        if self.list:
            for album in sorted({r['Album'] for r in results if r['Album']}):
                print(album)
        else:
            fix_links(results)
            Table(Column('Album'), Column('Link'), Column('Song'), update_width=True).print_rows(results)


class Compare(SingleSiteCommand, help='Compare lyrics from separate songs for common phrases, etc'):
    song_1 = Positional(help='One or more endpoints that contain lyrics for particular songs')
    song_2 = Positional(help='One or more endpoints that contain lyrics for particular songs')

    def main(self):
        self.lyric_fetcher.compare_lyrics(self.song_1, self.song_2)


class HybridGet(LyricFetcherCli, help='Retrieve lyrics from two separate sites and merge them'):
    korean_site = Option('-ks', choices=SITE_NAMES, help='Site from which Korean lyrics should be retrieved', required=True)
    english_site = Option('-es', choices=SITE_NAMES, help='Site from which the English translation should be retrieved', required=True)
    korean_endpoint = Option('-ke', help='Site from which Korean lyrics should be retrieved', required=True)
    english_endpoint = Option('-ee', help='Site from which the English translation should be retrieved', required=True)

    title = Option('-t', help='Page title to use (default: last part of song endpoint)')
    size: int = Option('-z', default=12, help='Font size to use for output')
    ignore_len = Flag('-i', help='Ignore stanza length match')
    output = Option('-o', help='Output directory to store the lyrics')

    english_lb = Option('-el', nargs='+', help='Additional linebreaks to use to split English stanzas')
    korean_lb = Option('-kl', nargs='+', help='Additional linebreaks to use to split Korean stanzas')

    english_extra = Option('-ex', nargs='+', help='Additional lines to add to the English stanzas at the end')
    korean_extra = Option('-kx', nargs='+', help='Additional lines to add to the Korean stanzas at the end')

    def main(self):
        params = FetcherParams(
            self.title, self.output, self.korean_site, self.english_site, self.korean_endpoint, self.english_endpoint,
            self.size, self.ignore_len, self.korean_lb, self.english_lb, self.korean_extra, self.english_extra
        )
        hybrid_get(params)


class FileGet(LyricFetcherCli, help='Retrieve lyrics from two separate text files and merge them'):
    korean = Option('-k', metavar='PATH', help='Path to a text file containing Korean lyrics')
    english = Option('-e', metavar='PATH', help='Path to a text file containing the English translation')
    title = Option('-t', help='Page title to use (default: last part of song endpoint)')
    size: int = Option('-z', default=12, help='Font size to use for output')
    output = Option('-o', help='Output directory to store the lyrics')

    def main(self):
        params = FetcherParams(self.title, self.output, 'file', 'file', self.korean, self.english, self.size)
        hybrid_get(params)


@dataclass
class FetcherParams:
    title: str
    output: str
    korean_site: str
    english_site: str
    korean_endpoint: str
    english_endpoint: str
    size: int
    ignore_len: bool = None
    korean_lb: list[str | int] = None
    english_lb: list[str | int] = None
    korean_extra: list[str] = None
    english_extra: list[str] = None


def hybrid_get(params: FetcherParams):
    fetchers = {}
    for lang in ('korean', 'english'):
        site = getattr(params, lang + '_site')
        try:
            fetchers[lang] = SITE_CLASS_MAPPING[site]()
        except KeyError as e:
            raise ValueError(f'Invalid site for {lang.title()} lyrics: {site}') from e

    hlf = HybridLyricFetcher(fetchers['korean'], fetchers['english'])

    extra_linebreaks = {
        'English': {int(str(val).strip()) for val in params.english_lb or []},
        'Korean': {int(str(val).strip()) for val in params.korean_lb or []}
    }
    extra_lines = {'English': params.english_extra or [], 'Korean': params.korean_extra or []}
    hlf.process_lyrics(
        None, params.title, params.size, params.ignore_len, params.output,
        kor_endpoint=params.korean_endpoint, eng_endpoint=params.english_endpoint,
        extra_linebreaks=extra_linebreaks, extra_lines=extra_lines
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
