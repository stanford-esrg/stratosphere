from pystalk import BeanstalkClient
import time
from bucket_extraction import getBucketsFromText

beanstalk_client = BeanstalkClient('127.0.0.1', 11301)

def replayExisting(file, label):
    with open(file, 'r') as f:
        for line in f:
            buckets = list(getBucketsFromText(line))
            for bucket in buckets:
                print('CAND:', bucket)
                beanstalk_client.put_job("generation/" + label + "," + bucket)
                time.sleep(1/200)

