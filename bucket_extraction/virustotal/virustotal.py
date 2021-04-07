import requests
import subprocess
import grequests
from .. import getBucketsFromText
import os

S3_IP_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
API_KEY = os.getenv("VIRUSTOTAL_API_KEY")
IP_LOOKUP_ENDPOINT = "https://www.virustotal.com/vtapi/v2/ip-address/report"
BATCH_SEARCH = 100
NUM_THREADS = 10
OUTPUT_NAME = "./data/extraction/virustotal/buckets_output.txt"

def exception(request, exception):
    print("Error: {}: {}".format(request.url, exception))

# Fetches CIDR ranges of all S3 IPs from Amazon
def getS3IPs():
    json = requests.get(S3_IP_URL).json()
    cidrs = []
    for prefix in json["prefixes"]:
        if prefix["service"] == "AMAZON" and "ip_prefix" in prefix:
            cidrs.append(prefix["ip_prefix"])
    with open('./data/extraction/virustotal/all_ips.txt', 'w+') as f:
        f.write("\n".join(cidrs))
    print("Wrote cidrs to all_ips.txt")

# Runs a ping scan via Zmap for all S3 IPs
def runZmap():
    with open("./data/extraction/virustotal/all_ips.txt", "r") as f:
        cidrs = f.read().splitlines()
    print(" ".join(cidrs))
    command = "sudo zmap -i ens8 --probe-module=icmp_echoscan -B 10M -o ./data/extraction/virustotal/live_ips.txt " + " ".join(cidrs)
    subprocess.call(command, shell=True)
    subprocess.call("cp ./data/extraction/virustotal/live_ips.txt ./data/extraction/virustotal/rem_ips.txt", shell=True)

def lookup(num):
    with open("./data/extraction/virustotal/rem_ips.txt", "r") as f:
        ips = f.read().splitlines()

    domains = set()
    with open("./data/extraction/virustotal/domains_output.txt", "r") as  f:
        domains = set(line.strip() for line in f)
    buckets = set()
    with open(OUTPUT_NAME, "r") as  f:
        buckets = set(line.strip() for line in f)
    while num > 0:
        numSearches = min(num, BATCH_SEARCH)
        num -= numSearches
        reqs = []
        for i in range(0, numSearches):
            ip = ips.pop(0)
            reqs.append(grequests.get(
                IP_LOOKUP_ENDPOINT,
                params={
                        "apikey": API_KEY,
                        "ip": ip
                        },
                stream=False))

        results = grequests.map(reqs, exception_handler=exception, size=NUM_THREADS)
        for result in results:
            if result is None:
                print("Error: null response")
                continue
            parsed = result.json()
            if ("response_code" in parsed and parsed["response_code"] == "0") or "resolutions" not in parsed:
                result.close()
                continue
            for res in parsed["resolutions"]:
                if "hostname" in res and res["hostname"] is not None:
                    domains.add(res["hostname"])
                    buckets = buckets.union(getBucketsFromText(res["hostname"]))
            result.close()

    with open(OUTPUT_NAME, 'w+') as f:
        f.write("\n".join(buckets))

    with open("./bucket_extraction/virustotal/domains_output.txt", 'w+') as f:
        f.write("\n".join(domains))

    with open("./bucket_extraction/virustotal/rem_ips.txt", "w+") as f:
        f.write("\n".join(ips))

    print("Wrote buckets to " + OUTPUT_NAME)


