import boto3
from botocore.exceptions import ClientError
import os

# Initialize the S3 client
s3 = boto3.client('s3', 
                  aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
                  aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
                  region_name="ca-central-1")

bucket_name = "html-differentiator" 

def delete_files_in_s3_folder(prefix):
    """Deletes all files in the S3 folder (prefix)."""
    try:
        # List objects with the given prefix
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        
        # If files exist, delete them
        if 'Contents' in response:
            for obj in response['Contents']:
                s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
                print(f"Deleted file: {obj['Key']}")
        else:
            print(f"No files found with prefix {prefix}.")
    
    except ClientError as e:
        print(f"Error accessing S3 or deleting files with prefix {prefix}: {e}")

def delete_folders():
    prefixes = [
        "html_runs/",
        "logs/",
        "differences/",
        "raw_diff/",
        "summarys/"
    ]
    
    for prefix in prefixes:
        delete_files_in_s3_folder(prefix)

if __name__ == "__main__":
    delete_folders()
