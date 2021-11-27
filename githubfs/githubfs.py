# based on
# https://github.com/higlass/simple-httpfs
# http://thepythoncorner.com/dev/writing-a-fuse-filesystem-in-python/
# https://github.com/dulwich/dulwich # git in pure python

import os
import os.path
from errno import EIO, ENOENT
from stat import S_IFDIR, S_IFREG
from fuse import FuseOSError, LoggingMixIn, Operations

import verify_github_api
from hexdump_canonical import hexdump_canonical

class GithubFs(LoggingMixIn, Operations):

    from init import __init__

    from getattr import getattr
    from readdir import readdir
    from read import read

    # helpers
    from getchunk import getchunk
    from _full_path import _full_path
    from getSize import getSize

    from write_methods import unlink, create, write # read only

    def destroy(self, path):
        self.disk_cache.close()
