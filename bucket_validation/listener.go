package main

/*
	This Listener takes in lines of IP addresses as input and delgates their results
	to processes.
*/

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/willf/bloom"

	"github.com/beanstalkd/go-beanstalk"
	"github.com/spf13/viper"
)

// Configuration class allows you to specify the source ips and read limit (in KB)
type Configuration struct {
	NumSenders       int
	BeanstalkHost    string
	ReadLimitPerHost int
	SourceIPs        []string
}

/*
Validator represents a process that takes in S3 hostnames and resolves their results to an
output file.
*/
type Validator struct {
	stdIn                io.WriteCloser
	stdOut               io.ReadCloser
	cmd                  *exec.Cmd
	ip                   string
	lastResponseReceived time.Time
	lastResponseMutex    sync.Mutex
}

//OutputFile represented the bucketed output types, abstracted just in case we want more member fields.
type OutputFile struct {
	f *os.File
}

var config Configuration

// The list of hosts to try a bucket against if no host is provided
var hosts []string

// The list of hosts that are accepted
var acceptedHosts []string

var validators []*Validator

var responseChan chan string

// The maximum number of times a single bucket is tried
var MAX_RETRIES = 3

type OpenRequest struct {
	provider    string
	source      string
	numAttempts int
	lastTried   time.Time
}

// A map from bucket names to their sources and number of retiries
var openRequests map[string]OpenRequest = make(map[string]OpenRequest)
var openRequestsMutex sync.Mutex

// Mutex for bloom filter
var previouslySeenMutex sync.Mutex

func handleErrorFatal(err error) {
	if err != nil {
		log.Fatal(err)
	}
}

func handleError(err error) {
	if err != nil {
		log.Println(err)
	}
}

func initializeZGrab(numSenders int, readLimitPerHost int, sourceIP string) *Validator {
	path, ok := os.LookupEnv("GOPATH")
	if ok {
		cmd := exec.Command(path+"/bin/zgrab2", "http",
			"--use-https",
			"--port", "443",
			"--read-limit-per-host", fmt.Sprintf("%d", readLimitPerHost),
			"--senders", fmt.Sprintf("%d", numSenders),
			"--source-ip", sourceIP,
			"--flush")
		stdout, err := cmd.StdoutPipe()
		handleError(err)
		cmd.Stderr = os.Stderr
		stdin, err := cmd.StdinPipe()
		handleError(err)
		err = cmd.Start()
		handleError(err)
		fmt.Printf("ZGrab running with %d senders on IP %s \n", numSenders, sourceIP)
		return &Validator{stdin, stdout, cmd, sourceIP, time.Now(), sync.Mutex{}}
	}
	fmt.Printf("GOPATH not set. %s", path)

	return nil
}

func delegateRequestJobs(files map[string]OutputFile, beanstalkHost string, prevSeen *bloom.BloomFilter) {
	jobQueue, err := beanstalk.Dial("tcp", beanstalkHost)
	handleErrorFatal(err)
	for {
		for i, v := range validators {
			v.lastResponseMutex.Lock()
			// If more than one minute has elapsed, restart validator
			if time.Since(v.lastResponseReceived) > time.Minute {
				closeValidator(v)
				initiateValidator(i)
				receiveResponse(validators[i])
				v.lastResponseReceived = time.Now()
			}
			v.lastResponseMutex.Unlock()
			// Check if any buckets should be retried
			shouldContinue := false
			openRequestsMutex.Lock()
			for bucket, openRequest := range openRequests {
				if openRequest.numAttempts > MAX_RETRIES {
					delete(openRequests, bucket)
					continue
				}
				if time.Since(openRequest.lastTried) > 60*time.Minute {
					spawnBucket(bucket, openRequest.provider, openRequest.source, v, openRequest.numAttempts+1, false, prevSeen)
					shouldContinue = true
					break
				}
			}
			openRequestsMutex.Unlock()
			if shouldContinue {
				continue
			}

			id, body, err := jobQueue.Reserve(5 * time.Second)
			log.Println("Reserved job " + string(body))
			if err != nil {
				if !strings.Contains(err.Error(), "timeout") { // Don't print if it's a timeout
					log.Println("Error reserving job: " + err.Error())
				}
				continue
			}
			jobContents := strings.Split(string(body), ",")
			if len(jobContents) != 2 {
				log.Println("INVALID FORMAT FOR " + string(body) + ": NEEDS ',' DELIMITER")
				err = jobQueue.Delete(id)
				continue
			}
			path := jobContents[0]
			bucket := jobContents[1]

			// If a host is already provided, we use only that host
			hostFound := false
			for _, host := range acceptedHosts {
				if strings.Contains(bucket, host) {
					spawnBucket(bucket, host, path, v, 1, true, prevSeen)
					hostFound = true
					break
				}
			}

			// Otherwise, we try on all hosts
			if !hostFound {
				for _, host := range hosts {
					bucketName := bucket
					if host == "oss-us-east-1.aliyuncs.com" {
						// For alibaba, replace dots with hyphens
						bucketName = strings.Replace(bucketName, ".", "-", -1)
					}
					spawnBucket(bucketName+"."+host, host, path, v, 1, true, prevSeen)
				}
			}

			err = jobQueue.Delete(id)
			handleError(err)
		}
		log.Println("Sleeping for 0.25 second")
		time.Sleep(time.Duration(250) * time.Millisecond)
	}

}

func spawnBucket(bucket string, host string, path string, v *Validator, count int, shouldLock bool, prevSeen *bloom.BloomFilter) {

	// First, confirm that we have not tried the bucket before.
	// Currently commented out - TODO: add option to use bloom filter
	// previouslySeenMutex.Lock()
	// old := prevSeen.Test([]byte(bucket))
	// previouslySeenMutex.Unlock()
	old := false

	if old { // The bucket has already been tried: just ignore.
		log.Println("Have seen " + bucket)
		if shouldLock {
			openRequestsMutex.Lock()
		}
		delete(openRequests, bucket)
		if shouldLock {
			openRequestsMutex.Unlock()
		}
		return
	}

	log.Println("Have not seen " + bucket)
	fmt.Println("Sending: " + bucket)

	go writeWithTimeout(v.stdIn, []byte(bucket+"\n"))

	if shouldLock {
		openRequestsMutex.Lock()
	}
	openRequests[bucket] = OpenRequest{host, path, count, time.Now()}
	if shouldLock {
		openRequestsMutex.Unlock()
	}
}

func writeWithTimeout(stdIn io.WriteCloser, text []byte) {
	c := make(chan string, 1)
	go func() {
		stdIn.Write(text)
		c <- "done"
	}()
	select {
	case <-c:
	case <-time.After(500 * time.Millisecond):
	}
}

func receiveResponses() {
	for _, v := range validators {
		receiveResponse(v)
	}
}

func receiveResponse(v *Validator) {
	go func(v *Validator, c chan string) {
		scanner := bufio.NewScanner(v.stdOut)
		if scanner != nil {
			for scanner.Scan() {
				v.lastResponseMutex.Lock()
				v.lastResponseReceived = time.Now()
				v.lastResponseMutex.Unlock()

				text := scanner.Text()
				c <- text
			}
		}
	}(v, responseChan)
}

func writeResponses(files map[string]OutputFile, prevSeen *bloom.BloomFilter) {
	for result := range responseChan {
		var responseBody interface{}
		err := json.Unmarshal([]byte(result), &responseBody)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
		} else {
			responseJSON := responseBody.(map[string]interface{})
			domain := responseJSON["domain"].(string)
			data := responseJSON["data"].(map[string]interface{})
			if data["http"] == nil {
				continue
			}
			http := data["http"].(map[string]interface{})
			if http["result"] == nil {
				continue
			}
			resultJSON := http["result"].(map[string]interface{})
			if resultJSON["response"] == nil {
				continue
			}
			response := resultJSON["response"].(map[string]interface{})
			statusCode := int(response["status_code"].(float64))
			fmt.Printf("%d %s\n", statusCode, domain)

			// Add bucket to our previously seen set.
			previouslySeenMutex.Lock()
			prevSeen.Add([]byte(domain))
			previouslySeenMutex.Unlock()

			// Alibaba: Check if response is redirecting to a different bucket
			if strings.Contains(domain, "oss-us-east-1.aliyuncs.com") && response["body"] != nil {
				body := response["body"].(string)
				if statusCode == 403 && strings.Contains(body, "must be addressed") && strings.Contains(body, "<Endpoint>") {
					newHost := strings.Split(strings.Split(body, "</Endpoint>")[0], "<Endpoint>")[1]
					bucket := strings.Split(domain, ".oss-us-east-1.aliyuncs.com")[0] + "." + newHost
					openRequestsMutex.Lock()
					origRequest := openRequests[domain]
					delete(openRequests, domain)
					// Add to pending queue with 0 time to force trying on new host
					openRequests[bucket] = OpenRequest{origRequest.provider, origRequest.source, origRequest.numAttempts + 1, time.Time{}}
					openRequestsMutex.Unlock()
					continue
				}
			}

			toLog := fmt.Sprintf("%s,%d\n", domain, time.Now().Unix())

			openRequestsMutex.Lock()
			request := openRequests[domain]
			getFile(request.source, files).f.WriteString(toLog)
			delete(openRequests, domain)
			openRequestsMutex.Unlock()

			for _, host := range acceptedHosts {
				if strings.Contains(domain, host) {
					getFile(strconv.Itoa(statusCode)+host, files).f.WriteString(toLog)
					break
				}
			}
		}
	}
}

func closeAllValidators() {
	for _, v := range validators {
		closeValidator(v)
	}
}

func closeValidator(v *Validator) {
	v.stdIn.Close()
	v.cmd.Process.Kill()
	v.cmd.Wait()
}

func getFile(path string, files map[string]OutputFile) OutputFile {
	if !strings.Contains(path, "..") {
		if val, ok := files[path]; ok {
			fmt.Println("VAL: " + path)

			return val
		}

		f, err := os.OpenFile(
			"./data/"+path+".txt",
			os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err == nil {
			files[path] = OutputFile{f}

			return files[path]
		}
		fmt.Fprintln(os.Stderr, err)

	}
	return OutputFile{nil}
}

func closeAllValidatorsOnSignal(files map[string]OutputFile, prevSeen *bloom.BloomFilter) {
	// Intercept sigint
	sig := make(chan os.Signal, 2)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)

	go func() {
		<-sig
		fmt.Println("Stopping. Closing all validators.")
		closeAllValidators()
		for _, v := range files {
			v.f.Close()
		}

		// Also write to the bloom filter file
		previouslySeenMutex.Lock()
		f, err := os.OpenFile("./bucket_validation/bloom/candidate_set.bloom", os.O_CREATE|os.O_RDWR, 0644)
		if err != nil {
			panic(err)
		}
		defer f.Close()
		w := bufio.NewWriter(f)
		prevSeen.WriteTo(w)
		previouslySeenMutex.Unlock()
		os.Exit(0)
	}()

}

func openFiles() map[string]OutputFile {
	types := map[string]string{
		"200": "public",
		"400": "invalid_bucket",
		"403": "private",
		"404": "no_such_bucket",
		"500": "error",
	}
	files := make(map[string]OutputFile)
	for k, v := range types {
		for _, host := range acceptedHosts {
			f, err := os.OpenFile(
				"./data/validation/"+host+"/"+v+".txt",
				os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
			if err == nil {
				files[k+host] = OutputFile{f}
			} else {
				fmt.Fprintln(os.Stderr, err)
			}
		}
	}
	return files
}

func parseConfig() {
	viper.SetConfigName("bucket_validation/listener-config")
	viper.AddConfigPath(".")
	err := viper.ReadInConfig()
	handleErrorFatal(err)
	err = viper.Unmarshal(&config)
	handleErrorFatal(err)
}

// Clears the job queue by deleting all items
func clearQueue(beanstalkHost string) {
	jobQueue, err := beanstalk.Dial("tcp", beanstalkHost)
	handleError(err)
	for {
		id, _, err := jobQueue.Reserve(5 * time.Second)
		if err != nil {
			if !strings.Contains(err.Error(), "timeout") { // Don't print if it's a timeout
				log.Println("Error reserving job: " + err.Error())
			}
			continue
		}
		err = jobQueue.Delete(id)
		handleError(err)
	}
}

func initiateValidators() {
	validators = make([]*Validator, 0)
	if len(config.SourceIPs) == 0 {
		validators = append(validators, initializeZGrab(config.NumSenders, config.ReadLimitPerHost, ""))
	} else {
		for _, ip := range config.SourceIPs {
			validators = append(validators, initializeZGrab(config.NumSenders, config.ReadLimitPerHost, ip))
		}
	}
}

func initiateValidator(i int) {
	newValidator := initializeZGrab(config.NumSenders, config.ReadLimitPerHost, validators[i].ip)
	validators[i].stdIn = newValidator.stdIn
	validators[i].stdOut = newValidator.stdOut
	validators[i].cmd = newValidator.cmd
}

func loadBloomFilter() *bloom.BloomFilter {
	filter := bloom.NewWithEstimates(300000000, .000001)
	// TODO: Add support for Bloom Filter
	// f, err := os.OpenFile("./bucket_validation/bloom/candidate_set.bloom", os.O_CREATE|os.O_RDWR, 0644)
	// if err != nil {
	// 	panic(err)
	// }
	// defer f.Close()
	// r := bufio.NewReader(f)
	// filter.ReadFrom(r)
	return filter
}

func main() {

	responseChan = make(chan string)
	// The hosts that we automatically try against. For Alibaba, we initially try
	// against one region and get the new region from the response if the bucket exists
	hosts = []string{"s3.amazonaws.com", "storage.googleapis.com", "oss-us-east-1.aliyuncs.com"}
	acceptedHosts = []string{"s3.amazonaws.com", "storage.googleapis.com", "aliyuncs.com"}

	//	clearQueue(config.BeanstalkHost)

	filter := loadBloomFilter()

	parseConfig()
	initiateValidators()

	outputFiles := openFiles()
	closeAllValidatorsOnSignal(outputFiles, filter)
	go delegateRequestJobs(outputFiles, config.BeanstalkHost, filter)
	receiveResponses()
	writeResponses(outputFiles, filter)

}
