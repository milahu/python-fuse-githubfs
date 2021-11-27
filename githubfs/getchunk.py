
if True:

    # TODO rename to getchunk
    def getchunk(self, path, url, chunk_num):
        #print(f"+ getchunk {path} # chunk {chunk_num}") # TODO remove chunk_num? probably github does not support range requests on raw urls
        print(f"+ getchunk {path}")
        """
        Get a data block from a URL. Blocks are 256K bytes in size

        Parameters:
        -----------
        url: string
            The url of the file we want to retrieve a block from
        chunk_num: int
            The # of the 256K'th block of this file
        """
        cache_key = "{} {} {}".format(url, self.chunk_size, chunk_num)
        #cache_key = url
        #cache = self.disk_cache

        #print(f"  cache_key = " + cache_key)

        self.total_blocks += 1

        if cache_key in self.lru_cache:
            print(f"  getchunk: cache hit @ lru")
            self.lru_hits += 1
            hit = self.lru_cache[cache_key]
            return hit
        else:
            print(f"  getchunk: cache miss @ lru")
            self.lru_misses += 1

            if cache_key in self.disk_cache: # TODO wtf? where was this added?
                print(f"  getchunk: cache hit @ disk")
                #self.logger.info("cache hit: %s", cache_key)
                try:
                    chunk_data = self.disk_cache[cache_key] # TODO wtf? where was this added?
                    # -> TRACE dtype=np.
                    # type of cache-content is <class 'numpy.ndarray'>

                    # TODO rename chunk_data to file_data (contains the whole file)
                    self.disk_hits += 1
                    self.lru_cache[cache_key] = chunk_data
                    print(f"  getchunk: cache hit @ disk -> {len(chunk_data)} bytes + type {type(chunk_data)}")

                    # TRACE

                    # FIXME unhandled exception here will crash the whole fuse mount ...
                    # -> handle all exceptions in try block, raise fuseosexception


                    return chunk_data
                except KeyError:
                    # TODO what is this?
                    print(f"  getchunk: cache miss @ disk")
                    pass

            self.disk_misses += 1
            chunk_start = chunk_num * self.chunk_size

            chunk_end = chunk_start + self.chunk_size - 1 # TODO verify: off by one error?
            #chunk_end = chunk_start + self.chunk_size

            # TRACE here we download blob_data

            blob_sha = self.blob_sha[path]
            attr = self.getattr(path) # TODO verify
            blob_size = attr['st_size']

            safe_print(f"  getchunk: blob_sha {blob_sha}")
            safe_print(f"  getchunk: blob_size {blob_size}")
            safe_print(f"  getchunk: dl_blob {path}")
            #print(f"  dl_blob {path} # chunk {chunk_num}")
            #self.logger.info("getting data %s", cache_key)
            """
            # note: byte range is INCLUSIVE -> chunk_end index is included in result
            chunk_data = self.fetcher.get_data(
                url, chunk_start, chunk_start + self.chunk_size - 1, blob_sha
            )
            """
            blob_data = None
            if blob_sha in self.lru_cache:
                blob_data = self.lru_cache[blob_sha]
            elif blob_sha in self.disk_cache:
                blob_data = self.disk_cache[blob_sha]
                self.lru_cache[blob_sha] = blob_data
            else:
                # fetch
                #blob_data = self.fetcher.get_data(url, 0, blob_size)
                blob_data = self.fetcher.get_data(url, 0, blob_size-1) # range is INCLUSIVE
                self.lru_cache[blob_sha] = blob_data
                self.disk_cache[blob_sha] = blob_data
                # verify blob after download
                verify_github_api.verify_blob(self, blob_sha, blob_size, blob_data.tobytes(), path)

            # TODO rename "block" to "chunk"
            chunk_data = blob_data[chunk_start:(chunk_end + 1)] # note: range is EXCLUSIVE, so we must add +1

            print(f"  getchunk: debug 1420: cache add " + cache_key)
            self.lru_cache[cache_key] = chunk_data
            self.disk_cache[cache_key] = chunk_data

        return chunk_data

