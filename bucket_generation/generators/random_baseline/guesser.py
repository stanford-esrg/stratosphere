import argparse
import random
import string

from bucket_generation.utils import getBeanstalkClient, addArguments

def randomlyGuessBucketNames(numCharacters=5, numTrials=float("inf"), name="random"):
    beanstalkClient = getBeanstalkClient()
    while numTrials > 0:
        numTrials -= 1
        randomBucket = "".join(
            [
                random.choice(list(string.ascii_lowercase) + list(string.digits) + ["-",".","_"])
                for _ in range(numCharacters)            
            ]
        )
        print(f"CAND: {randomBucket}")
        beanstalkClient.put_job(f"generation/{name},{randomBucket}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the PCFG generator.')
    addArguments(parser)
    parser.add_argument("--character_num", type=int, help="The length of characters to generate.")
    args = parser.parse_args()
    randomlyGuessBucketNames(name=args.name, numTrials=int(args.num_trials), numCharacters=int(args.character_num))
