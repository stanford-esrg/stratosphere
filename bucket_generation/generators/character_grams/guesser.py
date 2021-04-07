"""
Inspired from https://dl.acm.org/doi/pdf/10.1145/1102120.1102168 and https://hal.archives-ouvertes.fr/hal-01112124/file/omen.pdf
Do n-grams where n=4, but look at the character level.
"""
import argparse
from collections import Counter, defaultdict
import string

import numpy as np

from bucket_extraction.utils.extract_utils import getBucketsFromText
import bucket_generation.utils as gen_utils

def generateLaplaceDistribution():
    return Counter(list(string.ascii_lowercase) + list(string.digits) + ["-",".","_"])

def getCounters(buckets):
    """
    Build distribution from left to right of prev4 chars -> next char.
    We will have some default Laplace smoothing, both to add a little bit of randomness,
    and to make sure that we have at least some distribution if the sequence
    has not been encountered before.
    """
    lengthDistribution = Counter()
    counters = defaultdict(generateLaplaceDistribution)
    for bucket in buckets:
        bucketString = bucket.lower().strip()
        for i in range(len(bucketString)):
            counters[
                bucketString[max(0, i-4): i] # If we aren't at fourth character yet, just do previous characters.
            ][bucketString[i]] += 1
        lengthDistribution[len(bucket)] += 1000
    return counters, lengthDistribution

def sampleFromCounter(counter):
    total = sum(counter.values())
    return np.random.choice([k for k,v in counter.items()], p=[v/total for k,v in counter.items()])

def generateCandidates(name="c4grams", startingCandidates=None, beanstalkPort=None, numTrials=float("inf"), public=False):
    beanstalkClient = gen_utils.getBeanstalkClient(port=beanstalkPort)
    previouslySeen = startingCandidates | gen_utils.readBucketsFromFile(f"./data/generation/{name}.txt")
    
    # Randomly generate template according to distro
    while numTrials > 0:
        print("Updating character-level 4-grams.")
        # In intervals of 10,000 guesses, update our PCFG from our successful guesses.
        with gen_utils.Profiler(gen_utils.ProfilerType.TRAIN, name):
            candidates = startingCandidates | gen_utils.getExistingAlreadyGuessedBuckets(name, public=public)
            counters, lengthDistribution = getCounters(candidates)

        
        for _ in range(int(1e4)):
            with gen_utils.Profiler(gen_utils.ProfilerType.GENERATE, name) as p:
                bucket = ""
                bucketLength = sampleFromCounter(lengthDistribution)
                while len(bucket) < bucketLength:
                    bucket += sampleFromCounter(counters[bucket[max(0, len(bucket)-4): len(bucket)]])
                
                p.bucket(bucket)
                if bucket not in previouslySeen:
                    previouslySeen.add(bucket)
                    print('CAND:', bucket)
                    beanstalkClient.put_job(f"generation/{name},{bucket}")
                    numTrials -= 1
        
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the a character level n-grams.')
    gen_utils.addArguments(parser)
    args = parser.parse_args()
    candidates = gen_utils.getStartBucketNames(args)
    generateCandidates(name=args.name, startingCandidates=candidates, public=args.public, numTrials=int(args.num_trials) or float("inf"))
