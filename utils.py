from bucket_extraction import getBucketsFromText

def initializeSetFromTextFile(path, setType):
    """
    Initialize set comprised of lines from the text file
    :param path: path to text file
    :param setType: a set that we will add lines to
    """
    with open(path,'r') as f:
        for line in f:
            setType.add(line.strip())

def getBucketsFromTextFile(path):
    buckets = set()
    with open(path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            buckets = buckets.union(getBucketsFromText(line))
    return buckets
