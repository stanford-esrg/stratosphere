"""
Inspired from https://web.eecs.utk.edu/~mschucha/netsec/readings/cfgPass.pdf
Predict token based on distribution of tokens bucketd in types as CFG.
To begin, we will just do a really primitive survey: 
break bucket into delimiters, characters of a certain length, and
numbers of certain length. We can definitely extend this to
with more specific types.
Types : Ci -> i characters, Ni -> i numbers,
B -> T-T-T
"""
import argparse
from collections import Counter
import re

import numpy as np

from bucket_extraction.utils.extract_utils import getBucketsFromText
import bucket_generation.utils as gen_utils

templates = Counter()
C = {}
N = {}
for i in range(64):
    C[str(i)] = Counter()
    N[str(i)] = Counter()

def getType(c):
    if c.isalpha():
        return 'C'
    if c.isnumeric():
        return 'N'
    else:
        return c

def updateCounters(bucket):
    template = ''
    while len(bucket) > 0:
        ci = re.search('([a-z]*)', bucket).group()
        if len(ci) > 0:
            template += 'C' + str(len(ci))
            C[str(len(ci))][ci] += 1
            bucket = bucket[len(ci):]
            continue

        ni = re.search('([0-9]*)', bucket).group()
        if len(ni) > 0:
            template += 'N' + str(len(ni))
            bucket = bucket[len(ni):]
            N[str(len(ni))][ni] += 1
            continue

        other = re.search('([^a-z0-9]*)', bucket).group()
        template += other
        bucket = bucket[len(other):]
    templates[template] += 1

def sampleFromCounter(counter):
    total = sum(counter.values())
    return np.random.choice([k for k,v in counter.items()], p=[v/total for k,v in counter.items()])

def generatePCFGCandidates(name="pcfg", startingCandidates=None, beanstalkPort=None, numTrials=float("inf"), public=False):
    beanstalkClient = gen_utils.getBeanstalkClient(port=beanstalkPort)
    candidates = startingCandidates or gen_utils.getExistingBuckets(public=public)
    previouslySeen = startingCandidates | gen_utils.readBucketsFromFile(f"./data/generation/{name}.txt")

    # Randomly generate template according to distro
    while numTrials > 0:
        print("Updating PCFG.")
        # In intervals of 10,000 guesses, update our PCFG from our successful guesses.
        with gen_utils.Profiler(gen_utils.ProfilerType.TRAIN, name):
            candidates = startingCandidates | gen_utils.getExistingAlreadyGuessedBuckets(name, public=public)
            for candidate in candidates:
                updateCounters(candidate.strip().lower())
        
        
        for _ in range(int(1e4)):
            with gen_utils.Profiler(gen_utils.ProfilerType.GENERATE, name) as p:
                template = sampleFromCounter(templates)
                print(template)
                bucket = '' 
                while len(template) > 0:
                    if template[0] == 'C':
                        ni = re.search('([0-9]*)', template[1]).group()
                        i = ni
                        try:
                            bucket += sampleFromCounter(C[i])
                        except KeyError:
                            import pdb
                            pdb.set_trace()
                        template = template[1+len(ni):]
                    elif template[0] == 'N':
                        ni = re.search('([0-9]*)', template[1]).group()
                        i = ni
                        template = template[1+len(ni):]
                        bucket += sampleFromCounter(N[i])
                    else:
                        bucket += template[0]
                        template = template[1:]
                p.bucket(bucket)
                if bucket not in previouslySeen:
                    previouslySeen.add(bucket)
                    print('CAND:', bucket)
                    beanstalkClient.put_job(f"generation/{name},{bucket}")
                    numTrials -= 1
        
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the PCFG generator.')
    gen_utils.addArguments(parser)
    args = parser.parse_args()
    candidates = gen_utils.getStartBucketNames(args)
    generatePCFGCandidates(name=args.name, startingCandidates=candidates, public=args.public, numTrials=int(args.num_trials) or float("inf"))
