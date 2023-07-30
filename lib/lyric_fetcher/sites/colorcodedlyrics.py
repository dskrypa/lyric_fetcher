"""
"""

from __future__ import annotations

import logging
import re
from copy import copy
from urllib.parse import urlsplit
from typing import TYPE_CHECKING, Union

from ds_tools.caching.decorators import cached_property

from ..base import LyricFetcher
from ..processor import LyricProcessor, LyricStanzas, get_tag_text

if TYPE_CHECKING:
    from bs4 import Tag

__all__ = ['ColorCodedLyricFetcher']
log = logging.getLogger(__name__)

LyricResults = dict[str, Union[str, list[str]]]
SITE = 'https://colorcodedlyrics.com'


class ColorCodedLyricFetcher(LyricFetcher, site=SITE, display_name='colorcodedlyrics'):
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
            raise ValueError(f'No index is configured for {query=}')
        return endpoint

    def get_index_results(self, query):
        results = []
        for td in self.get_index(query).find_all('td'):
            title = td.find('img').get('title')
            for a in td.find_all('a'):
                link = a.get('href')
                results.append({'Album': title, 'Song': a.text, 'Link': urlsplit(link).path[1:]})
        return results

    def get_page(self, song: str, **kwargs) -> str:
        html = super().get_page(song, **kwargs)
        # html = html.replace('<p/>', '')
        # html = re.sub(r'\[\s*<span.*?]', '', html, flags=re.DOTALL)

        # html = re.sub(
        #     r'<p>(.*?<span[^>]*>)\s*<br>\s*(\S*)\s*</span>',
        #     r'\1</span></p>\2',
        #     html,
        #     flags=re.DOTALL
        # )

        # pat = re.compile(r'\[\s*<span.*?\]', re.DOTALL)
        # return pat.sub('', html)
        return html
        # pat = re.compile(r'<div class="wp-block-group__inner-container">\n(.*?)<p>', re.DOTALL)
        # return pat.sub(r'<p>\1</p>', html)

    def get_lyrics(self, song, title=None, *, kor_endpoint=None, eng_endpoint=None) -> LyricResults:
        log.debug(f'Getting lyrics for {song=!r}')
        html = self.get_page(song)
        lyrics = CCLProcessor(html, title).get_processed_lyrics()

        # soup = soupify(html, 'lxml')
        # lyrics = {
        #     'Korean': [],
        #     'English': [],
        #     'title': title or soup.find('h1', class_='entry-title').get_text(),
        # }
        #
        # try:
        #     sibling = soup.find('th', text='Romanization').parent.next_sibling
        #     lang_row = sibling.next_sibling or sibling
        # except AttributeError:
        #     self._process_lyrics_nontable(soup, lyrics)
        # else:
        #     self._process_lyrics_table(lang_row, lyrics)

        return lyrics

    # def _process_lyrics_nontable(self, soup: BeautifulSoup, lyrics: dict[str, list[str]]):
    #     columns = soup.find_all('div', class_='wp-block-column is-vertically-aligned-top')
    #     for lang, column in zip(('Korean', 'English'), columns[1:]):
    #         column_data = []
    #         container = column.find('div', class_='wp-block-group__inner-container')
    #         for p in container.find_all('p'):  # type: BeautifulSoup
    #             for ele in p.children:  # type: BeautifulSoup
    #                 if ele.name == 'span':
    #                     column_data.append(ele.get_text())
    #                 elif ele.name == 'br':
    #                     column_data.append('\n')
    #                 elif isinstance(ele, NavigableString):
    #                     column_data.append(ele)
    #             column_data.append('\n<br/>\n')
    #         lyric_str = ''.join(column_data)
    #         lyrics[lang] = lyric_str.splitlines()
    #         # log.debug(f'Lyrics for {lang=!r}:\n{lyric_str}')
    #
    # def _process_lyrics_table(self, lang_row, lyrics):
    #     for lang, td in zip(('Korean', 'English'), lang_row.find_all('td')[1:]):
    #         td_str = str(td)
    #         td_str = td_str[:4] + '<p>' + td_str[4:]
    #         fixed_td = soupify(re.sub('(?<!</p>|<td>)<p>', '</p><p>', td_str))
    #         log.log(5, 'Fixed td:\n{}\n\n'.format(fixed_td))
    #         for p in fixed_td.find_all('p'):
    #             lines = [l for l in p.get_text().replace('<br/>', '\n').splitlines() if l]
    #             for j, line in enumerate(lines):
    #                 if line.startswith('<span'):
    #                     lines[j] = soupify(line).find('span').get_text()
    #
    #             log.log(9, '{}: found stanza with {} lines'.format(lang, len(lines)))
    #             lines.append('<br/>')
    #             lyrics[lang].extend(lines)


class CCLProcessor(LyricProcessor, site=SITE):
    _name_prefix_pat = re.compile(r'^\[\w+(?:/\w+)+]\s*(.*)$')

    def get_title(self) -> str:
        if title := self.title:
            return title
        return self.soup.find('h1', class_='entry-title').get_text()

    @cached_property
    def _lang_columns(self) -> list[Tag]:  # romanized, korean, english
        if columns := [col for col in self.soup.select('.wp-block-column') if col.select('strong .has-inline-color')]:
            return columns
        elif tables := self.soup.find_all('table'):
            self.ignore_br = True
            table = tables[-1]
            return [table.select(f'tr td:nth-child({c})')[0] for c in range(1, 4)]
        else:
            raise RuntimeError('Unable to find any language columns')

    def get_korean_raw(self) -> Tag:
        return copy(self._lang_columns[1])

    def get_english_raw(self) -> Tag:
        return copy(self._lang_columns[2])

    def process_lang_lyrics(self, raw_lyrics: Tag) -> LyricStanzas:
        text = get_tag_text(raw_lyrics, ignore_br=self.ignore_br).strip()
        # line = '=' * 120
        # log.info(f'Processed lyrics:\n{line}\n{text}\n{line}')

        name_prefix_match = self._name_prefix_pat.match
        stanzas, stanza = [], []
        for line in map(str.strip, text.splitlines()[1:]):
            if not line and stanza:
                stanzas.append(stanza)
                stanza = []
            elif line:
                if m := name_prefix_match(line):
                    line = m.group(1).strip()
                stanza.append(line)
        if stanza:
            stanzas.append(stanza)
        return stanzas
