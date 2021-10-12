REPORT_INTERVAL = 60
#CLEANUP_INTERVAL = 60
#CLEANUP_EXPIRED = 60
#DISK_CACHE_SIZE_ENV = "HTTPFS_DISK_CACHE_SIZE"
#DISK_CACHE_DIR_ENV = "HTTPFS_DISK_CACHE_DIR"

from errno import EIO, ENOENT
import time
import numpy
from fuse import FuseOSError, LoggingMixIn, Operations

if True:


    def read(self, path, size, offset, fh):
        # TODO rename size to read_size
        # TODO rename offset to read_offset

        if not path in self.patched_paths:
            # passthrough
            os.lseek(fh, offset, os.SEEK_SET)
            return os.read(fh, size)

        print(f"+ read    {path} + offset {offset} + size {size}")

        t1 = time.time()

        #self.logger.debug("read %s %s %s", path, offset, size)

        if t1 - self.last_report_time > REPORT_INTERVAL:
            """
            self.logger.info(
                "lru hits: {} lru misses: {} disk hits: {} total_requests: {}".format(
                    self.lru_hits,
                    self.lru_misses,
                    self.disk_hits,
                    self.disk_misses,
                    self.total_requests,
                )
            )
            """
            pass
        try:
            self.total_requests += 1

            # FIXME handle github paths. map path to blob url
            # TODO refactor copy-paste code: self.tree_data vs self.blob_data
            if not path in self.blob_sha:
                print(f"  read: path not in self.blob_sha")
                path_parts = path.split("/")
                # find parent in cache: bottom-up
                parent_path = None
                parent_depth = None
                for path_len in range((len(path_parts) - 1), 1, -1):
                    maybe_parent_path = "/".join(path_parts[0:path_len])
                    print(f"  read: path {path} -> parent? {parent_path}")
                    if maybe_parent_path in self.tree_data:
                        parent_path = maybe_parent_path
                        parent_depth = path_len
                        break
                if parent_path == None:
                    #print("  parent NOT found")
                    parent_path = '/'
                    parent_depth = 1
                print(f"  read: path {path} -> parent! {parent_path}")
                # fetch entries: top-down
                #print(f"fetch parents from {parent_depth + 1} to {len(path_parts)}")
                for path_len in range((parent_depth + 1), (len(path_parts) + 1)):
                    parent_path = "/".join(path_parts[0:path_len])

                    if not parent_path in self.tree_sha:
                        raise FuseOSError(ENOENT) # no such file
                        # TODO also in getattr

                    #print(f"  fetch path {parent_path} @ path_len {path_len}")
                    print(f"  read: dl_tree {parent_path} {self.tree_sha[parent_path]}")

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

            # now path should be in blob_sha
            if not path in self.blob_sha:
                print(f"  read: no such file")
                raise FuseOSError(ENOENT) # no such file

            sha = self.blob_sha[path]

            print(f"  read: path in self.blob_sha -> {sha}")

            #path_parts = path.split("/")
            #parent_path = "/".join(path_parts[:-1])

            attr = self.getattr(path) # TODO verify
            blob_size = attr['st_size']

            #url = "{}:/{}".format(self.schema, path[:-2])
            #url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/blobs/{sha}"
            #url = f"https://github.com/{self.owner}/{self.repo}/git/blobs/{sha}"
            url = f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.commit}{path}"

            """
            self.logger.debug("read url: {}".format(url))
            self.logger.debug(
                "offset: {} - {} request_size (KB): {:.2f} block: {}".format(
                    offset,
                    offset + size - 1,
                    size / 2 ** 10,
                    offset // self.chunk_size,
                )
            )
            """

            # size != blob_size
            output = numpy.zeros((size,), numpy.uint8)

            t1 = time.time()

            # nothing fetched yet
            last_fetched = -1
            curr_start = offset

            while last_fetched < offset + size:
                chunk_num = curr_start // self.chunk_size
                chunk_start = self.chunk_size * chunk_num

                chunk_id = (url, chunk_num)
                while chunk_id in self.getting:
                    # block following calls to read
                    time.sleep(0.05)

                self.getting.add(chunk_id)
                print(f"  read: call getchunk {url} {chunk_num}")
                chunk_data = self.getchunk(path, url, chunk_num)
                print(f"  read: getchunk -> {len(chunk_data)} bytes")
                self.getting.remove(chunk_id)

                """
                print("  first 128 bytes of chunk_data:")
                hexdump_canonical(chunk_data[:128])
                print("  last 128 bytes of chunk_data:")
                hexdump_canonical(chunk_data[-128:])
                """

                data_start = (
                    curr_start - chunk_num * self.chunk_size
                )

                data_end = min(self.chunk_size, offset + size - chunk_start)
                data = chunk_data[data_start:data_end]
                print(f"  read: data = {len(data)} bytes")

                """
                print("  first 128 bytes of data:")
                hexdump_canonical(data[:128])
                print("  last 128 bytes of data:")
                hexdump_canonical(data[-128:])
                """

                print(f"  chunk {chunk_num} from {chunk_start} to {chunk_start + self.chunk_size}")
                print(f"  data  {chunk_num} from {data_start} to {data_end}")

                d_start = curr_start - offset
                print(f"  read: output[{d_start} : {d_start + len(data)}] = data")
                output[d_start : d_start + len(data)] = data

                last_fetched = curr_start + (data_end - data_start)
                curr_start += data_end - data_start

            _bytes = bytes(output)

            """
            print(f"  read    {path} + offset {offset} + size {size}")
            print("  first 128 bytes of output:")
            hexdump_canonical(_bytes[:128])
            print("  last 128 bytes of output:")
            hexdump_canonical(_bytes[-128:])
            """

            """
            + read    /pkgs/top-level/all-packages.nix + offset 917504 + size 131072
            read: path in self.blob_sha -> daa8d9cd38564425c72e7f53fd72c5a6a5464348
            + getattr /pkgs/top-level/all-packages.nix -> mode 100644 size 1083238 [cache hit]
            + read    /pkgs/top-level/all-packages.nix + offset 1048576 + size 36864
            read: path in self.blob_sha -> daa8d9cd38564425c72e7f53fd72c5a6a5464348
            + getattr /pkgs/top-level/all-packages.nix -> mode 100644 size 1083238 [cache hit]
            read: call getchunk https://raw.githubusercontent.com/TLATER/nixpkgs/c1b3f029a39f39e621eb0f9ab4c18acb2e7f74d0/pkgs/top-level/all-packages.nix 1
            + getchunk /pkgs/top-level/all-packages.nix
            getchunk: cache miss @ lru
            getchunk: cache hit @ disk
            getchunk: cache hit @ disk -> 34662 bytes + type <class 'numpy.ndarray'>
            read: getchunk -> 34662 bytes
            read: data = 34662 bytes
            read: output[0 : 34662] = data
            first 128 bytes of output:
            hexdump: 128 bytes
            00000000  70 20 3d 20 63 61 6c 6c  50 61 63 6b 61 67 65 20  |p = callPackage |
            00000010  2e 2e 2f 74 6f 6f 6c 73  2f 70 61 63 6b 61 67 65  |../tools/package|
            00000020  2d 6d 61 6e 61 67 65 6d  65 6e 74 2f 6e 69 78 2d  |-management/nix-|


            output file: note the ^@ -> error byte
            'p = callPackage ' is start of chunk


            nix-template-rpm = callPackage ../build-support/templaterpm { inherit (pythonPackages) python toposort; };

            nix-t^@p = callPackage ../tools/package-management/nix-top { };

            nix-tree = haskell.lib.justStaticExecutables (haskellPackages.nix-tree);



            -> off by one error
            chunk 0 ends at 'nix-t'
            chunk 1 starts at 'p = callPackage ../tools/package-management/nix-top { };'

            ^@ is NULL byte

            """

            return _bytes

        except Exception as ex:
            self.logger.exception(ex)
            raise
