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
from enum import Enum, auto
import re

import numpy as np

from bucket_extraction.utils.extract_utils import getBucketsFromText
import bucket_generation.utils as gen_utils

class Type(Enum):
    """
    Token types. These source files are sourced from the data/aux text files
    """
    TECH = auto() # tech term from 
    TEMPLATE = auto()
    WORD = auto()
    TLD = auto()
    FILE = auto()
    NUMBER = auto()
    COMPOUND = auto()
    DOMAIN = auto()
    OTHER = auto()

def getType(token, tech_terms, suffixes, file_extensions, domains, dictionary_words):
    """
    :param: token a string that we are tying to determine its type
    :params: sets of strings that we will check for membership 
    :return: the token type as an enum
    """
    if len(token) == 0:
        return ''
    if token in tech_terms:
        return Type.TECH
    if token in suffixes:
        return Type.TLD
    elif token in file_extensions or token[:-1] in file_extensions:
        return Type.FILE
    elif token in domains or token[:-1] in domains:
        return Type.DOMAIN
    elif token in dictionary_words or token[:-1] in dictionary_words:
        return Type.WORD
    elif token.isdigit():
        return Type.NUMBER
    else:
        for i in range(len(token)):
            if token[:i] in dictionary_words and token[i:] in dictionary_words:
                return Type.COMPOUND
    return Type.OTHER

def loadTypeSets():
    """
    Reads the type sets from the right text files and returns their sets
    """
    # ./data/aux/dictionary.txt' -- from https://github.com/dwyl/english-words/
    # instead, let's use SCOWL like Continella for better comparison. (/usr/share/dict/wodrds)
    with open('/usr/share/dict/words') as f:
        words = set([l.lower().strip() for l in f.readlines()])
    
    # TLDs but a little less strict (i.e. co.uk is not a TLD but a common suffix) 
    # from https://publicsuffix.org/list/public_suffix_list.dat
    with open('./data/aux/public_suffix_list.dat') as f:
        suffixes = set([l.lower().strip() for l in f.readlines()][1:])

    # Just sourced manually via the "Other" section
    with open('./data/aux/tech_terms.txt') as f:
        techTerms = set([l.lower().strip() for l in f.readlines()])
    
    # From https://s3-us-west-1.amazonaws.com/umbrella-static/index.html
    with open('./data/aux/top-1e5-domains.txt') as f:
        domains = set([line.split('.')[-2] for line in f.readlines() if len(line.split('.')) >= 2])

    # sourced manually form wikipedia: https://en.wikipedia.org/wiki/List_of_file_formats
    with open('./data/aux/wikipedia-file-extensions.txt') as f:
        files = set([l.lower().strip() for l in f.readlines()][1:])
    return techTerms, suffixes, files, domains, words


def updateCounters(buckets):
    """
    Generate distributions for each CFG node
    :return: a counter for templates, dictionary words, tech words, files, domains, compound words, TLDS, and numbers
    """

    techTerms, suffixes, files, domains, words = loadTypeSets()

    counters = { key: Counter() for key in Type }
    delimiters = re.compile('[-._]')
    for bucket in buckets:
        tokens = delimiters.split(bucket.lower())
        
        bucketDelimiters = list(delimiters.finditer(bucket))
        template = ''
        for i, token in enumerate(tokens):
            tokenType = getType(token, techTerms, suffixes, files, domains, words)
            if tokenType != '':
                template += tokenType.name
                counters[tokenType][token] += 1
            if i != len(tokens) - 1:
                template += bucketDelimiters[i].group()
                
        counters[Type.TEMPLATE][template] += 1         
    return counters  


def sampleFromCounter(counter):
    total = sum(counter.values())
    return np.random.choice([k for k,v in counter.items()], p=[v/total for k,v in counter.items()])

def generatePCFGCandidates(startingCandidates=None, beanstalkPort=None, name="token_pcfg", numTrials=float("inf"), public=False):
    beanstalkClient = gen_utils.getBeanstalkClient(port=beanstalkPort)
    previouslySeen = startingCandidates | gen_utils.readBucketsFromFile(f"./data/generation/{name}.txt")

    # Randomly generate template according to distro
    delimiters = re.compile('[-._]')
    while numTrials > 0:
         
        # Every 10,000 guesses, update the PCFG.
        print("Updating PCFG.")
        with gen_utils.Profiler(gen_utils.ProfilerType.TRAIN, name):
            candidates = startingCandidates | gen_utils.getExistingAlreadyGuessedBuckets(name, public=public)
            counters = updateCounters(candidates)

        for i in range(int(1e4)):
            with gen_utils.Profiler(gen_utils.ProfilerType.GENERATE, name) as p:
                template = sampleFromCounter(counters[Type.TEMPLATE])        
                tokens = delimiters.split(template)
                templateDelimiters = list(delimiters.finditer(template))
                bucket = ''
                for idx, token in enumerate(tokens):
                    if token != '':
                        bucket += sampleFromCounter(counters[Type[token]])
                    if idx != len(tokens) - 1:
                        bucket += templateDelimiters[idx].group()
                p.bucket(bucket)
                if bucket not in previouslySeen:
                    numTrials -= 1
                    previouslySeen.add(bucket)
                    print('CAND:', bucket)
                    beanstalkClient.put_job(f"generation/{name},{bucket}")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the Token PCFG generator.')
    gen_utils.addArguments(parser)
    args = parser.parse_args()
    candidates = gen_utils.getStartBucketNames(args)    
    generatePCFGCandidates(name=args.name, startingCandidates=candidates, public=args.public, numTrials=int(args.num_trials) or float("inf"))


