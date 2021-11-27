#!/usr/bin/env bash
#set -E -o functrace
#set -ex

PIPENV_IGNORE_VIRTUALENVS=1 /home/linuxbrew/.linuxbrew/bin/black
PIPENV_IGNORE_VIRTUALENVS=1 ~/.local/bin/pipenv run /home/linuxbrew/.linuxbrew/bin/black --check guake
PIPENV_IGNORE_VIRTUALENVS=1 ~/.local/bin/pipenv run /home/linuxbrew/.linuxbrew/bin/flake8 guake
PIPENV_IGNORE_VIRTUALENVS=1 ~/.local/bin/pipenv run /home/linuxbrew/.linuxbrew/bin/pylint --rcfile=.pylintrc --output-format=colorized guake


tempfile=$(mktemp -t tmp.XXXXXX)
trap "rm -f ${tempfile}; exit 1" 1 2 3 15

#[ -z "$REVRANGE" ] && REVRANGE="master..HEAD^1"
#git diff --name-only $REVRANGE | grep '\.py$' > ${tempfile}
oe '.py$' | ohne 'env\/|docs\/|.eggs|doc\/' > ${tempfile}

py_files=()
while read line; do
    if [[ -f "${line}" ]]; then
        echo "fast-styling ${line}"
        pipenv run fiximports ${line};
        pipenv run autopep8 --in-place --recursive setup.py ${line}
        pipenv run yapf --style .yapf --recursive -i ${line}
    fi
done < ${tempfile}
