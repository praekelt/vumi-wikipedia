#!/bin/bash
VER="$1"

if [[ "x${VER}" = "x" ]]
then
    echo "Usage: $0 <version number>"
    echo " e.g. $0 0.1.0"
    exit 1
fi

SHORT_VER=`echo "${VER}" | sed -e "s/\.[^.]*$//"`

function inplace_sed {
  # Note: we don't use sed -i -e ... because it isn't supported by FreeBSD
  # sed on OS X.
  suffix=".inplace.bak"
  sed -i"$suffix" -e "$1" "$2"
  rm "$2$suffix"
}

inplace_sed "s/\(version[ ]*=[ ]*[\"']\)\(.*\)\([\"'].*\)/\1${VER}\3/" setup.py
