"""
Flask routes and related functions for the lyric fetcher

:author: Doug Skrypa
"""

import json
import logging
import traceback
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import urlencode

from flask import request, render_template, redirect, Response, url_for, Blueprint
from werkzeug.http import HTTP_STATUS_CODES as codes

from . import SITE_CLASS_MAPPING
from .base import LyricFetcher
from .utils import normalize_lyrics, fix_links, StanzaMismatch

log = logging.getLogger(__name__)

DEFAULT_SITE = 'colorcodedlyrics'
SITES = list(SITE_CLASS_MAPPING.keys())
FETCHERS = {site: fetcher_cls() for site, fetcher_cls in SITE_CLASS_MAPPING.items()}  # type: Dict[str, LyricFetcher]

BASE_DIR = Path(__file__).resolve().parents[2]
blueprint = Blueprint(
    'lyric_fetcher',
    __name__,
    root_path=BASE_DIR.as_posix(),
    static_folder=BASE_DIR.joinpath('static').as_posix(),
    template_folder=BASE_DIR.joinpath('templates').as_posix(),
)


@blueprint.route('/')
def home():
    url = url_for('.search')
    log.info('Redirecting from / to {}'.format(url))
    return redirect(url)


@blueprint.route('/search/', methods=['GET', 'POST'])
def search():
    params = parse_params('q', 'subq', 'site', 'index')
    if request.method == 'POST':
        return redirect_to_get('.search', params)

    query = params.get('q')
    sub_query = params.get('subq')
    site = params.get('site') or DEFAULT_SITE   # site from which results should be retrieved
    index = params.get('index')                 # bool: show index results instead of search results

    form_values = {'query': query, 'sub_query': sub_query, 'site': site, 'index': index}
    render_vars = {'title': 'Lyric Fetcher - Search', 'form_values': form_values, 'sites': SITES}
    if not query:
        render_vars['error'] = 'You must provide a valid query.'
    elif site not in FETCHERS:
        render_vars['error'] = 'Invalid site.'
    else:
        fetcher = FETCHERS[site]
        if index:
            try:
                results = fetcher.get_index_results(query)
            except TypeError as e:
                raise ResponseException(501, str(e))
        else:
            results = fetcher.get_search_results(query, sub_query)

        render_vars['results'] = fix_links(results)
        if not results:
            render_vars['error'] = 'No results.'

    return render_template('search.html', **render_vars)


@blueprint.route('/reformatted/', methods=['POST'])
def reformatted():
    all_stanzas = {'Korean': request.form.get('Korean'), 'Translation': request.form.get('English')}
    normalized = {}
    line = '-' * 120
    for lang, text in all_stanzas.items():
        log.debug(f'Provided text for {lang=!r}:\n{line}\n{text}\n{line}')
        text = text.replace('\r', '')
        normalized[lang] = stanzas = [list(map(str.strip, stanza.split('\n'))) for stanza in text.strip().split('\n\n')]
        log.debug(f'Processed text for {lang=!r}:\n{json.dumps(stanzas, indent=4)}')

    return render_song(request.form.get('title'), normalized)


@blueprint.route('/song/<path:song_endpoint>', methods=['GET'])
def song(song_endpoint: str):
    site = request.args.get('site') or DEFAULT_SITE
    if site not in FETCHERS:
        raise ResponseException(400, 'Invalid site.')

    alt_title = request.args.get('title')
    ignore_len = request.args.get('ignore_len', type=bool)
    fetcher = FETCHERS[site]

    lyrics = fetcher.get_lyrics(song_endpoint, alt_title)
    discovered_title = lyrics.pop('title', None)
    title = alt_title or discovered_title or song_endpoint
    try:
        stanzas = normalize_lyrics(lyrics, ignore_len=ignore_len)
    except StanzaMismatch as e:
        render_vars = {
            'title': title,
            'original_url': fetcher.get_song_url(song_endpoint),
            'lyrics': e.stanzas,
            'lang_order': ('Korean', 'English'),
            'max_lines': e.max_lines,
        }
        return render_template('reformat.html', **render_vars)

    stanzas['Translation'] = stanzas.pop('English')
    return render_song(title, stanzas)


def render_song(title: str, stanzas: Dict[str, List[List[str]]]):
    max_stanzas = max(len(lang_stanzas) for lang_stanzas in stanzas.values())
    for lang, lang_stanzas in stanzas.items():
        if add_stanzas := max_stanzas - len(lang_stanzas):
            for i in range(add_stanzas):
                lang_stanzas.append([])

    render_vars = {
        'title': title,
        'lang_order': ['Korean', 'Translation'],
        'lyrics': stanzas,
        'stanza_count': max_stanzas
    }
    return render_template('song.html', **render_vars)


class ResponseException(Exception):
    def __init__(self, code, reason):
        super().__init__()
        self.code = code
        self.reason = reason
        if isinstance(reason, Exception):
            log.error(traceback.format_exc())
        log.error(self.reason)

    def __repr__(self):
        return '<{}({}, {!r})>'.format(type(self).__name__, self.code, self.reason)

    def __str__(self):
        return '{}: [{}] {}'.format(type(self).__name__, self.code, self.reason)

    def as_response(self):
        rendered = render_template('layout.html', error_code=codes[self.code], error=self.reason)
        return Response(rendered, self.code)


@blueprint.errorhandler(ResponseException)
def handle_response_exception(err):
    return err.as_response()


def parse_params(*param_keys: str) -> Dict[str, Any]:
    params = {}
    for param in param_keys:
        value = request.form.get(param)
        if value is None:
            value = request.args.get(param)
        if value is not None:
            if isinstance(value, str):
                if value := value.strip():
                    params[param] = value
            else:
                params[param] = value
    return params


def redirect_to_get(to_method: str, params: Dict[str, Any]):
    redirect_to = url_for(to_method)
    if params:
        redirect_to += '?' + urlencode(params, True)
    return redirect(redirect_to)
