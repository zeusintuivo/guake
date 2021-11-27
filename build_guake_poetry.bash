#!/bin/env bash

function build(){
# guake --quit     This just starts the terminal to later stop it. 

pkill guake                                                        # incase is running in the background
# source env/bin/activate     # Go into your virtualenv environment
PYTHONPATH=/home/zeus/.pyenv/versions/3.6.9/lib/python3.6/site-packages/
#export PYTHONPATH=/usr/local/lib/python3.7/site-packages
#/usr/bin/python3 -m pip install --upgrade pip
#/home/zeus/.pyenv/versions/3.6.9/bin/pip install --upgrade pip
make
# make dev               # build with sudo to warranty a clean build
sudo make dev               # build with sudo to warranty a clean build
# source deactivate           # Get out of your virtualenv environment
sudo make install           # install with sudo to replace your current executables
}

time build

guake --show --verbose      # or in case you also want to see what is going on.
