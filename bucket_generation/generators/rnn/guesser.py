"""
Jack Cable and Drew Gregory
LSTM Generator to produce S3 Bucket Candidate Names.
This uses a one-to-many design so that we can generate names from scratch (only basing off of a single character).
Inspired by:
    - https://towardsdatascience.com/generating-text-using-a-recurrent-neural-network-1c3bfee27a5e
    - https://github.com/keras-team/keras/blob/master/examples/lstm_text_generation.py
    - https://stackoverflow.com/questions/38714959/understanding-keras-lstms?rq=1
Here was a useful answer to why the output dimensions are for multiple sequences:
    - https://stackoverflow.com/questions/43702481/why-does-keras-lstm-batch-size-used-for-prediction-have-to-be-the-same-as-fittin
"""
import argparse
from datetime import date
import json
import numpy as np
import random
import time

from keras.callbacks import ModelCheckpoint, LambdaCallback
from keras.layers import Activation, Dense, Flatten, LSTM, Masking
from keras.models import Sequential, load_model
from keras.callbacks import ReduceLROnPlateau
from keras.optimizers import RMSprop

import bucket_generation.utils as generation_utils
from bucket_extraction.utils.extract_utils import getBucketsFromText
from bucket_generation.utils import getExistingAlreadyGuessedBuckets, getExistingBuckets


beanstalkClient = None

def sample(preds, temperature=1.0):
    # helper function to sample an index from a probability array
    preds = np.asarray(preds).astype('float64')
    preds = np.log(preds) / temperature
    exp_preds = np.exp(preds)
    preds = exp_preds / np.sum(exp_preds)
    probas = np.random.multinomial(1, preds, 1)
    return np.argmax(probas)

def standardizeText(line, forward=True):
    """
    Remove whitespace, lowercase,
     and end with termination character \r 
    """
    text = line.strip().lower()[:63]
    return (text if forward else text[::-1]) + '\r'

def buildModel(uniqueChars):
    # This is because we have variable length input sequences and thus different
    # dimensions, see https://github.com/keras-team/keras/issues/6776
    
    hiddenUnits = 64
    model = Sequential()
    inShape = (64, uniqueChars) # bucket names need to be between 3-63 chars
    model.add(
        LSTM(
            hiddenUnits, input_shape=inShape,
            return_sequences=True,
        )
    )
    model.add(Flatten()) # https://github.com/keras-team/keras/issues/6351
    model.add(Dense(uniqueChars, activation='softmax'))
    optimizer = RMSprop(lr=0.01)
    model.compile(loss='categorical_crossentropy', optimizer=optimizer)
    return model
    
def addNamesToCorpus(x,y, names, startingCharCounts, forward):
    for bucket_name in names:
        goodName = standardizeText(bucket_name,forward=forward)
        for i in range(len(goodName)-1):
            x.append(goodName[:i+1])
            y.append(goodName[i+1])
        startC = goodName[0]
        if startC not in startingCharCounts:
            startingCharCounts[startC] = 0
        startingCharCounts[startC] += 1


def addNamesToCorpusFromFile(x,y, filename, startingCharCounts, forward):
    buckets = set(random.sample(generation_utils.readBucketsFromFile(filename), k=int(1e4)))
    addNamesToCorpus(x,y, buckets, startingCharCounts, forward)


def generateText(startingCounts, model, indicesChar, charIndices, forward):
    startingChar = startingCounts[
        sample([c[1] for c in startingCounts])
    ][0]
    sentence = startingChar
    for _ in range(63):
        x_pred = np.zeros((1, 64, 40))
        for t, char in enumerate(sentence):
            x_pred[0, t, charIndices[char]] = 1.
        preds = model.predict(x_pred, verbose=0)[0]
        nextIndex = sample(preds)
        if nextIndex == charIndices['\r']:
            if len(sentence) <= 3:
                continue
            else:
                break
        sentence += indicesChar[str(nextIndex)]
    return sentence if forward else sentence[::-1]

def onEpochEnd(epoch, logs, startingCounts, model, indicesChar, charIndices, forward):
    print('FINISHED EPOCH', epoch)
    for _ in range(10):
        print(generateText(startingCounts, model, indicesChar, charIndices, forward))


def trainModel(
    startingCharCounts, model, filepath, charIndices, indicesChar, forward, 
    candidates=None, name=None, public=False):
    
    # Collect all bucket names and starting character distribution
    sentences = []
    nextChars = []
    candidates = candidates or getExistingBuckets(public=public)
    candidates |= getExistingAlreadyGuessedBuckets(name, public=public)

    # This many candidates wouldn't fit in memory, so let's grab 10,000 buckets at random.
    sampledBucketNames = random.sample(
        candidates,
        int(1e4)
    )
    addNamesToCorpus(sentences, nextChars, sampledBucketNames, startingCharCounts, forward)
  
    
    x = np.zeros((len(sentences), 64, 40), dtype=np.bool)
    y = np.zeros((len(sentences), 40), dtype=np.bool)

    for i, sentence in enumerate(sentences):
        for t, char in enumerate(sentence):
            x[i, t, charIndices[char]] = 1
        y[i, charIndices[nextChars[i]]] = 1
    print('NUM SENTENCES', len(sentences))
    startingCounts = list(startingCharCounts.items())

    checkpoint = ModelCheckpoint(filepath, monitor='loss',
                             verbose=1, save_best_only=True,
                             mode='min')
    checkpoint_backup = ModelCheckpoint("{}.{}".format(filepath, date.today().strftime("%Y_%m_%d")),monitor='loss',
                             verbose=1, save_best_only=True,
                             mode='min')
    reduce_lr = ReduceLROnPlateau(monitor='loss', factor=0.2,
                              patience=1, min_lr=0.00001)

    print_callback = LambdaCallback(on_epoch_end=lambda x,y: onEpochEnd(
        x, y,startingCounts, model, indicesChar, charIndices, forward
    ))
    callbacks = [print_callback, checkpoint, checkpoint_backup, reduce_lr]
    print('FITTING')
    print(len(x),len(y))
    while True:
        try:
            model.fit(x, y, batch_size=1000, epochs=10, callbacks=callbacks, use_multiprocessing=True)
            break
        except OSError as e:
            # Just retry, after waiting some time.
            time.sleep(17)
    return model

def makeGuesses(model, startingCharCounts, charIndices, indicesChar, forward, name="name", previous=None):
    candidates = previous or set()
    startingCounts = list(startingCharCounts.items())
    for _ in range(10000):
        with generation_utils.Profiler(generation_utils.ProfilerType.GENERATE, name) as p:
            cand = generateText(startingCounts, model, indicesChar, charIndices, forward)
            p.bucket(cand)
            print(len(candidates))
            if cand not in candidates:
                print('CAND', cand)
                beanstalkClient.put_job(f"generation/{name},{cand}")
                candidates.add(cand)
            else:
                print("ALREADY GUESSED")


def runTraining(name="rnn", forward=True, filepath=None, candidates=None, public=False):
    chars = 40
    assert filepath, "No weights filepath provided."
    try:
        model = load_model(filepath)
    except Exception as e:
        print("COULDNT LOAD MODEL", e)
        model = buildModel(chars)
    model.summary()
    charIndices = {}
    with open('./data/generation/rnn/charIndices.json') as f:
        charIndices = json.load(f,)
    indicesChar = {}
    with open('./data/generation/rnn/indicesChar.json') as f:
        indicesChar = json.load(f,)
    startingCharCounts = {}
    while True:
        with generation_utils.Profiler(generation_utils.ProfilerType.TRAIN, name):
            model = trainModel(
                startingCharCounts, model, filepath, charIndices, indicesChar,forward, 
                candidates=candidates,
                name=name, public=public
            )

def streamRNNGuesses(
    forward=True, beanstalkPort=None, name="rnn", numTrials=None, weights_path=None, seedSet=None
):

    if not numTrials:
        numTrials = float("inf")
    
    global beanstalkClient    
    beanstalkClient = generation_utils.getBeanstalkClient(port=beanstalkPort)

    filepath = weights_path
    charIndices = {}
    with open('./data/generation/rnn/charIndices.json') as f:
        charIndices = json.load(f,)
    indicesChar = {}
    with open('./data/generation/rnn/indicesChar.json') as f:
        indicesChar = json.load(f,)
    startingCharCounts = {}
    sentences = []
    nextChars = []
    numTrials /= 1e4
    previouslySeen = generation_utils.readBucketsFromFile(f"data/generation/{name}.txt") | (seedSet or set())
    # This is just to load up the startingCharCounts.
    addNamesToCorpusFromFile(sentences, nextChars, './final_output/all_platforms_all.txt', startingCharCounts, forward)
    sentences = []
    nextChars = []
    while numTrials > 0:
        try:
            model = load_model(filepath)
        except Exception as e:
            print("COULDNT LOAD MODEL, WAITING A MINUTE", e)
            time.sleep(60)
            continue
        model.summary()
        makeGuesses(model, startingCharCounts, charIndices, indicesChar, forward, name=name, previous=previouslySeen)
        numTrials -= 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Train rnn.')
    generation_utils.addArguments(parser)
    parser.add_argument("--train", action="store_true", help="Train rnn instead of stream guesses.")
    parser.add_argument("--forward", action="store_true", help="Run the rnn in forward vs. backward mode.")
    parser.add_argument("--stream", action="store_true", help="Stream guesses based off of the model.")

    args = parser.parse_args()
    name = args.name or "rnn"
    assert args.train or args.stream, "Must have one of --stream or --train."
    weights_path = "data/generation/rnn/{}_weights_{}.hdf5".format(
        name,
        "forward" if args.forward else "backward",
    )
    if args.stream:
        extractedCandidates = generation_utils.getStartBucketNames(args) if args.experiment else None
        streamRNNGuesses(
            beanstalkPort=args.port,
            forward=args.forward,
            name=name,
            numTrials=int(args.num_trials) or float("inf"),
            weights_path=weights_path,
            seedSet=extractedCandidates,
        )
    elif args.train:
        
        extractedCandidates = generation_utils.getStartBucketNames(args) if args.experiment else None 
        runTraining(
            name=name,
            forward=args.forward,
            filepath=weights_path,
            candidates=extractedCandidates,
            public=args.public,
        )
