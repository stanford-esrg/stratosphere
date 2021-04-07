from argparse import Action
from enum import Enum, auto
import random
import time
from utils import getBucketsFromText
from pystalk import BeanstalkClient
import json
import argparse


def randLines(file, n):
    """
    Grabs n random lines in a file using Algorithm R.
    """
    lines = []
    for num, line in enumerate(file):
        if num < n:
            lines.append(line)
        else:
            randNum = random.randrange(0, num)
            if randNum < n:
                lines[randNum] = line
    return lines

def readFile(file, removeSuffix=False):
    result = []
    with open(file, 'r') as f:
        for line in f:
            if line is not None:
                stripped = line.strip()
                if removeSuffix and ".s3.amazonaws.com" in stripped:
                    stripped = stripped.split(".s3.amazonaws.com")[0]
                result.append(stripped)
    return result

def readFullBucketNamesFromFile(path, timePeriod=None):
    result = set([])
    firstTimestamp = None
    with open(path, 'r') as f:
        for line in f:
            splitLine = line.strip().split(",")
            if len(splitLine) == 2:
                bucket, timestamp = splitLine
                timestamp = int(timestamp)
                if timePeriod:
                    if firstTimestamp:
                        if timestamp - firstTimestamp > timePeriod:
                            print(path, timestamp, firstTimestamp)
                            break
                    else:
                        firstTimestamp = timestamp
            result.add(bucket)
    return result

class BucketType(Enum):
    PUBLIC = auto()
    PRIVATE = auto()

def getFullBuckets(bucketType):
    assert (
        bucketType == BucketType.PUBLIC or bucketType == BucketType.PRIVATE
    ), "Bucket type must be one of PUBLIC/PRIVATE"
    if bucketType == BucketType.PUBLIC:
        return readFullBucketNamesFromFile("./final_output/all_platforms_public.txt")
    if bucketType == BucketType.PRIVATE:
        return readFullBucketNamesFromFile("./final_output/all_platforms_private.txt")

class GeneratorBeanstalkClient(BeanstalkClient):

    def __init__(self, address, port):
        super().__init__(address, port)

    def put_job(self, string, **kwargs):
        # first, check if the job queue isn't too big.
        # if so, sleep proportional to size so that we should slow down at around 10M queue size.        
        jobsReady = super().stats()["current-jobs-ready"]
        time.sleep(jobsReady/1e5)
        super().put_job(string, **kwargs)


def getExistingAlreadyGuessedBuckets(name, public=False):
    """
    Given the generator name, load the dataset comprised
    of already guessed buckets from that generator that also happen to exist.
    :param: The generator name.
    """
    return getExistingBuckets(public=public) & \
        readBucketsFromFile(f"./data/generation/{name}.txt")

def getExistingBuckets(public=False):
    filePath = './final_output/all_platforms_all.txt'
    if public:
        filePath = "./final_output/all_platforms_public.txt"
    return readBucketsFromFile(filePath)

def readBucketsFromFile(path):
    try:
        with open(path, "r") as f:
            return set([bucket for line in f.readlines() for bucket in getBucketsFromText(line)])
    except FileNotFoundError:
        return set()


def getStartBucketNames(args):
    if args.experiment:
        import bucket_generation.evaulator.evaluate_performance as evaluate_performance
        candidates = evaluate_performance.loadExtractedNames("2020_07_20")
        if args.public:
            candidates &= getExistingBuckets(public=True)
        return candidates
    return None

class ProfilerType(Enum):
    TRAIN = "train"
    GENERATE = "generate"

class Profiler:
    
    def __init__(self, profilerType, name):
        assert profilerType in ProfilerType, "Don't know where to write these profiled results."
        assert type(name) == str, "Name must be a string corresponding to the profiler."
        self.type = profilerType
        self.name = name
        self.bucket_name = ""

    def __enter__(self):
        self.start = time.process_time()
        return self
    
    def bucket(self, bucket):
        self.bucket_name = bucket

    def __exit__(self, exc_type, exc_vlaue, exc_tb):
        self.end = time.process_time()
        with open(f"./data/timing/{self.type.value}/{self.name}", "a+") as f:
            f.write(f"{self.bucket_name},{self.end - self.start},{time.time()}\n")
    

def getBeanstalkClient(port=None):
    """
    Start up a beanstalkclient.
    """
    config = {}
    if not port:
        with open('./bucket_validation/listener-config.json', 'r') as f:
            config = json.load(f)
        port = config["BeanstalkHost"].split(":")[1]
    return GeneratorBeanstalkClient("127.0.0.1", port)


def getPreviousCandidates():
    candidates = set()
    with open('./final_output/all_platforms_public.txt', 'r') as f:
        for line in f:
            try:
                cands = list(getBucketsFromText(line))
                if len(cands) > 0:
                    candidates.add(cands[0])
            except Exception as e:
                pass
    return candidates

def addArguments(parser):
    parser.add_argument("name", type=str, help="generator identifier")
    parser.add_argument("--num_trials", type=str, help="Number of trials to run generator.")
    parser.add_argument("--port", type=int, help="The beanstalk job queue port.")
    parser.add_argument("--public", action="store_true", help="Only load the public buckets in our models.")