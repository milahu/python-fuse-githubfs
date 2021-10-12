#!/usr/bin/env bash

# dont mount in cwd -> avoid noisy read access by codium
#mountpoint=/tmp/githubfs
#mountpoint=/tmp/githubfs_2
mountpoint=/tmp/githubfs_3

# fuse can hang ...
# umount: /tmp/githubfs: target is busy.

[ ! -d $mountpoint ] && mkdir $mountpoint

umount $mountpoint

# small repo for test
#python httpfs/__main__.py -f $mountpoint milahu logic_fn 3b882601217daf8bfd6e2acbcb1ef659e4659b33

# large repo
# https://github.com/NixOS/nixpkgs/pull/136343
# [DRAFT] Add librewolf

cat <<EOF
todo:

#nix-build -E 'with import <nixpkgs> { }; callPackage ./default.nix { }'

nix-build -I $mountpoint -A librewolf

EOF

./httpfs/__main__.py -f $mountpoint TLATER nixpkgs c1b3f029a39f39e621eb0f9ab4c18acb2e7f74d0

# compare with local repo
# /home/user/src/nixos/nixpkgs-2021-10-12/nixpkgs
#./httpfs/__main__.py -f $mountpoint NixOS nixpkgs e490a7c19310d995aef830d46e89e1cb783c8fa0
