import requests
import json
import os

def getGrayhatWarfare():
    buckets = []
    num_buckets = 100000
    current = 0
    chunk_size = 50000

    access_token = os.getenv("GRAYHAT_ACCESS_TOKEN")

    while current < num_buckets:
      resp = requests.get("https://buckets.grayhatwarfare.com/api/v1/buckets/" + str(current) + "/" + str(chunk_size) + "?access_token=" + access_token)
      resp_json = json.loads(resp.text)
      for bucket in resp_json["buckets"]:
        if bucket["type"] == "aws":
          buckets.append(bucket["bucket"])
      print(len(resp_json["buckets"]))
    
      current += chunk_size
    out = './data/extraction/grayhatwarfare/grayhatwarfare.txt'
    with open(out, 'w+') as f:
        for b in buckets:
            f.write(b + '\n')
    print("Wrote buckets to " + out)
            
if __name__ == "__main__":
  getGrayhatWarfare()