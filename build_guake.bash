#!/bin/env bash

function main(){
# guake --quit     This just starts the terminal to later stop it.

  pkill guake	# incase is running in the background
  rm -rf env
	mkdir -p env
 	python3 -m venv env
	source env/bin/activate     # Go into your virtualenv environment
  python3 -m pip install --upgrade pip
	python3 -m pip install -r requirements.txt
	python3 -m pip install PyGObject
	python3 -m pip install PyGObject
	python3 -m pip install upgrade
  # ./install
	make
  # sudo make dev               # build with sudo to warranty a clean build
  sudo make install           # install with sudo to replace your current executables
  source deactivate           # Get out of your virtualenv environment
  guake --show --verbose      # or in case you also want to see what is going on.
}

time main
