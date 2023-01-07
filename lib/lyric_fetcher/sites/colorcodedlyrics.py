"""
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit
from typing import TYPE_CHECKING, Union

from bs4 import NavigableString, Tag

from ds_tools.utils.soup import soupify

from ..base import LyricFetcher

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

__all__ = ['ColorCodedLyricFetcher']
log = logging.getLogger(__name__)

LyricResults = dict[str, Union[str, list[str]]]


class ColorCodedLyricFetcher(LyricFetcher, site='https://colorcodedlyrics.com', display_name='colorcodedlyrics'):
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
        html = html.replace('<p/>', '')
        html = re.sub(r'\[\s*<span.*?]', '', html, flags=re.DOTALL)

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
        soup = soupify(self.get_page(song), 'lxml')
        lyrics = {
            'Korean': [],
            'English': [],
            'title': title or soup.find('h1', class_='entry-title').get_text(),
        }

        columns = [col for col in soup.select('.wp-block-column') if col.select('strong .has-inline-color')]
        rom_col, ko_col, en_col = columns
        self._process_lyrics_from_columns(ko_col, en_col, lyrics)
        # try:
        #     sibling = html.find('th', text='Romanization').parent.next_sibling
        #     lang_row = sibling.next_sibling or sibling
        # except AttributeError:
        #     self._process_lyrics_nontable(html, lyrics)
        # else:
        #     self._process_lyrics_table(lang_row, lyrics)

        return lyrics

    # def _fix_lines(self, text: str):
    #     singer_text_match = re.compile(r'^(\[.*?\])(.*)$').match
    #     lines = text.splitlines()
    #     fixed = []
    #     building = []
    #     last_truthy = False
    #     for line in map(str.strip, lines):
    #         if not line:
    #             if last_truthy:
    #                 fixed.append('<br/>')
    #                 last_truthy = False
    #             continue
    #
    #         last_truthy = True
    #         if building:
    #             building.append(line)
    #             if (line.startswith(']') and not line.endswith('(')) or line.endswith(')'):
    #                 b_line = ''.join(building)
    #                 if m := singer_text_match(b_line):
    #                     fixed.append(m.group(2))
    #                 else:
    #                     fixed.append(line)
    #
    #                 # fixed.append(''.join(building))
    #                 building = []
    #
    #             # if line.startswith((')', ']')):
    #             #     fixed.append(''.join(building))
    #             #     building = []
    #             # elif line.endswith('('):
    #         # elif line.startswith('[') or line.endswith('('):
    #         elif line.startswith('['):
    #             building.append(line)
    #         elif line.startswith('('):
    #             building.append(fixed.pop(-1))
    #             building.append(line)
    #         else:
    #             fixed.append(line)
    #
    #     if building:
    #         fixed.append(''.join(building))
    #
    #     return fixed

    def _iter_blocks(self, soup: BeautifulSoup):
        block = []
        content = soup.select(('.wp-block-group__inner-container ' * 3).strip())[0]
        for ele in content:
            if isinstance(ele, Tag):
                if ele.name == 'p':
                    if block:
                        p = Tag(name='p')
                        p.extend(block)
                        yield p
                        # yield block
                        block = []
                    yield ele
                else:
                    block.append(ele.__copy__())
                # elif ele.name == 'br' and block:
                #     block.append(ele)
                # else:
                #     raise ValueError(f'Unexpected {ele=}')
            else:
                block.append(ele.__copy__())

        if block:
            yield block

    def _process_lyrics_from_columns(self, ko_col, en_col, lyrics: dict[str, list[str]]):
        # singer_text_match = re.compile(r'^(\[.*?\])(.*)$').match

        for lang, column in zip(('Korean', 'English'), (ko_col, en_col)):
            lang_lyrics = lyrics[lang]
            # lyrics[lang].extend(self._fix_lines(column.get_text('\n')))




            # col_str = str(column)
            # col_str = col_str.replace('</strong></p>', '</strong></p><p>', 1)
            # col_str = col_str.replace('<p><span', '</p><p><span', 1)
            # # col_str.replace('</span><br/>', '\n</span>')
            # soup = soupify(col_str)
            # for p in soup.select('p'):
            #     for line in p.get_text('\n').splitlines():
            #         if m := singer_text_match(line):
            #             lang_lyrics.append(m.group(2))
            #         else:
            #             lang_lyrics.append(line)
            #
            #     # lang_lyrics.extend(p.get_text('\n').splitlines())
            #     lang_lyrics.append('<br/>')

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
