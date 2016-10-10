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
    terms = scrapy.Field()


class ArchiveSpider(CrawlSpider):
    name = 'archiver'
    rules = (Rule(LinkExtractor(allow=()), callback='parse_page', follow=True),)
    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "FEED_FORMAT": "json",
        "FEED_URI" : "taxonomy.json"
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
        taxonomy_terms = self.get_taxonomy_terms(response)
        url = Url(url=response.url, terms=taxonomy_terms)
        yield url

    def get_taxonomy_terms(response):
        terms = response.xpath("//a[@typeof='skos:Concept']/text()").extract()
        return terms
