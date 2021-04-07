package main

/**
 * Creates a bloom filter and initilizes the filter to be from all read lines in all the validator files.
 */

import (
	"bufio"
	"log"
	"os"
	"strings"

	"github.com/willf/bloom"
)

/**
 * Adds all the lines of text from the textfile to the bloom filter.
 */
func addFromTextFile(filter *bloom.BloomFilter, filePath string) {
	file, err := os.Open(filePath)
	if err != nil {
		log.Fatal(err)
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		lineContents := strings.Split(line, ",")
		if len(lineContents) == 2 { // Of the form "<candidate>,<timestamp>"
			filter.AddString(lineContents[0])
		} else { // Normal form of <candidate>
			filter.AddString(scanner.Text())
		}
	}
}

func main() {
	filter := bloom.NewWithEstimates(300000000, .000001)

	f1, err := os.OpenFile("./bucket_validation/bloom/candidate_set.bloom", os.O_CREATE|os.O_RDONLY, 0644)
	if err != nil {
		panic(err)
	}
	defer f1.Close()

	r := bufio.NewReader(f1)
	readsize, err := filter.ReadFrom(r)

	if err != nil {
		panic(err)
	}
	log.Println(readsize)

	for i := 1; i < len(os.Args); i++ {
		log.Println(os.Args[i], filter.TestString(os.Args[i]))
	}

}
