from errno import EIO, ENOENT
from stat import S_IFDIR, S_IFREG
import time
from fuse import FuseOSError, LoggingMixIn, Operations
import os
from util import pretty_json, safe_print, dict_of_lstat, dict_of_statvfs
import verify_github_api

if True:


    def getattr(self, path, fh=None):
        if path not in self.patched_paths:
            # use lower_dir
            full_path = self._full_path(path)
            st = os.lstat(full_path)
            return dict_of_lstat(st)
            #return dict((key, getattr(st, key)) for key in ['st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid', 'st_blocks'])
            #return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid', 'st_blocks'))
            # why so complex? we must remove python-internal attributes
            #return st # AttributeError: 'os.stat_result' object has no attribute 'items'
            #print("dir(st) = " + pretty_json(dir(st)))
            #return {k: getattr(st, k) for k in dir(st) if k.startswith('st_')}
            #return dict(st) # TypeError: cannot convert dictionary update sequence element #0 to a sequence



        # FIXME getattr of path with unfetched parent tree
        try:
            if path in self.lru_attrs:
                #print("  cache hit")
                result = self.lru_attrs[path]
                result_str = f"mode {oct(result['st_mode'])[2:]}"
                if 'st_size' in result: # only files have size
                    result_str += f" size {result['st_size']}"
                print(f"+ getattr {path} -> {result_str} [cache hit]")
                return result

            #print("  cache miss")
            print(f"+ getattr {path} -> ...")

            # TODO check if path exists, otherwise throw
            #if not parent_path in self.tree_sha:
            #    raise FuseOSError(ENOENT) # no such file

            # FIXME httpfs -> githubfs

            path_parts = path.split("/")
            
            if not path in self.blob_sha and not path in self.tree_sha:

                print(f"  parent tree is missing -> try to fetch")

                # parent tree is missing -> try to fetch
                # TODO refactor copy-paste code: self.tree_data vs self.blob_data
                #if not path in self.blob_sha:
                #if not path in self.tree_data:
                #path_parts = path.split("/")
                # find parent in cache: bottom-up
                parent_path = None
                parent_depth = None
                for path_len in range((len(path_parts) - 1), 1, -1):
                    maybe_parent_path = "/".join(path_parts[0:path_len])
                    print(f"  path {path} -> try parent {maybe_parent_path}")
                    if maybe_parent_path in self.tree_data:
                        parent_path = maybe_parent_path
                        parent_depth = path_len
                        break
                if parent_path == None:
                    #print("  parent NOT found")
                    parent_path = '/'
                    parent_depth = 1
                #print(f"  path {path} -> found parent {parent_path}")
                # fetch entries: top-down
                #print(f"fetch parents from {parent_depth + 1} to {len(path_parts)}")
                #for path_len in range((parent_depth + 1), (len(path_parts) + 1)): # old ... (?)
                #for path_len in range((parent_depth), (len(path_parts))): # file?
                #for path_len in range((parent_depth), (len(path_parts) + 1)): # dir?
                for path_len in range((parent_depth + 1), (len(path_parts))): # file?
                    # TODO handle file vs dir
                    parent_path = "/".join(path_parts[0:path_len])
                    print(f"  parent_path = '{parent_path}'")
                    if not parent_path in self.tree_sha:
                        print(f"  parent_path {parent_path} not in tree_sha")
                        print(f"  getattr {path} -> no such file 1a")
                        raise FuseOSError(ENOENT) # no such file
                        # TODO also in getattr

                    print(f"  parent_path {parent_path} found in tree_sha")

                    #print(f"  fetch path {parent_path} @ path_len {path_len}")
                    print(f"  dl_tree {parent_path} {self.tree_sha[parent_path]}")

                    url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/{self.tree_sha[parent_path]}"
                    response = self.requests.get(url)
                    self.tree_data[parent_path] = response.json()
                    #print("  set tree_data %s" % parent_path)
                    verify_github_api.verify_tree(self, self.tree_sha[parent_path], self.tree_data[parent_path], parent_path)

                    # add subtree shas
                    # TODO refactor
                    path_prefix = '/' if parent_path == '/' else parent_path + '/'
                    #path_prefix = path + '/'
                    #if path == '/':
                    #    path_prefix = '/'
                    print(f"  add tree items of parent_path {parent_path}")
                    tree = self.tree_data[parent_path]['tree']
                    for tree_item in tree:
                        item_path = path_prefix + tree_item['path']
                        if tree_item['type'] == 'tree':
                            self.tree_sha[item_path] = tree_item['sha']
                        elif tree_item['type'] == 'blob':
                            self.blob_sha[item_path] = tree_item['sha']

            print(f"  fetch done")

            #if path == "/" or path in self.tree_data:
            if path in self.tree_data:
                # directory
                print(f"  path is directory")
                self.lru_attrs[path] = dict(
                    st_mode=(S_IFDIR | 0o555),
                    st_nlink=2
                )
                result = self.lru_attrs[path]
                result_str = f"mode {oct(result['st_mode'])[2:]}"
                if 'st_size' in result: # only files have size
                    result_str += f" size {result['st_size']}"
                print(f"+ getattr {path} -> {result_str}")
                return result

            #path_parts = path.split("/")
            parent_path = "/".join(path_parts[:-1])

            print(f"  path {path} -> parent_path {parent_path}") # debug

            if parent_path in self.tree_data:
                # file
                print(f"  path is file")
                parent_data = self.tree_data[parent_path]
                tree_item_path = path_parts[-1]
                print(f"  path {path} -> tree_item_path {tree_item_path}") # debug
                # TODO cache tree_item as blob_data[file_path]
                #print(f"  find path {tree_item_path} in tree " + pretty_json(parent_data['tree']))
                #print(f"  find path {tree_item_path} in parent_path {parent_path} with parent_data " + pretty_json(parent_data))
                # TODO handle truncated data ...
                tree_item = next(filter(lambda item: item['path'] == tree_item_path, parent_data['tree']), None)
                if tree_item == None:
                    #print("  no such file 1")
                    print(f"  getattr {path} -> no such file 1")
                    raise FuseOSError(ENOENT) # no such file
                item_path = path
                if tree_item['type'] == 'tree': # should not happen ... (?)
                    # dir
                    print(f"  path is dir 2 -> what?? expected file")
                    self.lru_attrs[path] = dict(
                        st_mode=(S_IFDIR | 0o555), # directory, read only
                        st_nlink=2
                    )
                else:
                    # file
                    #print('getattr debug 847: path = ' + path)
                    #print('getattr debug 847: tree_item = ' + pretty_json(tree_item))
                    print(f"  path is file 2")
                    file_mode = int(tree_item['mode'], 8)
                    if self.filemode_mask:
                        print(f"  getattr {path}: mask mode from {oct(file_mode)} to {oct(file_mode & self.filemode_mask)}")
                        file_mode = file_mode & self.filemode_mask
                    self.lru_attrs[path] = dict(
                        st_mode=file_mode,
                        st_nlink=1,
                        st_size=tree_item['size'],
                    )

                    print(f"  debug 920")

                result = self.lru_attrs[path]
                result_str = f"mode {oct(result['st_mode'])[2:]}"
                if 'st_size' in result: # only files have size
                    result_str += f" size {result['st_size']}"
                print(f"  getattr {path} -> {result_str}")
                return result



            print(f"  debug 930")


            # now path should be in blob_sha or tree_sha
            #if not path in self.blob_sha and not path in self.tree_sha:
            print(f"+ getattr {path} -> no such file 2")
            raise FuseOSError(ENOENT) # no such file



            if False:

                # TODO refactor copy-paste code: self.tree_data vs self.blob_data
                if not path in self.blob_sha:
                    # find parent in cache: bottom-up
                    parent_path = None
                    parent_depth = None
                    for path_len in range((len(path_parts) - 1), 1, -1):
                        maybe_parent_path = "/".join(path_parts[:path_len])
                        print(f"  path {path} -> parent? {parent_path}")
                        if maybe_parent_path in self.tree_data:
                            parent_path = maybe_parent_path
                            parent_depth = path_len
                            break
                    if parent_path == None:
                        #print("  parent NOT found")
                        parent_path = '/'
                        parent_depth = 1
                    print(f"  path {path} -> parent! {parent_path}")
                    # fetch entries: top-down
                    #print(f"fetch parents from {parent_depth + 1} to {len(path_parts)}")
                    for path_len in range((parent_depth + 1), (len(path_parts) + 1)):
                        parent_path = "/".join(path_parts[0:path_len])

                        if not parent_path in self.tree_sha:
                            raise FuseOSError(ENOENT) # no such file
                            # TODO also in getattr

                        #print(f"  fetch path {parent_path} @ path_len {path_len}")
                        print(f"  dl_tree {parent_path} {self.tree_sha[parent_path]}")
                        #print(f"+ gettree {path} {sha}") # todo?

                        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/{self.tree_sha[parent_path]}"
                        response = self.requests.get(url)
                        self.tree_data[parent_path] = response.json()
                        #print("  set tree_data %s" % parent_path)
                        verify_github_api.verify_tree(self, self.tree_sha[parent_path], self.tree_data[parent_path], parent_path)

                        # add subtree shas
                        # TODO refactor
                        path_prefix = '/' if parent_path == '/' else parent_path + '/'
                        #path_prefix = path + '/'
                        #if path == '/':
                        #    path_prefix = '/'
                        tree = self.tree_data[parent_path]['tree']
                        for tree_item in tree:
                            item_path = path_prefix + tree_item['path']
                            if tree_item['type'] == 'tree':
                                self.tree_sha[item_path] = tree_item['sha']
                            elif tree_item['type'] == 'blob':
                                self.blob_sha[item_path] = tree_item['sha']

                # TODO refactor ... if 'size' in tree_item:
                if path in self.blob_data:
                    # file
                    tree_item = self.blob_data[path]
                    #file_mode = S_IFREG | 0o444 # regular file, read only
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

                elif path in self.tree_data:
                    # dir
                    tree_item = self.tree_data[path]
                    self.lru_attrs[item_path] = dict(
                        st_mode=(S_IFDIR | 0o555), # directory, read only
                        st_nlink=2
                    )

                else:
                    raise FuseOSError(ENOENT) # no such file

                return self.lru_attrs[path]

                """
                # TODO remove old code??

                url = "{}:/{}".format(self.schema, path[:-2])

                print(f"  path {path} is file -> url {url}")

                # there's an exception for the -jounral files created by SQLite
                # TODO check this earlier, so we dont check twice
                "xxxx""
                if path.endswith("..-journal") or path.endswith("..-wal"):
                    size = 0
                else:
                    print("  call getSize, url = " + url)
                    size = self.getSize(url, blob_sha) # FIXME size is None
                    print("  call getSize -> size = " + repr(size))
                "xxxx""

                blob_sha = self.blob_sha[path]

                print("  call getSize, url = " + url)
                size = self.getSize(url, blob_sha) # FIXME? size is None
                print("  call getSize -> size = " + repr(size))

                # logging.info("head: {}".format(head.headers))
                # logging.info("status_code: {}".format(head.status_code))
                # print("url:", url, "head.url", head.url)

                if size is not None:
                    file_time = time.time()
                    self.lru_attrs[path] = dict(
                        st_mode=(S_IFREG | 0o644), # regular file. TODO read only? (0o444)
                        st_nlink=1,
                        st_size=size,
                        st_ctime=file_time,
                        st_mtime=file_time,
                        st_atime=file_time,
                    )
                else:
                    print("  size is None -> type is directory")
                    self.lru_attrs[path] = dict(
                        st_mode=(S_IFDIR | 0o555),
                        st_nlink=2
                    )

                return self.lru_attrs[path]
                """
        except Exception as ex:
            #self.logger.exception(ex)
            raise
