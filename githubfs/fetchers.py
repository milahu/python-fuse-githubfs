

import os
FALSY = {0, "0", False, "false", "False", "FALSE", "off", "OFF"}

import boto3 # amazon aws
import traceback
from errno import EIO, ENOENT
from ftplib import FTP
import time
from urllib.parse import urlparse
import numpy
from fuse import FuseOSError, LoggingMixIn, Operations
import slugid

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    wait_random,
)


class FtpFetcher:
    def server_path(self, url):
        o = urlparse(url)

        return (o.netloc, o.path)

    def login(self, server):
        ftp = FTP(server)
        ftp.login()

        try:
            # do a retrbinary on a non-existent file
            # to set the transfer mode to binary
            # use a dummy callback too
            ftp.retrbinary(slugid.nice(), lambda x: x + 1)
        except:
            pass

        return ftp

    def get_size(self, url):
        (server, path) = self.server_path(url)

        ftp = self.login(server)
        size = ftp.size(path)
        ftp.close()
        return size, None

    def get_data(self, url, start, end):
        import time

        (server, path) = self.server_path(url)
        ftp = self.login(server)
        conn = ftp.transfercmd("RETR {}".format(path), rest=start)

        amt = end - start
        chunk_size = 1 << 15
        data = []
        while len(data) < amt:
            chunk = conn.recv(chunk_size)
            if chunk:
                data += chunk
            else:
                break
        if len(data) < amt:
            data += [0] * (amt - len(data))
        else:
            data = data[:amt]

        ftp.close()
        t2 = time.time()
        return numpy.array(data, dtype=numpy.uint8)


def is_403(value):
    """Return True if the error is a 403 exception"""
    return value is not None


class HttpFetcher:
    SSL_VERIFY = os.environ.get("SSL_VERIFY", True) not in FALSY

    def __init__(self, logger):
        self.logger = logger
        if not self.SSL_VERIFY:
            logger.warning(
                "You have set ssl certificates to not be verified. "
                "This may leave you vulnerable. "
                "http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification"
            )

    def get_size(self, url):
        print("HttpFetcher.get_size: url = " + url)
        # TODO avoid try/except, use "if key in dict"
        try:
            # TODO rename head to response
            # TODO handle response.status_code
            head = self.requests.head(url, allow_redirects=True, verify=self.SSL_VERIFY)
            return int(head.headers["Content-Length"]), None
        except KeyError:
            # bad news: we must download the file to know its size
            # TODO rename head to response
            head = self.requests.get(
                url,
                allow_redirects=True,
                verify=self.SSL_VERIFY,
                headers={"Range": "bytes=0-1"},
            )
            if head.status_code != 200:
                # not found
                print("  TODO verify: get.status_code = " + str(head.status_code))
                self.logger.error(traceback.format_exc())
                raise FuseOSError(ENOENT)

            self.logger.info("got status %s", head.status_code)
            head.raise_for_status() # TODO ?
            safe_print("TRACE dtype=numpy. 480")
            file_data = numpy.frombuffer(head.content, dtype=numpy.uint8)

            file_size = file_data.size

            # TODO better handle large files
            # https://docs.python-requests.org/en/master/user/quickstart/#raw-response-content

            print("  file_size = " + str(file_size))

            return file_size, file_data

            # TODO ?
            #self.logger.error(traceback.format_exc())
            #raise FuseOSError(ENOENT)

    @retry(wait=wait_fixed(1) + wait_random(0, 2), stop=stop_after_attempt(2))
    def get_data(self, url, start, end):
        #print("HttpFetcher.get_data: url = " + url)
        headers = {"Range": "bytes={}-{}".format(start, end), "Accept-Encoding": ""}
        # NOTE github DOES support range requests on the raw endpoint!
        # still, we need the whole file to verify checksum
        #self.logger.info("getting %s %s %s", url, start, end)
        r = self.requests.get(url, headers=headers)
        #self.logger.info("got %s", r.status_code)



        r.raise_for_status()
        #safe_print("TRACE dtype=numpy. 500") # yepp! after dropping the disk_cache, this is called
        chunk_data = numpy.frombuffer(r.content, dtype=numpy.uint8)
        return chunk_data


class S3Fetcher:
    SSL_VERIFY = os.environ.get("SSL_VERIFY", True) not in FALSY

    def __init__(self, aws_profile, logger):
        self.logger = logger
        self.logger.info("Creating S3Fetcher with aws_profile=%s", aws_profile)
        self.session = boto3.Session(profile_name=aws_profile)
        self.client = self.session.client("s3")
        pass

    def parse_bucket_key(self, url):
        url_parts = urlparse(url, allow_fragments=False)
        bucket = url_parts.netloc
        key = url_parts.path.strip("/")

        return bucket, key

    def get_size(self, url):
        bucket, key = self.parse_bucket_key(url)

        response = self.client.head_object(Bucket=bucket, Key=key)
        size = response["ContentLength"]
        return size, None

    @retry(wait=wait_exponential(multiplier=1, min=4, max=10))
    def get_data(self, url, start, end):
        bucket, key = self.parse_bucket_key(url)
        obj = boto3.resource("s3").Object(bucket, key)
        stream = self.client.get_object(
            Bucket=bucket, Key=key, Range="bytes={}-{}".format(start, end)
        )["Body"]
        contents = stream.read()
        safe_print("TRACE dtype=numpy. 540")
        chunk_data = numpy.frombuffer(contents, dtype=numpy.uint8)
        return chunk_data

