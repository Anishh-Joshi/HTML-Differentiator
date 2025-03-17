import boto3
import os
from botocore.exceptions import ClientError

# Initialize the S3 client with credentials and region
s3 = boto3.client('s3', aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
                  aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"), region_name='ca-central-1')

# Define the bucket name
bucket_name = 'html-differentiator'

def list_files_in_bucket(bucket_name, prefix=''):
    try:
        # List the files in the specified bucket with the given prefix
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        
        if 'Contents' in response:
            print(f"Files in bucket '{bucket_name}':")
            for file in response['Contents']:
                print(file['Key'])
        else:
            print(f"No files found in bucket '{bucket_name}'.")
        
        # Check if there are more files (paging)
        while response.get('IsTruncated'):  # If there are more files to retrieve
            next_token = response.get('NextContinuationToken')
            response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, ContinuationToken=next_token)
            for file in response['Contents']:
                print(file['Key'])
    
    except ClientError as e:
        print(f"Error accessing bucket '{bucket_name}': {e}")

# Example usage:
list_files_in_bucket(bucket_name)
