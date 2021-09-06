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

import re
import time
import sqlite3
from datetime import datetime, timedelta, timezone
from collections import namedtuple
from urllib.parse import urlparse

import requests

from savepagenow import BlockedByRobots
from savepagenow.exceptions import WaybackRuntimeError
from savepagenow import capture as sp_capture

import wayback

import scrapy
from scrapy import crawler
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor

# from scrapy.spidermiddlewares.offsite import OffsiteMiddleware

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
    rules = (
        Rule(LinkExtractor(allow=()),
             callback='parse_page',
             follow=True),
    )
    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DAYS_BEFORE_RENEW_ARCHIVE":365,
        "DATABASE_PATH":"/etc/spider/archive.db",
        "COLLECT_OFFSITE": True,
        #"LOG_LEVEL": logging.INFO,
        "DOWNLOAD_ALL_PDFS": False, # TODO Not implemented
        "LOG_LEVEL": logging.DEBUG
    }

    def __init__(self, *args, **kwargs):
        super(ArchiveSpider, self).__init__(*args, **kwargs)
        self.conn = None
        self.db_initialized = None
        self.archive_filter = {'link_deny':[]}

        base_url = environ['URL']
        parsed_url = urlparse(base_url)

        if parsed_url.scheme == '':
            url_def = "[http[s]]//[host].[domain].[tld]"
            raise ValueError('You must use a full url. e.g. {0}'.format(url_def))
        self.start_urls = [base_url]
        self.allowed_domains = [parsed_url.netloc]

    def populate_custom_archive_rules(self, base_url):
        url = urlparse(base_url)
        netloc = url.netloc

        if len(netloc) > 3:
            c = self.conn.cursor()
            res = c.execute('SELECT rule_type, rule FROM scrape_rules WHERE netloc = ?', (netloc,)).fetchall()
            for row in res:
                self.make_archive_rule(rule_type=row[0],
                                       rule=row[1])

    def make_archive_rule(self, rule_type, rule):
        if rule_type == "link_deny":
            self.archive_filter['link_deny'].append(re.compile(rule))

    def init_database(self):
        if self.db_initialized is True:
            return
        dbpath = self.settings.get("DATABASE_PATH")
        self.conn = sqlite3.connect(dbpath)
        c = self.conn.cursor()
        c.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='archives' ''')
        if c.fetchone()[0] != 1:
            self._create_database(name="archives")
        c.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='found_external_links' ''')
        if c.fetchone()[0] != 1:
            self._create_database(name="external_links")
        c.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='blocked_from_archiving' ''')
        if c.fetchone()[0] != 1:
            self._create_database(name="blocked")
        c.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='scrape_rules' ''')
        if c.fetchone()[0] != 1:
            self._create_database(name="scrape_rules")
        self.db_initialized = True

    def spider_closed(self, spider):
        # Close database when spider is done.
        self.conn.close()

    def save_offsite_links(self, response):
        if self.settings.getbool("COLLECT_OFFSITE", False) is not True:
            return
        offsite_links = []
        for offsite in LinkExtractor(
                allow=(),
                deny = self.allowed_domains
        ).extract_links(response):
            offsite_links.append(offsite.url)
        for link in offsite_links:
            self.write_external_link_to_db(link,
                                           response.url,
                                           datetime.now(timezone.utc))
        self.conn.commit()

    def parse_page(self, response):
        # create database connection if missing
        # Do this here because settings are not available in init
        if self.conn is None:
            # Setup Database
            self.init_database()
            # Populate any site specific rules
            self.populate_custom_archive_rules(self.start_urls[0])
        # Don't archive any pages matching link_deny rules
        archive_page = True
        for deny_rule in self.archive_filter.get('link_deny', []):
            if deny_rule.match(response.url):
                self.logger.debug("Rejecting page {0} for archiving due to archive rules".format(response.url))
                archive_page = False
        if archive_page is True:
            self.save_offsite_links(response)
            self.archive_link(response.url)
        yield None


    def _create_database(self, name="all"):
        # Archive Site: self.sources.submission
        # Date of Archive:
        # Archive URL:
        if name == "all" or name == "archives":
            self.conn.execute(
                '''
            CREATE TABLE archives (
            URL text PRIMARY KEY NOT NULL UNIQUE,
            Archive text NOT NULL,
            LastSubmitDate timestamp,
            ArchiveURL text)
            '''
            )
        if name == "all" or name == "external_links":
            self.conn.execute(
                '''
                CREATE TABLE found_external_links (
                ID integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
                ExternalURL text,
                FoundWhere text,
                FoundDate timestamp,
                UNIQUE(ExternalURL,FoundWhere)
                )
                '''
            )
        if name == "all" or name == "blocked":
            self.conn.execute(
                '''
                CREATE TABLE blocked_from_archiving (
                URL text PRIMARY KEY NOT NULL UNIQUE,
                Why text,
                LastCheckDate timestamp
                )
                '''
            )
        if name == "all" or name == "scrape_rules":
            self.conn.execute(
                '''
                CREATE TABLE scrape_rules (
                ID integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
                rule_type text,
                rule text,
                netloc text
                )
                '''
            )
        self.conn.commit()

    def db_contains_recent_link_archive(self, link):
        c = self.conn.cursor()
        try:
            c.execute('SELECT LastSubmitDate FROM archives WHERE URL = ?', (link,))
            db_date = c.fetchone()[0]
            db_date = datetime.fromisoformat(db_date)
            # log.info(db_date)
            renewal_date_period_start_date = datetime.now(timezone.utc) - timedelta(self.settings.get("DAYS_BEFORE_RENEW_ARCHIVE"))
            # If no archive has been captured in the last renewal period we should capture one now.
            if renewal_date_period_start_date < db_date:
                needs_renew = False
        except TypeError:
            needs_renew = True
        if needs_renew is False:
            return True
        return False

    def archive_link(self, link):
        if self.db_contains_recent_link_archive(link):
            self.logger.info("Link not Archived (DB shows recently archived):  {0}".format(link))
            return None
        days_before_renew = self.settings.get("DAYS_BEFORE_RENEW_ARCHIVE")
        link_archive = Archiver(link, days_before_renew_archive=days_before_renew)
        link_archive.find()
        if link_archive.needs_renewal():
            try:
                self.logger.info("Submitting link to archive: {0}".format(link))
                archive_url = link_archive.archive()
                self.write_archive_to_db(link=link,
                                         archive_name="Wayback Machine",
                                         last_submit_datetime=datetime.now(timezone.utc),
                                         archive_url=archive_url)
            except BlockedByRobots:
                self.logger.warning("Site does not allow archiving by wayback {0}".format(link))
                self.write_blocked_to_db(link=link,
                                         reason="robots.txt",
                                         time_blocked=datetime.now(timezone.utc))
            except WaybackRuntimeError:
                self.logger.warning("Error occured archiving {0}".format(link))
                self.write_blocked_to_db(link=link,
                                         reason="Unknown Archiving Error",
                                         time_blocked=datetime.now(timezone.utc))
                return None
        else:
            _last_archive_date = link_archive.latest_memento.timestamp
            _last_archive_uri = link_archive.latest_memento.raw_url
            _archive_type = "Wayback Machine"
            self.write_archive_to_db(link=link,
                                     archive_name=_archive_type,
                                     last_submit_datetime=_last_archive_date,
                                     archive_url=_last_archive_uri)
            self.logger.info("Link not Archived (Archived recently on {0}):  {1}".format(_last_archive_date, link))

    def write_archive_to_db(self, link, archive_name, last_submit_datetime, archive_url):
        self.conn.execute('INSERT OR REPLACE INTO archives(URL, Archive, LastSubmitDate, ArchiveURL) VALUES (?,?,?,?)',
                          (link,
                           archive_name,
                           last_submit_datetime,
                           archive_url))
        self.conn.commit()

    def write_blocked_to_db(self, link, reason, time_blocked):
        self.conn.execute('INSERT OR REPLACE INTO blocked_from_archiving(URL, Why, LastCheckDate) VALUES (?,?,?)',
                          (link,
                           reason,
                           time_blocked))
        self.conn.commit()

    def write_external_link_to_db(self, external_url, found_where, time_blocked):
        self.conn.execute('INSERT OR REPLACE INTO blocked_from_archiving(URL, Why, LastCheckDate) VALUES (?,?,?)',
                          (external_url,
                           found_where,
                           time_blocked))
        self.conn.commit()



class Archiver(object):
    """

    :returns:  object

    http://timetravel.mementoweb.org/guide/api/
    http://www.mementoweb.org/guide/quick-intro/
    http://examinemint.com/about-the-time-travel-service/
    """

    def __init__(self, target_url,
                 days_before_renew_archive=365):
        # /list/20210624
        """
        :param target_url: The url that will be
        :type name: str.
        """
        self.raw = None
        self.latest_memento = None
        self.last_archive_date = None
        self.days_before_renewal = days_before_renew_archive
        self.submission = None
        self.source_target = target_url
        self.wb_client = wayback.WaybackClient()
        self.memento_not_found = None

    def archive(self, custom_UA=None):
        if custom_UA is not None:
            # Change sp_capture user_agent string to not show default
            # The default is "savepagenow (https://github.com/pastpages/savepagenow)"
            archive_url = sp_capture(self.source_target,
                                     user_agent=custom_UA,
                                     accept_cache=True)
        else:
            archive_url = sp_capture(self.source_target,
                                     accept_cache=True)
        return archive_url

    def find(self):
        query_day =  datetime.today() - timedelta(self.days_before_renewal)
        log.debug("Searching for URL in wayback: {0}".format(self.source_target))
        results = self.wb_client.search(self.source_target,
                                        from_date=query_day,
                                        fastLatest=True)
        try:
            latest = next(results)
            log.debug("URL found in wayback: {0}".format(self.source_target))
        except StopIteration:
            self.memento_not_found = True
            log.debug("URL not found in wayback: {0}".format(self.source_target))
            return None
        for res in results:
            if latest.timestamp < res.timestamp:
                latest = res
        self.latest_memento = latest

    def needs_renewal(self):
        """Checks if an archive of a url has occured in the required renewel period

        For example: if the self.days_before_renewal is 365 days then we check if an archive has been taken
        in the last 365 days. If no archive can be found in the last 365 days then we take an archive.
        """
        if self.memento_not_found is True:
            return True
        else:
            self.find()

        if self.latest_memento is not None:
           self.last_archive_date = self.latest_memento.timestamp

        last_acceptable_date = datetime.now(timezone.utc) - timedelta(self.days_before_renewal)
        if last_acceptable_date > self.last_archive_date:
            return True
        else:
            log.debug("Archived copy of URL is older than last acceptable date: {0}".format(self.source_target))
        return False
