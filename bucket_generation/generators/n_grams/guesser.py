
import argparse
from collections import Counter, defaultdict
import json
import random
import re
import time

import numpy as np
from pystalk import BeanstalkClient

from bucket_extraction import getBucketsFromText
import bucket_generation.utils as generation_utils 


def generateNGrams(candidates):
    ngrams = defaultdict(lambda: Counter())
    lengthDistribution = Counter()
    delimiterDistribution = Counter()
    for bucket in candidates:
        splitBucket = re.split(r'([\.|\-|_])', bucket.lower().strip())
        delimiterDistribution.update(
            [
                d for d in splitBucket if d in [".", "-", "_"]
            ]
        )
        tokens = [t for t in splitBucket if t not in [".", "-", "_"]]
        for i in range(len(list(tokens))):
             ngrams[
                tuple(tokens[max(0, i-1): i])
            ][tokens[i]] += 1
        lengthDistribution[len(tokens)] += 1
    return ngrams, lengthDistribution, delimiterDistribution

def sampleFromCounter(counter):
    total = sum(counter.values())
    return np.random.choice([k for k,v in counter.items()], p=[v/total for k,v in counter.items()])

def streamNGramCandidates(
    startingCandidates=None, beanstalkPort=None, numTrials=float("inf"), name="ngrams", experiment=False, public=False,
):
    candidates = startingCandidates or generation_utils.getExistingBuckets(public=public)
    previouslySeen = startingCandidates | generation_utils.readBucketsFromFile(f"./data/generation/{name}.txt")
    beanstalkClient = generation_utils.getBeanstalkClient(port=beanstalkPort)

    while numTrials > 0:
        # Update our prior distribution for every 10,000 candidates.
        print("Initializing bigram distribution.")
        
        with generation_utils.Profiler(generation_utils.ProfilerType.TRAIN, name):
            if experiment:
                # add all existing buckets that have been guessed by ngrams and are in seed set.
                candidates |= generation_utils.getExistingAlreadyGuessedBuckets(name, public=public)
            nGrams, lengthDistribution, delimiterDistribution = generateNGrams(candidates)
        
        
        for _ in range(int(1e4)):
            with generation_utils.Profiler(generation_utils.ProfilerType.GENERATE, name) as p:
                bucket = []
                bucketLength = sampleFromCounter(lengthDistribution)
                for _ in range(bucketLength):
                    if len(bucket) > 0:
                        bucket += [sampleFromCounter(delimiterDistribution)]
                    ngramsKey = tuple(bucket[-2:-1])
                    if ngramsKey in nGrams:
                        bucket += sampleFromCounter(nGrams[ngramsKey])
                bucket = "".join(bucket)
                p.bucket(bucket)
                if len(bucket) < 64 and bucket not in previouslySeen:
                    previouslySeen.add(bucket)
                    beanstalkClient.put_job("generation/{},{}".format(name, bucket))
                    print("Generated: " + bucket)
                    numTrials -= 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the ngrams generator.')
    generation_utils.addArguments(parser)
    args = parser.parse_args()
    candidates = generation_utils.getStartBucketNames(args)
    streamNGramCandidates(name=args.name, startingCandidates=candidates, public=args.public, numTrials=int(args.num_trials) or float("inf"))