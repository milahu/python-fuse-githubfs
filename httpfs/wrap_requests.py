import time
from datetime import datetime

def wrap_requests(requests, github_token):

  # TODO requests.head

  real_requests_get = requests.get
  def wrap_requests_get(*args, **kwargs):
      if not 'headers' in kwargs:
          kwargs['headers'] = {}
      kwargs['headers']['Authorization'] = 'token ' + github_token
      response = real_requests_get(*args, **kwargs)
      if 'x-ratelimit-used' in response.headers._store:
          remain = int(response.headers['X-RateLimit-Remaining'])
          #if remain < 20:
          if True:
              print("  ratelimit status: used %s of %s. next reset in %s minutes" % (
                  response.headers['X-RateLimit-Used'],
                  response.headers['X-RateLimit-Limit'],
                  datetime.utcfromtimestamp(int(response.headers['X-RateLimit-Reset']) - time.time()).strftime('%M:%S')
              ))
      url = args[0]
      if url.startswith("https://api.github.com/"):
          data = response.json()
          if 'truncated' in data and data['truncated'] == True:
              print(f"  FIXME handle truncated data from url {args[0]}")
              print(pretty_json(data))
              print(f"  FIXME handle truncated data from url {args[0]}")
      return response
  requests.get = wrap_requests_get

  real_requests_post = requests.post
  def wrap_requests_post(*args, **kwargs):
      if not 'headers' in kwargs:
          kwargs['headers'] = {}
      kwargs['headers']['Authorization'] = 'token ' + github_token
      response = real_requests_post(*args, **kwargs)
      if 'x-ratelimit-used' in response.headers._store:
          remain = int(response.headers['X-RateLimit-Remaining'])
          if remain < 20:
              print("  ratelimit status: used %s of %s. next reset in %s minutes" % (
                  response.headers['X-RateLimit-Used'],
                  response.headers['X-RateLimit-Limit'],
                  datetime.utcfromtimestamp(int(response.headers['X-RateLimit-Reset']) - time.time()).strftime('%M:%S')
              ))
      return response
  requests.post = wrap_requests_post
