#!/bin/env bash

function main(){
# guake --quit     This just starts the terminal to later stop it. 

pkill guake                                                        # incase is running in the background
# source env/bin/activate     # Go into your virtualenv environment
python -m virtualenv kivy_venv
source kivy_venv/bin/activate 
python -m pip install  -r requirements.py.txt

# export PYTHONPATH=$HOME/.pyenv/versions/3.6.9/lib/python3.6/site-packages/
export PYTHONPATH=$HOME/.pyenv/versions/3.10.0/lib/python3.10/site-packages/
# export PYTHONPATH=/usr/local/lib/python3.7/site-packages
#/usr/bin/python3 -m pip install --upgrade pip
#$HOME/.pyenv/versions/3.6.9/bin/pip install --upgrade pip
make
# make dev               # build with sudo to warranty a clean build
sudo make dev               # build with sudo to warranty a clean build
# source deactivate           # Get out of your virtualenv environment
deactivate
sudo make install           # install with sudo to replace your current executables
guake --show --verbose      # or in case you also want to see what is going on.
}

time main
