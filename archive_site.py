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
from os import environ

import logging
logging.basicConfig(level=logging.ERROR)
log = logging.getLogger(__name__)


class Url(scrapy.Item):
    url = scrapy.Field()
    archive = scrapy.Field()


class ArchiveSpider(CrawlSpider):
    name = 'archiver'
    rules = (Rule(LinkExtractor(allow=()), callback='parse_page', follow=True),)
    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1
    }

    def __init__(self, *args, **kwargs):
        super(ArchiveSpider, self).__init__(*args, **kwargs)
        base_url = environ['URL']
        parsed_url = urlparse(base_url)
        if parsed_url.scheme == '':
            url_def = "[http[s]]//[host].[domain].[tld]"
            raise ValueError('You must use a full url. e.g. {0}'.format(url_def))
        self.start_urls = [base_url]
        self.allowed_domains = [parsed_url.netloc]

    def parse_page(self, response):
        archive = self.archive_link(response.url)
        url = Url(url=response.url, archive=archive)
        yield url

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
