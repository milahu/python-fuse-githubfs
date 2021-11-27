import json

def pretty_json(_object):
    return json.dumps(_object, indent=2, sort_keys=False)

# thread-safe print
# otherwise we cannot print from callback functions
# https://stackoverflow.com/questions/3029816/how-do-i-get-a-thread-safe-print-in-python-2-6
def safe_print(*args, sep=" ", end="", **kwargs):
    joined_string = sep.join([ str(arg) for arg in args ])
    print(joined_string  + "\n", sep=sep, end=end, **kwargs)

# http://thepythoncorner.com/dev/writing-a-fuse-filesystem-in-python/
def dict_of_lstat(lstat_res):
    lstat_keys = ['st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid', 'st_blocks']
    return dict((k, getattr(lstat_res, k)) for k in lstat_keys)

def dict_of_statvfs(statvfs_res):
    statvfs_keys = ['f_bavail', 'f_bfree', 'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag', 'f_frsize', 'f_namemax']
    return dict((k, getattr(statvfs_res, k)) for k in statvfs_keys)
