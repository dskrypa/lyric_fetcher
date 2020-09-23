#!/usr/bin/env python
"""
Flask server for cleaning up Korean to English translations of song lyrics to make them easier to print

:author: Doug Skrypa
"""

if __name__ == '__main__':
    from gevent import monkey
    monkey.patch_all()

import argparse
import logging
import platform
import socket
import sys
import traceback
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, request, render_template, redirect, Response, url_for
from werkzeug.http import HTTP_STATUS_CODES as codes

from ds_tools.flasks.server import init_logging

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(BASE_DIR.joinpath('lib').as_posix())
from lyric_fetcher import SITE_CLASS_MAPPING, normalize_lyrics, fix_links

log = logging.getLogger(__name__)
app = Flask(
    __name__,
    static_folder=BASE_DIR.joinpath('static').as_posix(),
    template_folder=BASE_DIR.joinpath('templates').as_posix()
)
app.config.update(PROPAGATE_EXCEPTIONS=True, JSONIFY_PRETTYPRINT_REGULAR=True)

DEFAULT_SITE = 'colorcodedlyrics'
SITES = list(SITE_CLASS_MAPPING.keys())
fetchers = {site: fetcher_cls() for site, fetcher_cls in SITE_CLASS_MAPPING.items()}


def main():
    parser = argparse.ArgumentParser('Lyric Fetcher Flask Server')
    parser.add_argument('--use_hostname', '-u', action='store_true', help='Use hostname instead of localhost/127.0.0.1')
    parser.add_argument('--port', '-p', type=int, default=10000, help='Port to use')
    parser.add_argument('--verbose', '-v', action='count', help='Print more verbose log info (may be specified multiple times to increase verbosity)')
    args = parser.parse_args()
    init_logging(None, args.verbose or 2)

    host = socket.gethostname() if args.use_hostname else None
    if platform.system() == 'Windows':
        from ds_tools.flasks.socketio_server import SocketIOServer as Server
    else:
        from ds_tools.flasks.gunicorn_server import GunicornServer as Server

    server = Server(app, args.port, host)
    server.start_server()


@app.route('/')
def home():
    url = url_for('.search')
    log.info('Redirecting from / to {}'.format(url))
    return redirect(url)


@app.route('/search/', methods=['GET', 'POST'])
def search():
    req_is_post = request.method == 'POST'
    params = {}
    for param in ('q', 'subq', 'site', 'index'):
        value = request.form.get(param)
        if value is None:
            value = request.args.get(param)
        if value is not None:
            if isinstance(value, str):
                if value := value.strip():
                    params[param] = value
            else:
                params[param] = value

    if req_is_post:
        redirect_to = url_for('.search')
        if params:
            redirect_to += '?' + urlencode(params, True)
        return redirect(redirect_to)

    query = params.get('q')                     # query
    sub_query = params.get('subq')              # sub query
    site = params.get('site') or DEFAULT_SITE   # site from which results should be retrieved
    index = params.get('index')                 # bool: show index results instead of search results

    form_values = {'query': query, 'sub_query': sub_query, 'site': site, 'index': index}
    render_vars = {'title': 'Lyric Fetcher - Search', 'form_values': form_values, 'sites': SITES}
    if not query:
        render_vars['error'] = 'You must provide a valid query.'
    elif site not in fetchers:
        render_vars['error'] = 'Invalid site.'
    else:
        fetcher = fetchers[site]
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


@app.route('/song/<path:song>', methods=['GET'])
def song(song):
    site = request.args.get('site') or DEFAULT_SITE
    if site not in fetchers:
        raise ResponseException(400, 'Invalid site.')

    alt_title = request.args.get('title')
    ignore_len = request.args.get('ignore_len', type=bool)
    fetcher = fetchers[site]

    lyrics = fetcher.get_lyrics(song, alt_title)
    discovered_title = lyrics.pop('title', None)
    stanzas = normalize_lyrics(lyrics, ignore_len=ignore_len)
    stanzas['Translation'] = stanzas.pop('English')

    max_stanzas = max(len(lang_stanzas) for lang_stanzas in stanzas.values())
    for lang, lang_stanzas in stanzas.items():
        if add_stanzas := max_stanzas - len(lang_stanzas):
            for i in range(add_stanzas):
                lang_stanzas.append([])

    render_vars = {
        'title': alt_title or discovered_title or song,
        'lyrics': stanzas,
        'lang_order': ['Korean', 'Translation'],
        'stanza_count': max_stanzas,
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


@app.errorhandler(ResponseException)
def handle_response_exception(err):
    return err.as_response()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
