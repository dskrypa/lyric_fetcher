#!/bin/bash

# Create a desktop shortcut with the following target (with the proper path to this file) to launch the server + firefox:
# "C:\Program Files\Git\bin\bash.exe" "C:\path\to\this_file"

if [[ ${#1} < 1 ]]; then
    port=10000
else
    port=$1
fi

lf_dir="`dirname $0`"
# /usr/bin/env python "$lf_dir"/lyric_fetcher_server.py -p $port & "/c/Program Files/Mozilla Firefox/firefox.exe" localhost:$port

proj_root=`dirname $lf_dir | sed 's/^\/c/C:/' | sed 's/\//\\\\/g'`
VIRTUAL_ENV="$proj_root\venv"
export VIRTUAL_ENV

echo $VIRTUAL_ENV

_OLD_VIRTUAL_PATH="$PATH"
PATH="$VIRTUAL_ENV/Scripts:$PATH"
export PATH

# unset PYTHONHOME if set
# this will fail if PYTHONHOME is set to the empty string (which is bad anyway)
# could use `if (set -u; : $PYTHONHOME) ;` in bash
if [ -n "${PYTHONHOME:-}" ] ; then
    _OLD_VIRTUAL_PYTHONHOME="${PYTHONHOME:-}"
    unset PYTHONHOME
fi

run_firefox () {
  sleep 1
  "/c/Program Files/Mozilla Firefox/firefox.exe" localhost:$port
}

# "$lf_dir"/../venv/Scripts/python.exe "$lf_dir"/lyric_fetcher_server.py -p $port & sleep 2 & "/c/Program Files/Mozilla Firefox/firefox.exe" localhost:$port
"$lf_dir"/../venv/Scripts/python.exe "$lf_dir"/lyric_fetcher_server.py -p $port & run_firefox
