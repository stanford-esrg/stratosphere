import requests
import json
from .. import getBucketsFromText
import os

API_ENDPOINTS = [("https://api.dnsdb.info/lookup/rrset/name/", "rrname"), ("https://api.dnsdb.info/lookup/rdata/name/", "rdata")]
regions = ["us-east-2", "us-east-1", "us-west-1", "us-west-2", "af-south-1", "ap-east-1", "ap-south-1", "ap-northeast-3", "ap-northeast-2", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ca-central-1", "cn-north-1", "cn-northwest-1", "eu-central-1", "eu-west-1", "eu-west-2", "eu-south-1", "eu-west-3", "eu-north-1", "me-south-1", "sa-east-1", "us-gov-east-1", "us-gov-west-1"]

API_KEY = os.getenv("FARSIGHT_API_KEY")
OUTPUT_NAME = "./data/extraction/farsight/"

api_limit = 1000000

def lookupFile(file, type):
    files = []
    with open(file, 'r') as f:
        for line in f:
            text = line.strip()
            if "{region}" in text:
                all_regions = []
                for region in regions:
                    all_regions.append(text.replace("{region}", region))
                files.append(all_regions)
            else:
                files.append([text])
    for endpoint_list in files:
        lookup(endpoint_list, type + "/")

def lookup(endpoints, directory=""):
    all_domains = set()
    for domain in endpoints:
        for endpoint_pair in API_ENDPOINTS:
            (endpoint, field_name) = endpoint_pair
            offset = 0
            while True:
                url = "{}*.{}?limit={}&offset={}".format(endpoint, domain, api_limit, offset)
                print("Fetching " + url)
                headers = {'Accept': 'application/json', 'X-API-Key': API_KEY}
                resp = requests.get(url, headers=headers)
                if resp.status_code != 200:
                    break
                split = resp.text.split("\n")
                for line in split:
                    if line.strip() == "":
                        continue
                    resp_json = json.loads(line)
                    if field_name in resp_json:
                        dns_val = resp_json[field_name]
                        if dns_val[-1] == ".":
                            dns_val = dns_val[:-1]
                        all_domains.add(dns_val)
                print(len(split))
                if len(split) < api_limit or offset >= 4000000:
                    break
                offset += api_limit
    out = './data/extraction/farsight/' + directory + domain + ".txt"
    with open(out, 'w+') as f:
        f.write("\n".join(all_domains))
    print("Wrote buckets to " + out)

