import random
import time
import dateutil.parser
from hashlib import sha1
from hexdump_canonical import hexdump_canonical

import sys # TODO raise Exception

# https://github.com/dulwich/dulwich/blob/master/dulwich/objects.py
# https://www.samba.org/~jelmer/dulwich/docs/tutorial/file-format.html
# http://www-cs-students.stanford.edu/~blynn/gitmagic/ch08.html

def verify_blob(self, sha_expected, size_expected, body, blob_path):

  size_actual = len(body)
  if size_expected != size_actual:
    print("  bad blob: size mismatch")
    print(f"    expected {size_expected}")
    print(f"    actual   {size_actual}")

    # write actual file to /tmp
    tmpfile_path = '/tmp/githubfs-bad-blob.' + blob_path.replace('/', '_') + '.size-' + str(size_actual)
    tmpfile = open(tmpfile_path, 'wb')
    tmpfile.write(body)
    tmpfile.close()
    print("  bad blob: written to " + tmpfile_path)
    return False

  actual_sha = hash_blob_body(body)
  verify_passed = test_sha(sha_expected, actual_sha)
  if verify_passed:
    print(f"  ok_blob {sha_expected} {blob_path}") # debug
    return

  # TODO write to file (especially for large files)
  if (len(body) < 128):
    print("actual blob body:")
    hexdump_canonical(body)
  else:
    print(f"actual blob body: large body (size {len(body)}). first 128 bytes:")
    hexdump_canonical(body[:128])

  throw_if_bad_sha(verify_passed, sha_expected, "blob")



def verify_tree(self, sha_expected, data, tree_path):

  if data['truncated'] == True:
    print("FIXME implement truncated tree data")
    raise NotImplementedError("FIXME implement truncated tree data")
    #sys.exit(1)

  def get_mode(item):
    # remove left zero padding
    m = item['mode']
    while m[0] == '0':
      m = m[1:]
    return m.encode("ascii")

  tree_body = b""
  for tree_item in data['tree']:
    #tree_body += tree_item['mode'].encode("ascii") + tree_item['path'].encode("utf8") + b"\0" + bytes.fromhex(tree_item['sha']) + b"\n"
    tree_body += get_mode(tree_item)
    tree_body += b" "
    tree_body += tree_item['path'].encode("utf8")
    tree_body += b"\0"
    tree_body += bytes.fromhex(tree_item['sha'])

  #print("#### tree_body:\n%s\n:tree_body ####" % tree_body.decode('utf8'))

  actual_sha = hash_tree_body(tree_body)
  verify_passed = test_sha(sha_expected, actual_sha)
  if verify_passed:
    print("  ok_tree") # debug
    #print("  good tree %s %s" % (sha_expected, tree_path))
    return

  print("actual tree tree_body:")
  hexdump_canonical(tree_body)

  throw_if_bad_sha(verify_passed, sha_expected, "tree")



def verify_commit(self, sha_expected, data):

  if data['verification']['payload'] != None:
    #print("  vf_comm use data.verification.payload")
    # simple case: we have all metadata (lossless)
    body_str = data['verification']['payload']
    committer_end = body_str.find("\n\n") + 1
    body_str = body_str[:committer_end] + "gpgsig " + data['verification']['signature'].replace("\n", "\n ") + "\n" + body_str[committer_end:]
    body = body_str.encode('utf8')
    actual_sha = hash_commit_body(body)
    #test_sha_or_throw(sha_expected, actual_sha, "commit")
    verify_passed = test_sha(sha_expected, actual_sha)
    if verify_passed == False:
      print("data:"); print(repr(data))
      print("#### actual commit body:")
      #hexdump_canonical(body)
      print(body.decode('utf8'))
      print("#### :actual commit body")
      print("get expected commit body:")
      #print(f"git cat-file commit {sha_expected} -C path/to/repo | hexdump -C")
      print(f"git cat-file commit {sha_expected} -C path/to/repo")
      #hexdump_canonical(body)
    throw_if_bad_sha(verify_passed, sha_expected, "commit")

    # verify payload-tree vs data-tree. data['tree']['sha'] could be wrong
    expected_tree = data['verification']['payload'].split("\n")[0].split(" ")[1]
    actual_tree = data['tree']['sha']
    test_sha_or_throw(expected_tree, actual_tree, "commit.tree")

    print("  ok_comm") # debug
    return

  # complex ...
  # commit data from github is LOSSY!
  # timezone is missing -> we have 24 different guesses ...
  # or worse: if author != commiter, we have 24*24 = 576 guesses. WTF github? >:(
  # TODO handle the "even worse" case

  author_id = get_user_id(data['author'])
  committer_id = get_user_id(data['committer'])

  timezone_list = None
  if author_id in self.timezone_cache and committer_id in self.timezone_cache:
    # cache hit :)
    timezone = self.timezone_cache[author_id]
    timezone_list = [timezone] # simple case: timezone: author == committer
    print("  cache hit: re-use timezone %s for %s" % (timezone_str(timezone), author_id))
  else:
    # simple case: timezone: author == committer
    # TODO handle complex case: timezone: author != committer
    timezone_list = list(range(-12, 13)) # -12 to 12
    random.shuffle(timezone_list) # random is fastest solution for unknown input

  body = b""

  verify_passed = False
  for timezone in timezone_list:
    #print("verify commit: test timezone " + timezone_str(timezone))

    body = b""
    body += b"tree "
    body += data['tree']['sha'].encode("ascii")
    body += b"\n"
    for parent_item in data['parents']:
      body += b"parent " + parent_item['sha'].encode("ascii") + b"\n"
    body += b"author "
    body += get_user_bytes(data['author'], timezone)
    body += b"\n"
    body += b"committer "
    body += get_user_bytes(data['committer'], timezone)
    body += b"\n"
    # TODO maybe add gpgsig: PGP SIGNATURE indented by one space
    # github api: data['verification']['signature']
    body += b"\n"
    body += data['message'].encode("utf8")
    body += b"\n"

    #print("#### body:\n%s\n:body ####" % body.decode('utf8'))

    actual_sha = hash_commit_body(body)
    verify_passed = test_sha(sha_expected, actual_sha)
    if verify_passed:
      # found timezone. cache timezone by author + committer
      self.timezone_cache[author_id] = timezone
      self.timezone_cache[committer_id] = timezone
      print("  ok_comm") # debug
      #print("  good commit %s. guessed timezone %s" % (sha_expected, timezone_str(timezone)))
      break # stop guessing

  if verify_passed == False:
    print("actual commit body:")
    #hexdump_canonical(body)
    print(body)
    print("get expected commit body:")
    #print(f"git cat-file commit {sha_expected} -C path/to/repo | hexdump -C")
    print(f"git cat-file commit {sha_expected} -C path/to/repo")

  throw_if_bad_sha(verify_passed, sha_expected, "commit")



def get_user_bytes(user, timezone):
  return (get_user_id(user) + " " + time_str(user['date'], timezone)).encode("utf8") # TODO encoding? UTF-8?

def signum(n):
  return "-" if n < 0 else "+"
  # TODO verify. is this git's signum function?

def timezone_str(timezone):
  return "%s%02i00" % (signum(timezone), abs(timezone))

def time_str(iso_time, timezone):
  return "%i %s" % (time.mktime(dateutil.parser.parse(iso_time).timetuple()) + timezone * 3600, timezone_str(timezone))

def get_user_id(user):
  return user['name'] + " <" + user['email'] + ">"

def hash_commit_body(body):
  b = b""
  b += b"commit "
  b += str(len(body)).encode("ascii")
  b += b"\0"
  b += body
  return sha1(b"commit " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()

def hash_tree_body(body):
  return sha1(b"tree " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()

def hash_blob_body(body):
  return sha1(b"blob " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()

def test_sha(expected, actual):
  return expected == actual
  # debug
  if expected == actual:
    print("  commit ok: " + actual)
    return True
  else:
    print("  bad commit")
    print(f"    expected {expected}")
    print(f"    actual   {actual}")
    return False

def throw_if_bad_sha(verify_passed, expected, type):
  if verify_passed == False:
    print(f"ERROR bad {type}. could not verify sha " + expected)
    #sys.exit(1) # fatal error
    # TODO raise Exception
    raise Exception(f"ERROR bad {type}. could not verify sha " + expected)

def test_sha_or_throw(expected, actual, type):
  if expected != actual:
    print(f"ERROR bad {type}. could not verify sha " + expected)
    print(f"  expected {expected}")
    print(f"  actual   {actual}")
    raise Exception(f"ERROR bad {type}. could not verify sha {expected}\n  expected {expected}\n  actual   {actual}")
    #sys.exit(1) # fatal error
    # TODO raise Exception
