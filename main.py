from gevent import monkey as curious_george
curious_george.patch_all(thread=False, select=False)

from dotenv import load_dotenv
load_dotenv()

from bucket_extraction.bing.bing import getBucketsFromBing
from bucket_extraction.virustotal.virustotal import getS3IPs
from bucket_extraction.grayhatwarfare.grayhatwarfare import getGrayhatWarfare
from bucket_extraction.virustotal.virustotal import runZmap
from bucket_extraction.virustotal.virustotal import lookup
from bucket_generation.generators.n_grams.n_grams import streamNGramCandidates
from bucket_generation.evaulator.evaluate_performance import evaluatePerformance, fetchExtractedNames

import argparse

parser = argparse.ArgumentParser(description='Stratosphere: Discover public cloud storage buckets')
parser.add_argument('--backward', help='Train the RNN backwards', action='store_true')
parser.add_argument('--bing', help='Get S3 bucket names from Bing API searches', action='store_true')
parser.add_argument('--eval', help='Evaluate generator performance with provided date of form %%Y_%%M_%%d.', type=str)
parser.add_argument('--fetch', help='Load dataset of JUST extracted bucket names.', action='store_true')
parser.add_argument('--lookup', help='Checks all IPs against VirusTotal', action='store_true')
parser.add_argument('--ips', help='Fetch S3 IPs for Zmap', action='store_true')
parser.add_argument('-n', help='Number of requests to make', type=int,)
parser.add_argument('-i', help='Network interface for zgrab to use')
parser.add_argument('--label', help='Output filename label')
parser.add_argument('--ngrams', help='Generate candidates using NGrams', action='store_true')
parser.add_argument('--ngrams2', help='Generate candidates using NGrams', action='store_true')
parser.add_argument('--ngrams3', help='Generate candidates using NGrams', action='store_true')
parser.add_argument('--templates', help='Template bucket names', action='store_true')
parser.add_argument('-f', help='Path to buckets_output.txt file', type=str)
parser.add_argument('--type', help='Service type', type=str)
parser.add_argument('--rnn', help='Run RNN LSTM generator.', action='store_true')
parser.add_argument('--train', help='Train', action='store_true')
parser.add_argument('--stream', help='Continuously stream candidates', action='store_true')
parser.add_argument('-r', help='Number of candidates per second to generate', type=int)
parser.add_argument('--pingAll', help='Ping all S3 IPs with Zmap', action='store_true')
parser.add_argument('--pcfg', help='Run PCFG generator', action='store_true')
parser.add_argument('--token', help='Run token PCFG generator', action='store_true')
parser.add_argument('--farsight', help='Get bucket names from FarSight', action='store_true')
parser.add_argument('--virustotal', help='Get S3 bucket names from VirusTotal', action='store_true')
parser.add_argument('--grayhatwarfare', help='Get bucket names from grayhatwarfare', action='store_true')
parser.add_argument('--feedToValidator', help='Send buckets_output.txt candidates to validator', action='store_true')
parser.add_argument('--replayExisting', help='Replay existing buckets with a new domain', action='store_true')
parser.add_argument('--domain', help='Root domain to look up', type=str)

args = parser.parse_args()
if args.bing:
	getBucketsFromBing()
elif args.grayhatwarfare:
	getGrayhatWarfare()
elif args.virustotal:
	if args.ips:
		getS3IPs()
	if args.pingAll:
		runZmap()
	if args.lookup:
		lookup(args.n)
elif args.farsight:
	if args.f:
		from bucket_extraction.farsight.farsight import lookupFile
		lookupFile(args.f, args.type)
	else:
		from bucket_extraction.farsight.farsight import lookup
		lookup([args.domain])
elif args.ngrams:
	streamNGramCandidates(args.r)
elif args.ngrams2:
	from bucket_generation.generators.n_grams2.n_grams2 import streamNGrams2
	streamNGrams2(args.r)
elif args.ngrams3:
	from bucket_generation.generators.n_grams2.n_grams2 import streamNGrams3
	streamNGrams3(args.r)
elif args.templates:
	from bucket_generation.generators.templates.templates import steamCandidates
	steamCandidates(args.n)
elif args.replayExisting:
	from bucket_generation.replayExisting import replayExisting
	replayExisting(args.f, args.label)
elif args.rnn:
	from bucket_generation.generators.rnn.rnn import streamRNNGuesses, runTraining
	if args.stream:
		streamRNNGuesses(not args.backward)
	if args.train:
		runTraining(not args.backward)
elif args.feedToValidator:
	from bucket_extraction.feed_to_validator.feed_to_validator import feedToValidator
	feedToValidator(args.f, args.label)
elif args.pcfg:
	from bucket_generation.generators.pcfg.guesser import generatePCFGCandidates
	generatePCFGCandidates()
elif args.token:
	from bucket_generation.generators.token_pcfg.guesser import generatePCFGCandidates
	generatePCFGCandidates()
elif args.eval:
	evaluatePerformance(args.eval)
elif args.fetch:
	fetchExtractedNames()
else:
	print("Error: command not found.")
	parser.print_help()

