#!/bin/bash

# Create a desktop shortcut with the following target (with the proper path to this file) to launch the server + firefox:
# "C:\Program Files\Git\bin\bash.exe" "C:\path\to\this_file"
# mate-terminal -e /path/to/this_file

if [[ ${#1} < 1 ]]; then
    port=10000
else
    port=$1
fi

server=lyric_fetcher_server.py
proj_bin="`dirname $0`"

_OLD_VIRTUAL_PATH="$PATH"
if [[ ${OS,,} =~ windows ]]; then
    proj_root=`dirname $proj_bin | sed 's/^\/c/C:/' | sed 's/\//\\\\/g'`
    VIRTUAL_ENV="$proj_root\venv"
    export PATH="$VIRTUAL_ENV/Scripts:$PATH"
    firefox_path="/c/Program Files/Mozilla Firefox/firefox.exe"
    py_path="$proj_root"/venv/Scripts/python.exe
else
    proj_root=`dirname $proj_bin`
    VIRTUAL_ENV="$proj_root/venv"
    export PATH="$VIRTUAL_ENV/bin:$PATH"
    firefox_path=firefox
    py_path="$proj_root"/venv/bin/python
fi
export VIRTUAL_ENV
echo "$VIRTUAL_ENV"

# unset PYTHONHOME if set
# this will fail if PYTHONHOME is set to the empty string (which is bad anyway)
# could use `if (set -u; : $PYTHONHOME) ;` in bash
if [ -n "${PYTHONHOME:-}" ] ; then
    _OLD_VIRTUAL_PYTHONHOME="${PYTHONHOME:-}"
    unset PYTHONHOME
fi

run_firefox () {
    sleep 1
    "$firefox_path" localhost:$port
}

run_firefox &

# When the Python command is the last command in the script, it makes the terminal window stay open (on linux)
"$py_path" "$proj_bin"/$server -p $port -vv
