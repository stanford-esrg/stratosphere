import grequests
import csv
from .. import getBucketsFromText
import random
import string
import os

subscription_key = os.getenv("BING_API_KEY")
search_url = "https://api.cognitive.microsoft.com/bing/v7.0/search"

headers = {"Ocp-Apim-Subscription-Key": subscription_key}

NUM_SEARCHES = 100
NUM_THREADS = 10
SEED_LENGTH = 3
OUTPUT_NAME = "./data/extraction/bing/buckets_output.txt"

def exception(request, exception):
    print("Error: {}: {}".format(request.url, exception))

def getBucketsFromBing():

    try:
        with open(OUTPUT_NAME, "r") as  f:
            buckets = set(line.strip() for line in f)
    except Exception as e:
        buckets = set()

    initLen = len(buckets)

    reqs = []

    for i in range(0, NUM_SEARCHES):
        rand = ''.join(random.choice(string.ascii_lowercase) for _ in range(SEED_LENGTH))
        platform = random.choice(["s3.amazonaws.com", "storage.googleapis.com", "oss.aliyuncs.com"])
        reqs.append(grequests.get(
            search_url,
            headers=headers,
            params={
                    "q": "site:" + platform + " \"" + rand + "\"",
                    "responseFilter": "Webpages",
                    "count": 50,
                    "offset": 0
                    },
            stream=False
            ))

    results = grequests.map(reqs, exception_handler=exception, size=NUM_THREADS)

    for result in results:
        if result is None:
            continue
        
        result.close()

        if result.status_code != 200:
            print(result)
            continue

        parsed = result.json()
        if "webPages" in parsed and "value" in parsed["webPages"]:
            for page in parsed["webPages"]["value"]:
                if "snippet" in page:
                    buckets = buckets.union(getBucketsFromText(page["snippet"]))
                    buckets = buckets.union(getBucketsFromText(page["url"]))

    numAdded = len(buckets) - initLen
    ratio = numAdded / NUM_SEARCHES
    print("Discovered {} new buckets. ({} buckets / search)".format(numAdded, ratio))
    print("Wrote buckets to " + OUTPUT_NAME)

    with open(OUTPUT_NAME, 'w+') as f:
        f.write("\n".join(buckets))
