#!/usr/bin/env python
"""
Flask server for cleaning up Korean to English translations of song lyrics to make them easier to print

:author: Doug Skrypa
"""

if __name__ == '__main__':
    from gevent import monkey

    monkey.patch_all()

import platform
from pathlib import Path

from cli_command_parser import Command, Option, Flag, Counter, main
from flask import Flask

from lyric_fetcher.routes import blueprint

BASE_DIR = Path(__file__).resolve().parents[1]
app = Flask(__name__, static_folder=BASE_DIR.joinpath('static').as_posix())
app.config.update(PROPAGATE_EXCEPTIONS=True, JSONIFY_PRETTYPRINT_REGULAR=True)


class LyricFetcherServer(Command, option_name_mode='*-'):
    """Lyric Fetcher Flask Server"""

    bind_address = Option('-b', default='0.0.0.0', help='Address for the server to bind to')
    port: int = Option('-p', default=10_000, help='Port to use')
    debug = Flag('-d', help='If specified, debugging will be enabled for the server')
    verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')

    def _init_command_(self):
        from ds_tools.flasks.server import init_logging

        init_logging(None, self.verbose or 2)

    def main(self):
        if platform.system() == 'Windows':
            from ds_tools.flasks.socketio_server import SocketIOServer as Server
        else:
            from ds_tools.flasks.gunicorn_server import GunicornServer as Server

        server = Server(app, self.port, self.bind_address, blueprints=[blueprint], debug=self.debug)
        server.start_server()


if __name__ == '__main__':
    main()
