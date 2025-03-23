import boto3
import os
import json

# Initialize the S3 client with environment variables
s3 = boto3.client(
    's3',
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
    region_name='ca-central-1'
)

def fetch_s3_file(bucket_name, file_key):
    try:
        response = s3.get_object(Bucket=bucket_name, Key=file_key)
        content = response['Body'].read().decode('utf-8')  # Read and decode content
        return json.loads(content)  # Parse JSON content
    except Exception as e:
        print(f"Error fetching {file_key}: {e}")
        return None

# Example Usage
bucket_name = "html-differentiator"  # Replace with your bucket name
file_key = "logs/logs.json"

logs_data = fetch_s3_file(bucket_name, file_key)
if logs_data:
    print("Logs Data:", json.dumps(logs_data, indent=4))
else:
    print("Failed to fetch logs.")
