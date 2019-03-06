#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2016 seamus tuohy, <code@seamustuohy.com>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the included LICENSE file for details.

# Spider a website and archive all the links on Internet Archive.

import scrapy
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor

# https://github.com/seamustuohy/DocOps
from docops.review import Archive, MissingArchiveError
from docops.review import RobotAccessControlException, UnknownArchiveException
from urllib.error import HTTPError
from urllib.parse import urlparse
from os import environ, path
from datetime import datetime
import requests
import csv


import logging
logging.basicConfig(level=logging.ERROR)
log = logging.getLogger(__name__)


class Url(scrapy.Item):
    url = scrapy.Field()
    archive = scrapy.Field()


class ArchiveSpider(CrawlSpider):
    name = 'archiver'
    rules = (Rule(
        LinkExtractor(allow=(), deny=(
            ['.*index.php.*','.*wiki/Special.*', ".*api.php.*"]
        )),
        callback='parse_page',
        follow=True),
    )
    # allow=('.*site.com/category_pattern.*',)), callback='your_callback', follow=False
    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1
    }

    def __init__(self, *args, **kwargs):
        super(ArchiveSpider, self).__init__(*args, **kwargs)
        base_url = "https://learn.equalit.ie"
        parsed_url = urlparse(base_url)
        if parsed_url.scheme == '':
            url_def = "[http[s]]//[host].[domain].[tld]"
            raise ValueError('You must use a full url. e.g. {0}'.format(url_def))
        self.start_urls = [base_url]
        self.allowed_domains = [parsed_url.netloc]

    def parse_page(self, response):
        resp_urls = [response.url]
        # resp_path = path.split(urlparse(response.url).path)[-1]
        resp_path = urlparse(response.url).path.strip("/wiki/")
        raw_url = 'https://learn.equalit.ie/mw/index.php?title={0}&action=raw'.format(resp_path)
        raw_found = self.download_raw(resp_path, raw_url)
        if raw_found is True:
            resp_urls.append(raw_url)
        for resp in resp_urls:
            archive = self.archive_link(resp)
            url = Url(url=resp, archive=archive)
            yield url


    def download_raw(self, title, url):
        r = requests.get(url)
        formatted_title = title.replace("/","_")
        if len(formatted_title) > 100:
            formatted_title = formatted_title[0:100]
        path = '/etc/spider/data/learn_equalit.ie/{0}'.format(formatted_title)
        with open(path, 'w+') as fp:
            fp.write(r.text)
        # Log successful collection
        if r.ok is True:
            log.debug("Raw found for {0}".format(formatted_title))
            self.write_captured(title, url, path, True)
            return True
        else:
            log.debug("Raw NOT found for {0}".format(formatted_title))
            self.write_captured(title, url, path, False)
            return False

    def write_captured(self, title, url, path, success):
        with open('/etc/spider/data/learn_equalit.ie/CAPTURED_DATA.csv', 'a+') as fp:
            csv_writer = csv.writer(fp)
            csv_writer.writerow([str(datetime.utcnow()),
                                 title,
                                 url,
                                 path,
                                 success])
            
    def archive_link(self, link):
        try:
            log.debug("Archiving {0} link".format(link))
            link_archive = Archive(link)
            log.debug("submitting link {0}".format(link))
            link_archive.submit()
            log.debug("requesting archived link {0}".format(link))
            archive = link_archive.request()
            return archive
        except (HTTPError,
                RobotAccessControlException,
                MissingArchiveError,
                UnknownArchiveException):
            return None

    def ignore_index_pages(self, response):
        log.debug("Ignoring {0}".format(response.url))
