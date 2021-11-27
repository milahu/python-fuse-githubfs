import os.path
from errno import EIO, ENOENT
from stat import S_IFDIR, S_IFREG
import time
from fuse import FuseOSError, LoggingMixIn, Operations


if True:
    def readdir(self, path, fh):
        #print("+ readdir", path)
        # overlay (hybrid mode)
        full_path = self._full_path(path)
        if not os.path.isdir(full_path):
            return # TODO raise error?
        dirents = ['.', '..']
        dirents.extend(os.listdir(full_path))
        # add new patched files
        for p in self.patched_paths:
            d = os.path.dirname(p)
            if d == path:
                b = os.path.basename(p)
                if not b in dirents:
                    dirents.append(b)
        for r in dirents:
            yield r
        return

        #full_path = self.lower_dir + path
        repo_list = ['.', '..']
        path_ele = path.split('/')
        if path.startswith('.'):
            pass

        if not path in self.tree_data:
            path_parts = path.split("/")
            # find parent in cache: bottom-up
            parent_path = None
            parent_depth = None
            for path_len in range((len(path_parts) - 1), 1, -1):
                maybe_parent_path = "/".join(path_parts[0:path_len])
                print("debug 1220")
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
            for path_len in range((parent_depth + 1), (len(path_parts) + 1)):
                parent_path = "/".join(path_parts[0:path_len])

                if not parent_path in self.tree_sha:
                    raise FuseOSError(ENOENT) # no such file
                    # TODO also in getattr

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
                tree = self.tree_data[parent_path]['tree']
                for tree_item in tree:
                    item_path = path_prefix + tree_item['path']
                    if tree_item['type'] == 'tree':
                        self.tree_sha[item_path] = tree_item['sha']
                    elif tree_item['type'] == 'blob':
                        self.blob_sha[item_path] = tree_item['sha']


        #self.tree_sha = {}
        #self.tree_sha['/'] = data['tree']['sha']
        #self.tree_data = {}
        #self.blob_sha = {}



        path_prefix = path + '/'
        if path == '/':
            path_prefix = '/'

        #print("  tree_data keys: " + " ".join(self.tree_data.keys())) # debug

        tree = self.tree_data[path]['tree']

        res = ['.', '..']
        for tree_item in tree:
            res.append(tree_item['path'])

            item_path = path_prefix + tree_item['path']

            #file_time = time.time()

            if 'size' in tree_item:
                # file
                #file_mode = S_IFREG | 0o444 # regular file, read only
                file_mode = int(tree_item['mode'], 8)
                if filemode_mask:
                    print(f"+ getattr {path}: mask mode from {oct(file_mode)} to {oct(file_mode & filemode_mask)}")
                    file_mode = file_mode & filemode_mask
                self.lru_attrs[item_path] = dict(
                    st_mode=(file_mode),
                    st_nlink=1,
                    st_size=tree_item['size'],
                    #st_ctime=file_time,
                    #st_mtime=file_time,
                    #st_atime=file_time,
                )
            else:
                # dir
                self.lru_attrs[item_path] = dict(
                    st_mode=(S_IFDIR | 0o555), # directory, read only
                    st_nlink=2
                )

        return res

        #print("data = " + repr(self.tree_data['/']))
        #print("data.tree[0].path = " + repr(self.tree_data['/']['tree'][0]['path']))

        """
        elif path == '/':
            return ['.', '..', 'repos']
        elif path == '/repos':
            return repo_list + self.repo_list
        elif path_ele[-1] in self.repo_list:
            repo_name = path_ele[-1]
            for item in self.user.get_user().get_repos():
                if item.name == repo_name:
                    files = item.get_dir_contents('/')
                    break
            for item in files:
                repo_list.append(item.name)
            return repo_list
        """
