"""
Scrape a given site's source for buckets.
"""
import requests
import re
    
def getBucketsFromText(text):
    regexes = [r'([\w\d_\.-]+)\.s3[\w\d-]*\.amazonaws\.com',
               r'([\w\d_\.-]+)\.storage\.googleapis\.com',
               r'([\w\d_\.-]+)\.[\w\d\.-]*\.cdn\.digitaloceanspaces\.com',
               r'([\w\d_-]+)\.oss[\w\d-]*\.aliyuncs\.com',
               r'^[^.]*s3[\w\d-]*\.amazonaws\.com\/([\w\d_.-]+)',
               r'^[^.]*s3[\w\d\.-]*\.wasabisys\.com\/([\w\d_.-]+)',
               r'^[^.]*storage\.googleapis\.com\/([\w\d_.-]+)',
               r'^[^.]*oss[\w\d_-]*\.aliyuncs\.com\/([\w\d_.-]+)']
    for regex in regexes:
        found = re.findall(regex, text.lower())
        if len(found) > 0:
            return found
    return set()

