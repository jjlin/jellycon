#!/bin/sh

set -ex

python -m pip install --upgrade pip
python -m pip install pyyaml
python build.py --version py3
