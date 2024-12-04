#!/bin/bash
cd "${0%/*}"
OUTPUT="${1:-TA-googlebigquery.spl}"
chmod -R u=rwX,go= *
chmod -R u-x+X *
chmod -R u=rwx,go= bin/*
python3.9 -m pip install --upgrade --no-dependencies -t lib -r lib/requirements.txt
rm -rf lib/*/__pycache__
rm -rf lib/*/*/__pycache__
cd ..
tar -cpzf $OUTPUT --exclude=.* --exclude=package.json --overwrite TA-googlebigquery