"""
Base lyric processor for converting HTML into a simpler layout/format for easier printing.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Type, Iterator, Union

from bs4 import BeautifulSoup, PageElement, Tag, NavigableString

from ds_tools.caching.decorators import cached_property

from .utils import soupify

__all__ = ['LyricProcessor', 'LyricStanzas', 'get_tag_text']
log = logging.getLogger(__name__)
iter_text_log = logging.getLogger(f'{__name__}.iter_text')
iter_text_log.setLevel(logging.CRITICAL)

LyricStanzas = list[list[str]]
LyricResults = dict[str, Union[str, list[str]]]

INLINE_NAMES = frozenset({
    'span', 'em', 'strong', 'font', 'mark', 'label', 'sub', 'sup', 'tt', 'bdo', 'button', 'cite', 'del',
    'a', 'b', 'u', 'i', 's',
})


class LyricProcessor(ABC):
    site_cls_map: dict[str, Type[LyricProcessor]] = {}
    site: str
    html: str
    title: str | None
    ignore_br: bool = False

    def __init_subclass__(cls, site: str = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if not site:
            return
        cls.site = site
        cls.site_cls_map[site] = cls

    def __init__(self, html: str, title: str = None):
        self.html = html
        self.title = title

    @classmethod
    def for_site(cls, site: str) -> Type[LyricProcessor]:
        return cls.site_cls_map[site]

    @cached_property
    def soup(self) -> BeautifulSoup:
        return soupify(self.html, 'html5lib')

    @abstractmethod
    def get_title(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_korean_raw(self) -> Tag:
        raise NotImplementedError

    @abstractmethod
    def get_english_raw(self) -> Tag:
        raise NotImplementedError

    @abstractmethod
    def process_lang_lyrics(self, raw_lyrics: PageElement) -> LyricStanzas:
        """
        Called by methods :meth:`.get_korean` and :meth:`.get_english` with the output from methods
        :meth:`.get_korean_raw` and :meth:`.get_english_raw`, respectively.
        """
        raise NotImplementedError

    def get_korean(self) -> LyricStanzas:
        return self.process_lang_lyrics(self.get_korean_raw())

    def get_english(self) -> LyricStanzas:
        return self.process_lang_lyrics(self.get_english_raw())

    def get_processed_lyrics(self) -> LyricResults:
        return {'Korean': self.get_korean(), 'English': self.get_english(), 'title': self.get_title()}


def get_tag_text(tag: Tag, ignore_br: bool = False) -> str:
    iter_text_log.debug(f'Beginning get_tag_text for tag={id(tag)}', extra={'color': 11})
    tag_text = ''.join(_iter_text(tag, ignore_br))
    iter_text_log.debug(f'Finished get_tag_text for tag={id(tag)}', extra={'color': 11})
    return tag_text


def _iter_text(tag: Tag, ignore_br: bool = False) -> Iterator[str]:
    if not (children := tag.contents):
        iter_text_log.debug('Found tag with no children')
        yield '\n'
        return

    inline_names = INLINE_NAMES
    for child in children:
        if isinstance(child, Tag):
            if (name := child.name) == 'br':
                if ignore_br:
                    iter_text_log.debug(f'Found <br/>, but ignoring it', extra={'color': 12})
                else:
                    iter_text_log.debug(f'Found <br/>', extra={'color': 13})
                    yield '\n'
                continue

            # if the tag is a block type tag then yield new lines before & after
            if is_block_element := name not in inline_names:
                iter_text_log.debug(
                    f'In block element {name=} ========================================', extra={'color': 13}
                )
                yield '\n'
            else:
                iter_text_log.debug(f'In inline element {name=} ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')

            yield from _iter_text(child, ignore_br)
            if is_block_element:
                iter_text_log.debug(
                    f'End of block element {name=} ========================================', extra={'color': 13}
                )
                yield '\n'
            else:
                iter_text_log.debug(f'End of inline element {name=} ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')
        elif isinstance(child, NavigableString):
            iter_text_log.debug(f'Found text={child!r}')
            yield child
        else:
            iter_text_log.warning(f'IGNORING ELEMENT: {child=}')
