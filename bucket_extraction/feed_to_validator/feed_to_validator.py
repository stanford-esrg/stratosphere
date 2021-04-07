from pystalk import BeanstalkClient
import time

beanstalk_client = BeanstalkClient('127.0.0.1', 11301)

def feedToValidator(file, label):
    with open(file, 'r') as f:
        lines = list(f)
    for line in lines:
        line = line.strip()
        print('CAND:', line)
        beanstalk_client.put_job("extraction/" + label + "," + line)
