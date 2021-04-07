"""
Generate bucket names according to the algorithms specified in Continella et al:
https://re.public.polimi.it/retrieve/handle/11311/1065367/314518/2018-continella-bucketsec.pdf

- Enumerate all 3/4 character combinations
- Enumerate word mutations
"""
import argparse
from enum import Enum, auto
import random
import string


import bucket_generation.utils as utils

def generateRandomThreeOrFour(beanstalkPort=None, numTrials=float("inf"), candidates=None, name="continella_threefour"):
    beanstalkClient = utils.getBeanstalkClient(port=beanstalkPort)
    allPossibleCandidates = set()
    for char1 in list(string.ascii_lowercase) + [""]:
        for char2 in list(string.ascii_lowercase):
            for char3 in list(string.ascii_lowercase):
                for char4 in list(string.ascii_lowercase):
                    allPossibleCandidates.add("".join([char1,char2,char3,char4]))
    candidates = random.sample(allPossibleCandidates, min(numTrials, len(allPossibleCandidates)))
    for candidate in candidates:
        beanstalkClient.put_job("generation/{},{}".format(name, candidate))

class Mutation(Enum):

    DELETE = auto()
    DUPLICATE = auto()
    CONCATENATE = auto()
    END = auto()

def mutateWords(beanstalkPort=None, numTrials=float("inf"), name="continella_dictionary"):
    with open("/usr/share/dict/words", "r") as f:
        dictionary = [
            l.strip().lower() for l in f.readlines() 
            if l.strip().isalnum() and all(ord(c) < 128 for c in l.strip()) # alphanumeric ascii characters
        ]
    prevCandidates = utils.readBucketsFromFile("./data/generation/{}.txt".format(name))
    beanstalkClient = utils.getBeanstalkClient(port=beanstalkPort)
    
    while numTrials > 0:
        with utils.Profiler(utils.ProfilerType.GENERATE, name) as p:
            word = random.choice(dictionary)
            mutation = random.choice([mutation for mutation in Mutation])
            assert any([mutation == m for m in Mutation]), "wrong equals"
            while mutation != Mutation.END:
                if mutation == Mutation.DELETE and len(word) > 1:
                    deletedCharIdx = random.randint(0, len(word) - 1)
                    word = word[:deletedCharIdx] + word[deletedCharIdx + 1:]
                elif mutation == Mutation.DUPLICATE and len(word) < 63: # Can't exceed limit.
                    dupCharIdx = random.randint(0, len(word) - 1)
                    word = word[:dupCharIdx] + 2 * word[dupCharIdx] + word[dupCharIdx + 1:]
                elif mutation == Mutation.CONCATENATE:
                    otherWord = random.choice(dictionary)
                    if len(word) + len(otherWord) < 63:
                        if random.random() < .5:
                            word += otherWord
                        else:
                            word = otherWord + word
                mutation = random.choice([mutation for mutation in Mutation])
            p.bucket(word)
            if word not in prevCandidates:
                print(word)
                prevCandidates.add(word)
                beanstalkClient.put_job("generation/{},{}".format(name, word))
                numTrials -= 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the continella experiments.')
    utils.addArguments(parser)
    parser.add_argument("--mutateWords", action="store_true", help="Run the mutateWords experiment.")
    parser.add_argument("--generateRandom34", action="store_true", help="Generate all 3/4 character sequences.")
    args = parser.parse_args()
    assert args.mutateWords != args.generateRandom34, "One of --mutateWords and --generateRandom34 must be selected."
    
    if args.mutateWords:
        mutateWords(numTrials=int(args.num_trials) or float("inf"), name=args.name)
    elif args.generateRandom34:
        generateRandomThreeOrFour(name=args.name)
    
        

