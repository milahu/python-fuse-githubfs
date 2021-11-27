# -*- coding: utf-8 -*-

import diskcache # https://github.com/grantjenks/python-diskcache/
import logging
import sys
import requests as requests_unwrapped
from stat import S_IFDIR, S_IFREG
import glob

from secret import github_token # TODO read from env or configfile
from lru_cache import LRUCache
from fetchers import HttpFetcher
from wrap_requests import wrap_requests
import verify_github_api

from util import pretty_json

if True:
    """
        disk_cache_size=2 ** 30,
        disk_cache_dir="/tmp/xx",
        lru_capacity=400,
        chunk_size=2 ** 20,
        aws_profile=None,
        logger=None,
        owner=None,
        repo=None,
        commit=None
    """

    def __init__(self, **kwargs):

        print("+ init githubfs")

        for key in kwargs:
            setattr(self, key, kwargs[key])

        #self.schema = "https" # old code from simple-httpfs

        # passthrough fs
        # http://thepythoncorner.com/dev/writing-a-fuse-filesystem-in-python/

        self.requests = requests_unwrapped
        wrap_requests(self.requests, github_token)

        self.lru_cache = LRUCache(capacity=self.lru_capacity)
        self.lru_attrs = LRUCache(capacity=self.lru_capacity)
        #self.logger = logger
        self.log = self.logger
        self.last_report_time = 0
        self.total_requests = 0
        self.getting = set()

        self.filemode_mask = None
        #self.filemode_mask = 0o777555 # mask to read only
        # con: mostly not needed, since file self.owner is root
        # con: filemode is needed to compute checksums

        #self.owner = owner
        #self.repo = repo
        #self.commit = commit

        if self.owner == None or self.repo == None or self.commit == None:
            print("required argumenets: owner repo commit")
            sys.exit(1) # TODO raise?

        #self.foreground = True # no effect -> see __main__.py

        if not self.logger:
            self.logger = logging.getLogger(__name__)

        #self.logger.info("Starting with disk_cache_size: %d", disk_cache_size)

        self.fetcher = HttpFetcher(self.logger)

        """
        if schema == "http" or schema == "https":
            self.fetcher = HttpFetcher(self.logger)
        elif schema == "ftp":
            self.fetcher = FtpFetcher()
        elif schema == "s3":
            self.fetcher = S3Fetcher(aws_profile, self.logger)
        else:
            raise ("Unknown schema: {}".format(schema))
        """

        print(f"  init: disk_cache_dir = {self.disk_cache_dir}")
        print(f"  init: disk_cache_size = {self.disk_cache_size}")
        print(f"  init: chunk_size = {self.chunk_size}")

        self.disk_cache = diskcache.Cache(self.disk_cache_dir, size_limit=self.disk_cache_size)
        # TODO implement
        #self.disk_cache = GitStore('/tmp/githubfs_store')

        self.total_blocks = 0
        self.lru_hits = 0
        self.lru_misses = 0

        self.disk_hits = 0
        self.disk_misses = 0
        #self.chunk_size = chunk_size

        # init root directory
        # https://api.github.com/repos/TLATER/nixpkgs/git/commits/c1b3f029a39f39e621eb0f9ab4c18acb2e7f74d0
        # https://api.github.com/repos/TLATER/nixpkgs/git/trees/16b11d75cab9046e4be9e331f02dc837af481a06

        self.commit_data = {}
        self.tree_sha = {}
        self.tree_data = {}
        self.blob_sha = {} # TODO? self.blob_data = {} -> LRU cache of file contents
        # TODO cache data to disk -> persistent
        self.timezone_cache = {}


        self.patched_paths = set() # TODO remove?
        """
        # old code. dirty solution: overlay only changed files
        # but this breaks when the store_dir is too old (version mismatch)
        # TODO
        # https://api.github.com/repos/NixOS/nixpkgs/pulls/136343/files
        pull_id = 136343
        print(f"  dl_pull / {pull_id}")
        url = f"https://api.github.com/repos/NixOS/nixpkgs/pulls/{pull_id}/files" # url of upstream repo
        response = self.requests.get(url)
        data = response.json()
        self.patched_paths = set()
        for data_item in data:
            #print(pretty_json(data_item))
            p = '/' + data_item['filename']
            print("  add patched path: " + p)
            self.patched_paths.add(p)
            # sample filename: pkgs/applications/networking/browsers/firefox/common.nix
        """



        # build cache of local git objects
        # TODO use more local nixpkgs dirs -> /nix/store/*-nixpkgs-*? where are channels stored?
        # we must traverse the file-tree depth-first (bottom-up)
        # to first build blob objects and then build tree objects

        import os
        import os.path
        import verify_github_api
        import time
        import subprocess

        self.verify_blob_sha_with_git_hash_object = False
        #self.verify_blob_sha_with_git_hash_object = True # slow. useful for debug / audit of code

        self.git_cache_dir = '/home/user/src/nixos/nixpkgs_git_cache' # global cache stores symlinks of all objects

        self.git_objects_dir = self.git_cache_dir + '/objects'
        # our private folders inside the .git folder
        self.git_stores_dir = self.git_cache_dir + '/_stores'
        self.git_shaidx_dir = self.git_cache_dir + '/_shaidx'

        for d in [self.git_objects_dir, self.git_stores_dir, self.git_shaidx_dir]:
            if not os.path.isdir(d):
                os.makedirs(d)

        import collections

        self.store_dirs = collections.OrderedDict()

        # WONTFIX? /nix/store is lossy! file permissions are reduced to readonly -> all trees are wrong
        # workaround: do 'chmod +w' on files. this should restore the original permissions in MOST cases
        nix_store_globs = [
            (4, '/nix/store/*-nixpkgs-*/pkgs/top-level/all-packages.nix'), # nixpkgs in nix store
            (5, '/nix/store/*-nixos-*/nixos/pkgs/top-level/all-packages.nix'), # nixos channels in nix store
        ]
        for store_dir_len, glob_str in nix_store_globs:
            for f in glob.glob(glob_str):
                nix_sha = f.split("/")[3].split("-")[0]
                store_name = 'nix-' + nix_sha
                store_dir = "/".join(f.split("/")[:store_dir_len])
                self.store_dirs[store_name] = store_dir

        # globbing all /nix/store for 'pkgs/top-level/all-packages.nix' takes too long
        # currently 100K items in /nix/store ... maybe with updatedb + locate

        # add non-nix-store paths last, to prefer nix-store paths, and to avoid replacing symlinks
        # find all the nixpkgs!
        # $ find $HOME -path '*/pkgs/top-level/all-packages.nix'
        # TODO for now, we must manually reset these repose to a 'clean' state = git stash/commit + git checkout master
        # 'git status' should say 'clean'

        self.store_dirs['my_first_store'] = "/home/user/src/nixos/nixpkgs-2021-10-12/nixpkgs"
        # FIXME missing root tree at end of file
        # /home/user/src/nixos/nixpkgs_git_cache/_shaidx/my_first_store

        self.store_dirs['my_second_store'] = "/home/user/src/nixos/milahu--nixos-packages/nur-packages/pkgs/jdownloader/nixpkgs-git/nixpkgs"

        t1_all_store_dirs = time.time()

        do_debug = False
        #do_debug = True

        num_blobs = 0
        num_trees = 0
        num_objects = 0
        t1_tick = time.time()
        progress_tick_interval = 1000 # show progress every n objects

        filemode_of_file = dict()
        blob_sha_of_file = dict()
        tree_sha_of_dir = dict()

        # loop stores
        for store_name, store_dir in self.store_dirs.items():

            print(f"build git tree of store {store_name} in {store_dir}")
            t1_store_dir = time.time()
            is_git_repo = os.path.exists(store_dir + '/.git')
            store_dir_is_in_nix_store = store_dir.startswith('/nix/store/')

            # add symlink to store dir
            # for "variable" (movable) link-targets, we use two symlinks
            # for "constant" link-targets (e.g. /nix/store), we can use one symlink = link directly from git object to nix store
            symlink_path = None if store_dir_is_in_nix_store else self.git_stores_dir + '/' + store_name
            shaidx_path = self.git_shaidx_dir + '/' + store_name # 4.5 MByte for 200 MByte repo (nixpkgs, my_first_store). could be worse

            # TODO dont link /nix/store ...
            if not store_dir_is_in_nix_store and not os.path.exists(symlink_path):
                os.symlink(store_dir, symlink_path)
                # TODO avoid generating so many files
                # instead, use sqlite database + fuse filesystem

            dirpath_prefix_len = len(store_dir) # no +1 = do NOT strip leading / in paths

            # TODO database:
            #   map dirpath to tree_sha
            #   map tree_sha to dirpath
            #   ...
            #   how does git store this? index files? compression?

            # we assume that .gitignore would no change the tree (simpler)

            if is_git_repo:
                # make sure that git tree is clean
                git_dirty_files = subprocess.run(['git', 'status', '--porcelain=v1'], cwd=store_dir, text=True).stdout
                if git_dirty_files != None:
                    print("git is dirty:")
                    print(f'( cd {store_dir} && git status --porcelain=v1 )')
                    print(git_dirty_files)
                    print("fatal error")
                    sys.exit(1) # TODO better
            # else: /nix/store is readonly ... should be clean

            # load cache
            # TODO better cache ... diskcache? custom version of diskcache? something with sqlite backend ...
            if os.path.exists(shaidx_path):
                with open(shaidx_path, 'r') as shaidx_file:
                    print(f"parse shaidx_path {shaidx_path}")
                    #read_str = shaidx_file.read(100)
                    #print(f"read_str {read_str}")
                    for line in shaidx_file.readlines():
                        # note. file could be corrupted
                        # sample error: line[-1] != '\n'
                        #print(f"  line = '{line[:-1]}'")
                        sha = line[5:45]
                        mode = line[46:52]
                        path = line[53:-1] # last is newline. assume unix file format = no \r\n nonsense
                        # TODO use git index file format (?)
                        if line.startswith('blob '):
                            blob_sha_of_file[path] = sha
                            filemode_of_file[path] = int(mode, 8)
                        elif line.startswith('tree '):
                            tree_sha_of_dir[path] = sha
                    num_blobs = len(blob_sha_of_file)
                    num_trees = len(tree_sha_of_dir)
                    num_objects = num_blobs + num_trees
                    print(f"loaded from cache: {num_blobs} blobs + {num_trees} trees = {num_objects} objects")

            # loop files + dirs (bottom-up)
            with open(shaidx_path, 'a') as shaidx_file:
                for dirpath_abs, subdirs, filenames in os.walk(store_dir, topdown=False, followlinks=False):
                    dirpath = dirpath_abs[dirpath_prefix_len:] # on windows, can contain backslashes ... (WTF windows?)
                    if dirpath == '':
                        dirpath = '/'
                    if is_git_repo and (dirpath.startswith('/.git/') or dirpath == '/.git'):
                        # skip git-internal files
                        continue
                    if dirpath in tree_sha_of_dir:
                        # done
                        continue
                    tree_items = [] # files + dirs

                    # loop files
                    for filename in filenames:
                        filepath = (dirpath + '/' + filename) if dirpath != '/' else ('/' + filename)
                        blob_sha = None
                        filemode = None
                        if filepath in blob_sha_of_file:
                            blob_sha = blob_sha_of_file[filepath]
                            filemode = filemode_of_file[filepath]
                        else:
                            filepath_abs = dirpath_abs + '/' + filename
                            t1 = time.time()
                            blob_sha = verify_github_api.hash_blob_body(open(filepath_abs, 'rb').read())
                            dt_py = time.time() - t1
                            if is_git_repo and self.verify_blob_sha_with_git_hash_object:
                                # paranoid/strict and slow
                                # about 20x slower than hashing in python (subprocess overhead)
                                t1 = time.time()
                                blob_sha_expected = subprocess.run(["git", "hash-object", filepath[1:]], capture_output=True, cwd=store_dir, text=True).stdout[:-1]
                                dt_c = time.time() - t1
                                if blob_sha != blob_sha_expected:
                                    print("  bad blob")
                                    print(f"    {blob_sha} actual")
                                    print(f"    {blob_sha_expected} expected")
                                    print(f"( cd {store_dir} && git hash-object {filepath[1:]} )")
                                    sys.exit(1)
                                if do_debug:
                                    print("blob %s %s py=%f c=%f c/py=%f" % (blob_sha, filepath, dt_py*1000, dt_c*1000, dt_c/dt_py))
                            else:
                                if do_debug:
                                    print("blob %s %s" % (blob_sha, filepath))

                            # assume that cached files are symlinked
                            obj_dir = self.git_objects_dir + '/' + blob_sha[:2]
                            if not os.path.exists(obj_dir):
                                os.mkdir(obj_dir)

                            symlink_path = obj_dir + '/' + blob_sha[2:]
                            symlink_target = ''

                            if store_dir_is_in_nix_store:
                                symlink_target = store_dir + filepath
                            else:
                                symlink_target = '../../_stores/' + store_name + filepath
                            if os.path.exists(symlink_path):
                                old_target = os.readlink(symlink_path)
                                if old_target.startswith('../') and store_dir_is_in_nix_store:
                                    # remove old symlink
                                    # prefer symlinks to /nix/store (more stable)
                                    os.unlink(symlink_path)
                            if not os.path.exists(symlink_path):
                                if do_debug:
                                    print("%s  ->  %s" % (symlink_path, symlink_target)) # debug
                                os.symlink(symlink_target, symlink_path)

                            #from stat import S_IFDIR, S_IFREG
                            import stat

                            if do_debug:
                                time.sleep(0.1) # debug

                            filemode = os.lstat(filepath_abs).st_mode
                            # not needed. only files in filenames list
                            #if filemode & stat.S_IFDIR != 0:
                            #    filemode = 0o40000

                            if store_dir_is_in_nix_store:
                                # workaround to restore writable files. LOSSY = some files will break
                                filemode = filemode | 0o200 # = chmod +w

                            shaidx_file.write("blob %s %s %s\n" % (blob_sha, oct(filemode)[2:].zfill(6), filepath))

                        sortkey = filename
                        tree_items.append((sortkey, filename, filemode, blob_sha))

                        num_blobs += 1
                        num_objects += 1

                        # show progress
                        if (num_objects % progress_tick_interval == 0):
                            dt_tick = time.time() - t1_tick
                            t1_tick = time.time() # reset
                            print(f"  done {num_blobs} blobs + {num_trees} trees = {num_objects} objects @ {dt_tick*1000} ms/{progress_tick_interval}obj")

                    # loop dirs
                    #if do_debug:
                    #    print(f"dirpath = '{dirpath}'")
                    for subdir in subdirs:
                        subdirpath = (dirpath + '/' + subdir) if dirpath != '/' else ('/' + subdir)
                        if is_git_repo and (subdirpath.startswith('/.git/') or subdirpath == '/.git'):
                            # ignore git-internal files
                            continue
                        tree_sha = tree_sha_of_dir[subdirpath]
                        # implementation detail of git
                        # append / after dirname before sorting, to get the correct sort-order
                        sortkey = subdir + '/'
                        tree_items.append((sortkey, subdir, 0o40000, tree_sha))

                    tree_items.sort(key=lambda x: x[0])

                    import hashlib

                    # debug
                    if do_debug:
                        print("tree items for the next tree:")
                        # similar output: git cat-file tree -p $sha  # -p = printable ascii, no raw binary
                        for _sortkey, name, mode, sha in tree_items:
                            _type = "tree" if mode == 0o40000 else "blob"
                            print("  %s %s %s %s" % (_type, sha, oct(mode)[2:], name))

                    t1 = time.time()
                    def bytes_mode(mode):
                        # TODO left padding with zeros? (width = 6 chars)
                        #return oct(mode)[2:].encode('ascii').zfill(6)
                        return oct(mode)[2:].encode('ascii')

                    # loop tree_items
                    tree_body = b"".join([
                        bytes_mode(mode) + b" " + name.encode('utf8') + b"\0" + bytes.fromhex(sha)
                        for _sortkey, name, mode, sha in tree_items
                    ])
                    tree_data = b"tree " + str(len(tree_body)).encode('ascii') + b"\0" + tree_body
                    tree_sha = hashlib.sha1(tree_data).hexdigest()
                    dt_py = time.time() - t1 # bad comparison, i know. just want to show the subprocess overhead

                    tree_sha_of_dir[dirpath] = tree_sha
                    shaidx_file.write("tree %s 040000 %s\n" % (tree_sha, dirpath))

                    from hexdump_canonical import hexdump_canonical

                    if is_git_repo and self.verify_blob_sha_with_git_hash_object:
                        # paranoid/strict and slow
                        # about 20x slower than hashing in python (subprocess overhead)
                        t1 = time.time()
                        # git cat-file blob 58dca6479b84517295b227c40cc8b5203827b579
                        tree_body_expected = subprocess.run(["git", "cat-file", "tree", tree_sha], capture_output=True, cwd=store_dir).stdout
                        dt_c = time.time() - t1
                        if tree_body != tree_body_expected:
                            print("bad tree")
                            print("  dir:")
                            print(dirpath_abs)

                            print(f"position in os.walk: blob {num_blobs} tree {num_trees}")

                            # actual tree sha by path
                            tree_sha_expected = subprocess.run(["git", "rev-parse", "HEAD:" + dirpath[1:]], capture_output=True, cwd=store_dir, text=True).stdout[:-1]
                            print(f"( cd {store_dir} && git rev-parse 'HEAD:{dirpath[1:]}' )") # TODO escape quotes in dirpath (shlex?)
                            print("tree_sha_expected = " + tree_sha_expected)

                            print("actual tree body:")
                            hexdump_canonical(tree_body)
                            print("expected tree body:")

                            tree_body_expected = subprocess.run(["git", "cat-file", "tree", tree_sha_expected], capture_output=True, cwd=store_dir).stdout
                            print(f"( cd {store_dir} && git cat-file tree {tree_sha_expected} | hexdump -C )")
                            hexdump_canonical(tree_body_expected)

                            print("actual tree items:")
                            # similar output: git cat-file -p $sha   # -p = printable ascii, no raw binary
                            for _sortkey, name, mode, sha in tree_items:
                                _type = "tree" if mode == 0o40000 else "blob"
                                print("%s %s %s    %s" % (oct(mode)[2:].zfill(6), _type, sha, name))

                            print("expected tree items:")
                            tree_body_expected_printable = subprocess.run(["git", "cat-file", "-p", tree_sha_expected], capture_output=True, cwd=store_dir, text=True).stdout
                            print(f"( cd {store_dir} && git cat-file -p {tree_sha_expected} )")
                            print(tree_body_expected_printable)

                            sys.exit(1)
                        if do_debug:
                            print("tree %s %s py=%f c=%f c/py=%f" % (tree_sha, dirpath, dt_py*1000, dt_c*1000, dt_c/dt_py))
                    else:
                        if do_debug:
                            print("tree %s %s" % (tree_sha, dirpath))

                    num_trees += 1
                    num_objects += 1

                    # show progress
                    if (num_objects % progress_tick_interval == 0):
                        dt_tick = time.time() - t1_tick
                        t1_tick = time.time() # reset
                        print(f"  done {num_blobs} blobs + {num_trees} trees = {num_objects} objects @ {dt_tick*1000} ms/{progress_tick_interval}obj")

                    if do_debug:
                        time.sleep(0.1) # debug

            dt_store_dir = time.time() - t1_store_dir

            print(f"  done sha tree of {store_dir} in {dt_store_dir} seconds")
            #print(f"    dt = {dt_store_dir} seconds = {dt_store_dir/(num_objects)*1000} ms/object")
            print(f"    cache file: {shaidx_path}")
            print(f"    cache size: {num_blobs} blobs + {num_trees} trees = {num_objects} objects")

            # TODO add tree_sha_of_dir + blob_sha_of_file to global store, keyed by store_name
            # TODO add reverse lookup from sha to filepath -> need virtual fs for trees

        dt_all_store_dirs = time.time() - t1_all_store_dirs
        print(f"done all {len(self.store_dirs)} store_dirs in {dt_all_store_dirs}")



        # download commit = entry point to git tree
        print(f"  dl_comm / {self.commit}")
        #print(f"+ getcomm {self.commit}") # todo?

        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/commits/{self.commit}"
        response = self.requests.get(url)
        
        if response.status_code != 200:
            print(f"  HTTP status {response.status_code} from {url}")
            if response.status_code == 403:
                print(f"  api quota exceeded = rate limit exceeded")
                # TODO workaround: scrape webinterface
                # or use graphql api (requires login with api token)
            raise Exception("fatal")

        #self.logger.info("got status %s", response.status_code)
        #response.raise_for_status() # TODO ?
        #file_data = np.frombuffer(response.content, dtype=np.uint8)
        #file_size = file_data.size

        data = response.json()
        verify_github_api.verify_commit(self, self.commit, data)
        self.commit_data[self.commit] = data

        self.tree_sha['/'] = data['tree']['sha']
        #print("  set tree_sha %s %s" % (data['tree']['sha'], '/'))



        # get root tree = list root dir
        # TODO maybe use cached tree
        path = '/'
        print(f"  dl_tree {path} {self.tree_sha[path]}")
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/{self.tree_sha[path]}"
        response = self.requests.get(url)
        self.tree_data[path] = response.json()
        #print("  set tree_data %s" % path)
        verify_github_api.verify_tree(self, self.tree_sha[path], self.tree_data[path], path)

        # add subtree shas
        # TODO refactor with line 560: for tree_item in self.tree_data
        path_prefix = '/' if path == '/' else path + '/'
        #path_prefix = path + '/'
        #if path == '/':
        #    path_prefix = '/'
        tree = self.tree_data[path]['tree']
        for tree_item in tree:
            item_path = path_prefix + tree_item['path']
            if tree_item['type'] == 'tree':
                # debug
                #print("  set tree_sha %s %s" % (tree_item['sha'], item_path))
                self.tree_sha[item_path] = tree_item['sha']
                #print("  set tree_sha %s %s" % (tree_item['sha'], item_path)) # debug
                # add directory to attrs cache
                # TODO refactor with readdir
                self.lru_attrs[item_path] = dict(
                    st_mode=(S_IFDIR | 0o555), # directory, read only
                    st_nlink=2
                )
            elif tree_item['type'] == 'blob':
                #print("  set blob_sha %s %s" % (tree_item['sha'], item_path)) # debug
                self.blob_sha[item_path] = tree_item['sha']
                # add file to attrs cache
                # TODO refactor with readdir

                file_mode = int(tree_item['mode'], 8)
                if self.filemode_mask:
                    print(f"+ getattr {path}: mask mode from {oct(file_mode)} to {oct(file_mode & self.filemode_mask)}")
                    file_mode = file_mode & self.filemode_mask
                self.lru_attrs[item_path] = dict(
                    st_mode=(file_mode),
                    st_nlink=1,
                    st_size=tree_item['size'],
                    #st_ctime=file_time,
                    #st_mtime=file_time,
                    #st_atime=file_time,
                )

        #print("data = " + repr(self.tree_data['/']))
        #print("data.tree[0].path = " + repr(self.tree_data['/']['tree'][0]['path']))
