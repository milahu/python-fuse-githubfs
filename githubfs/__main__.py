#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# based on https://github.com/higlass/simple-httpfs 

import sys

if sys.version_info.major < 3:
    print("error: this program requires python 3")
    sys.exit(1)

import argparse
import logging
import os.path as op

from fuse import FUSE

from __init__ import GithubFs


def main():
    parser = argparse.ArgumentParser(
        description="mount github repo at commit",
        prog="githubfs.py", # TODO rename __main__.py to githubfs.py
    )

    parser.add_argument("mountpoint")

    # TODO parse URL github:owner/repo/commit
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("commit")

    parser.add_argument(
        "-f",
        "--foreground",
        action="store_true",
        default=False,
        help="Run in the foreground",
    )

    #parser.add_argument("--schema", default=None, type=str)

    parser.add_argument("--chunk-size", default=2 ** 20, type=int)

    parser.add_argument("--disk-cache-size", default=2 ** 30, type=int)

    parser.add_argument("--disk-cache-dir", default="/tmp/githubfs_disk_cache") # TODO implement persistent cache

    parser.add_argument("--lru-capacity", default=400, type=int)

    parser.add_argument("--aws-profile", default=None, type=str)

    parser.add_argument(
        "--allow-other",
        action="store_true",
        default=False,
        help="Allow other users to access this fuse",
    )

    parser.add_argument("-l", "--logfile", default=None, type=str) # logfile

    if len(sys.argv) == 1:
        # with no args, show full help
        parser.print_help(sys.stderr)
        sys.exit(1)
    
    args = vars(parser.parse_args())

    if not op.isdir(args["mountpoint"]):
        print(
            "Mount point must be a directory: {}".format(args["mountpoint"]),
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("githubfs")
    #logger.setLevel(logging.DEBUG) # noisy! prints all return values

    if args["logfile"]:
        hdlr = logging.FileHandler(args["logfile"])
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(module)s: %(message)s"
        )
        hdlr.setFormatter(formatter)
        logger.addHandler(hdlr)

#    foreground: {foreground}
#    allow others: {allow_other}
    start_msg = """
githubfs.main
  mountpoint {mountpoint}
""".format(
        mountpoint=args["mountpoint"],
        foreground=args["foreground"],
        allow_other=args["allow_other"],
    )
    print(start_msg, file=sys.stderr)

    args['logger'] = logger

    """
    disk_cache_size=args["disk_cache_size"],
    disk_cache_dir=args["disk_cache_dir"],
    lru_capacity=args["lru_capacity"],
    chunk_size=args["chunk_size"],
    aws_profile=args["aws_profile"],
    logger=logger,

    owner=args["disk_cache_size"],
    repo=args["disk_cache_size"],
    commit=args["disk_cache_size"],

    # small test repo
    owner="milahu", repo="logic_fn", commit="3b882601217daf8bfd6e2acbcb1ef659e4659b33",

    # large repo
    #owner="TLATER", repo="nixpkgs", commit="c1b3f029a39f39e621eb0f9ab4c18acb2e7f74d0",
    """

    fuse = FUSE(
        GithubFs(
            **args
        ),
        args["mountpoint"],
        foreground=args["foreground"],
        allow_other=args["allow_other"],
        #debug=True, # noisy
        nothreads=True, # slower?
    )


if __name__ == "__main__":
    main()
