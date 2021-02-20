#!/usr/bin/env python
"""
Flask server for cleaning up Korean to English translations of song lyrics to make them easier to print

:author: Doug Skrypa
"""

if __name__ == '__main__':
    from gevent import monkey
    monkey.patch_all()

import logging
import platform
import socket
import sys
from pathlib import Path

from flask import Flask

from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from ds_tools.flasks.server import init_logging

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(BASE_DIR.joinpath('lib').as_posix())
from lyric_fetcher.routes import blueprint

log = logging.getLogger(__name__)
app = Flask(__name__, static_folder=BASE_DIR.joinpath('static').as_posix())
app.config.update(PROPAGATE_EXCEPTIONS=True, JSONIFY_PRETTYPRINT_REGULAR=True)


@wrap_main
def main():
    parser = ArgParser('Lyric Fetcher Flask Server')
    parser.add_argument('--use_hostname', '-u', action='store_true', help='Use hostname instead of localhost/127.0.0.1')
    parser.add_argument('--port', '-p', type=int, default=10000, help='Port to use')
    parser.include_common_args('verbosity')
    args = parser.parse_args()
    init_logging(None, args.verbose or 2)

    host = socket.gethostname() if args.use_hostname else None
    if platform.system() == 'Windows':
        from ds_tools.flasks.socketio_server import SocketIOServer as Server
    else:
        from ds_tools.flasks.gunicorn_server import GunicornServer as Server

    server = Server(app, args.port, host, blueprints=[blueprint])
    server.start_server()


if __name__ == '__main__':
    main()
