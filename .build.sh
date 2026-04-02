#!/bin/bash
cd "${0%/*}"
OUTPUT="${1:-TA-googlebigquery.spl}"
chmod -R u=rwX,go= *
chmod -R u-x+X *
chmod -R u=rwx,go= bin/*
python3.9 -m pip install --upgrade -t lib -r lib/requirements.txt
cd ..
COPYFILE_DISABLE=1 tar -cpzf $OUTPUT --exclude='*/.*' --exclude=.* --exclude=package.json --exclude='__pycache__' TA-googlebigquery
