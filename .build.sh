#!/bin/bash
cd "${0%/*}"
OUTPUT="${1:-TA-googlebigquery.spl}"
chmod -R u=rwX,go= *
chmod -R u-x+X *
chmod -R u=rwx,go= bin/*
python3.9 -m pip install --upgrade -t lib -r lib/requirements.txt
find lib -type d -name "__pycache__" -exec rm -r {} +
cd ..
tar -cpzf $OUTPUT --exclude=.* --exclude=package.json --overwrite TA-googlebigquery
