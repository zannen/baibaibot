#!/bin/bash

destination="${1:?Specify destination server+path as first argument}"

src_dir="$PWD"
[[ "${src_dir: -1}" != "/" ]] && src_dir="${src_dir}/"
[[ "${destination: -1}" != "/" ]] && destination="${destination}/"

rsync -avz --delete --exclude-from .rsyncexclude "$src_dir" "$destination"
