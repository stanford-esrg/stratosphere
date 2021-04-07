#!/bin/bash
shopt -s extglob

# Helper script to gather data from all folders
cat ./data/validation/@(s3.amazonaws.com|storage.googleapis.com|aliyuncs.com|bucket_types)/private.txt > ./final_output/all_platforms_private.txt
sort -u -t, -k1,1 ./final_output/all_platforms_private.txt -o ./final_output/all_platforms_private.txt
cat ./data/validation/@(s3.amazonaws.com|storage.googleapis.com|aliyuncs.com|bucket_types)/public.txt > ./final_output/all_platforms_public.txt
sort -u -t, -k1,1 ./final_output/all_platforms_public.txt -o ./final_output/all_platforms_public.txt
cat ./final_output/all_platforms_public.txt ./final_output/all_platforms_private.txt | sort -u > ./final_output/all_platforms_all.txt

