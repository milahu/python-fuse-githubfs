if True:



    def getSize(self, url, blob_sha):
        print("+ getSize: url = " + url)
        try:
            #return self.fetcher.get_size(url)
            # FIXME get file size from self.tree_data
            safe_print("  getSize: call fetcher.get_size") # FIXME not printed
            size, file_data = self.fetcher.get_size(url)


            print("  getSize: type(file_data) = " + repr(type(file_data)))
            if type(file_data) == type(None): # file_data is None or numpy.ndarray
                print("  getSize: file_data is None -> size = " + repr(size))
                return size

            # else ...
            
            # FIXME where is file_data??
            # wrong file size
            # 1089383 expected
            # 1048576 actual
            #   40807 diff
            # -> chunk for read() ... ? where is full file?
            # TODO convert numpy to bytes, or, verify earlier, before converting to numpy
            #verify_github_api.verify_blob(self, self.blob_sha[path], chunk_data, path)
            #print(f"  cache hit @ disk -> tobytes type {type(chunk_data.tobytes())}") # debug

            path = "/" + url.split("/")[6:].join("/")
            attr = self.getattr(path) # TODO verify
            blob_size = attr['st_size']
            print(f"  getSize: expected size {blob_size}") # debug

            verify_github_api.verify_blob(self, self.blob_sha[path], blob_size, chunk_data.tobytes(), path)






            print("  getSize: add file_data to cache")

            # this loop is simpler than in in "def read"

            """
            # TODO maybe ...
            cache_key = blob_sha
            """

            object_data = file_data

            cache_key = url

            self.lru_cache[cache_key] = object_data
            self.disk_cache[cache_key] = object_data

            """
            last_fetched = -1
            curr_start = 0
            while curr_start < size:
                chunk_num = curr_start // self.chunk_size
                chunk_start = self.chunk_size * chunk_num
                chunk_data = file_data[chunk_start:(chunk_start + self.chunk_size)]
                cache_key = "{} {} {}".format(url, self.chunk_size, chunk_num)
                print(f"  getSize: debug 760: cache add " + cache_key)
                self.lru_cache[cache_key] = chunk_data
                self.disk_cache[cache_key] = chunk_data
                curr_start += self.chunk_size
            """

            return size

        except Exception as ex:
            self.logger.exception(ex)
            raise
