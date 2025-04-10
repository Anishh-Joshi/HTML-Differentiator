import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
import os
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
import time
import schedule
import glob
import difflib
from openai import OpenAI
client = OpenAI(api_key=os.environ.get("apiKey"))

# AWS S3 client initialization
# Initialize the S3 client with credentials and region
s3_client = boto3.client('s3', aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
                  aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"), region_name='ca-central-1')

s3_bucket = 'html-differentiator'
LOGS_KEY = "logs/logs.json"

def clean_html(content):
    if not content:
        return None
    soup = BeautifulSoup(content, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'meta']):
        tag.decompose()
    return str(soup)

def extract_body_content(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.body if soup.body else soup

def highlight_text_diff(text1, text2):
    """Generates highlighted HTML diff for inline text changes."""
    diff = difflib.ndiff(text1.split(), text2.split())
    highlighted_text = []
    
    for word in diff:
        if word.startswith("- "):
            highlighted_text.append(f'<span style="color: red; text-decoration: line-through;">{word[2:]}</span>')
        elif word.startswith("+ "):
            highlighted_text.append(f'<span style="color: green;">{word[2:]}</span>')
        else:
            highlighted_text.append(word)
    
    return " ".join(highlighted_text)

def highlight_differences(old_html, latest_html):
    old_soup = BeautifulSoup(old_html, "html.parser")
    latest_soup = BeautifulSoup(latest_html, "html.parser")

    diff = difflib.ndiff(old_soup.prettify().splitlines(), latest_soup.prettify().splitlines())

    modified_html = []
    raw_diff = []
    for line in diff:
        if line.startswith("+ "):
            modified_html.append(f'<ins style="background-color: lightgreen;">{line[2:]}</ins>')
            raw_diff.append(f'<ins style="background-color: lightgreen;">{line[2:]}</ins>')
        elif line.startswith("- "):
            modified_html.append(f'<del style="background-color: lightcoral;">{line[2:]}</del>')
            raw_diff.append(f'<del style="background-color: lightcoral;">{line[2:]}</del>')
        else:
            modified_html.append(line[2:])

    return "\n".join(modified_html), "\n".join(raw_diff)

def summarize_changes(diff_text):
    prompt = (
        "Summarize only the differences in the actual textual content (Immigration Related issues only), ignoring any changes in HTML structure, tags, divs, spans, classes, ids, styles, or UI components. "
        "Only focus on changes in visible text that a user would read on the webpage. "
        "Do not mention modifications to code, formatting, or layout. Present the summary in bullet points:\n\n"
        f"{diff_text}"
    )
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    return completion.choices[0].message.content

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def get_latest_test_link_file(link):
    # Use S3 to get the latest file
    files = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=f"html_runs/{link}_")
    if 'Contents' not in files:
        return None
    return max(files['Contents'], key=lambda x: x['LastModified'])['Key']


def cleanup_old_files(prefix, keep=3):
    """Delete old files keeping only the most recent 'keep' number of files."""
    try:
        keep = int(keep)
    except (ValueError, TypeError):
        keep = 3  # default value if conversion fails
    
    try:
        response = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)
        if 'Contents' not in response:
            print(f"No files found with prefix: {prefix}")
            return
        
        # Sort by LastModified date (newest first)
        files = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
        file_keys = [file['Key'] for file in files]
        
        if len(file_keys) <= keep:
            print(f"Found {len(file_keys)} files for prefix {prefix}, keeping all (<= {keep})")
            return
        
        # Delete all except the newest 'keep' files
        for file_key in file_keys[keep:]:
            s3_client.delete_object(Bucket=s3_bucket, Key=file_key)
            print(f"Deleted old file: {file_key}")
            
    except Exception as e:
        print(f"Error cleaning up files with prefix {prefix}: {str(e)}")
    
    files = sorted(response['Contents'], key=lambda x: x['LastModified'])
    file_keys = [file['Key'] for file in files]
    
    if len(file_keys) <= keep:
        print(f"Found {len(file_keys)} files, which is less than or equal to keep count ({keep}). No files deleted.")
        return
    
    for file_key in file_keys[:-keep]:
        s3_client.delete_object(Bucket=s3_bucket, Key=file_key)
        print(f"Deleted old file: {file_key}")


def download_html_from_link(url):
    """Download HTML content from the provided link."""
    try:
        response = requests.get(url)
        response.raise_for_status() 
        return response.text
    except requests.RequestException as e:
        print(f"Failed to download HTML from {url}: {e}")
        return None

def remove_slashes(link):
    return link.replace("/", "")

def prune_old_files(sanitised_link):
    # For differences files
    cleanup_old_files(f"differences/{sanitised_link}_", keep=3)
    # For html_runs files
    cleanup_old_files(f"html_runs/{sanitised_link}_", keep=3)
    # For summary files
    cleanup_old_files(f"summarys/{sanitised_link}_", keep=3)
    # For raw_diff files
    cleanup_old_files(f"raw_diff/{sanitised_link}_", keep=3)


def extract_title(html):
    """Extracts the title of the webpage from the HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string if soup.title else "No Title"
    return title


def log_to_json(link, timestamp, title):
    sanitised_link = remove_slashes(link)
    
    try:
        # Fetch current logs from S3
        logs_object = s3_client.get_object(Bucket=s3_bucket, Key=LOGS_KEY)
        logs = json.loads(logs_object['Body'].read().decode('utf-8'))
    except s3_client.exceptions.NoSuchKey:
        logs = []

    # Check if the link already exists in the logs
    log_entry = next((entry for entry in logs if entry['id'] == sanitised_link), None)
    if log_entry:
        log_entry['last_updated_at'] = timestamp
        log_entry['title'] = title 
    else:
        logs.append({
            'id': sanitised_link,
            'last_updated_at': timestamp,
            'title': title  
        })

    # Save the updated logs back to S3
    s3_client.put_object(Bucket=s3_bucket, Key=LOGS_KEY, Body=json.dumps(logs, indent=4))

def extract_updated_at(id):
    try:
        # Fetch logs from S3
        logs_object = s3_client.get_object(Bucket=s3_bucket, Key=LOGS_KEY)
        logs = json.loads(logs_object['Body'].read().decode('utf-8'))
    except s3_client.exceptions.NoSuchKey:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if len(logs) == 0:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    for item in logs:
        if item.get('id') == id:
            return item.get("last_updated_at") 
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def load_links_from_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return list(data.values())  # Extract URLs from the JSON file

def initiate_cron():
    links = load_links_from_json("urls.json")
    master_timestamp = get_timestamp()
    master_summary_content = []
    
    for link in links:
        sanitised_link = remove_slashes(link=link)
        timestamp = get_timestamp()
        existing_file = get_latest_test_link_file(link=sanitised_link)
        
        # If no existing file, use the link itself
        if not existing_file:
            print(f"No existing file found for {link}. Using the link as the baseline.")
            old_html = download_html_from_link(link)
            old_html = clean_html(old_html)
            if not old_html:
                print(f"Failed to download HTML for {link}. Skipping this run.")
                continue
            file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
            
            # Upload to S3
            s3_client.put_object(Bucket=s3_bucket, Key=file2_save_path, Body=old_html)
            print(f"Latest HTML for {link} saved to {file2_save_path}")
        else:
            # Fetch the existing file from S3
            existing_object = s3_client.get_object(Bucket=s3_bucket, Key=existing_file)
            old_html = existing_object['Body'].read().decode('utf-8')
        
        # Download the latest HTML
        latest_html = download_html_from_link(link)
        latest_html = clean_html(latest_html)
        if not latest_html:
            continue
        title = extract_title(latest_html)
        
        print(f"Comparing {existing_file} with {link}")
        
        diff_html, raw_diff_html = highlight_differences(old_html, latest_html)

        if not raw_diff_html.strip():
            print(f"No differences found for {link}. Skipping file generation.")
            old_time_stamp = extract_updated_at(id=sanitised_link)
            log_to_json(link, timestamp=old_time_stamp, title=title)
            continue
        else:
            diff_filename = f"differences/{sanitised_link}_{timestamp}.html"
            file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
            raw_diff_path = f"raw_diff/{sanitised_link}_{timestamp}.html"
            log_to_json(link, timestamp=datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), title=title)

            # Upload to S3
            s3_client.put_object(Bucket=s3_bucket, Key=file2_save_path, Body=latest_html)
            s3_client.put_object(Bucket=s3_bucket, Key=diff_filename, Body=diff_html)
            s3_client.put_object(Bucket=s3_bucket, Key=raw_diff_path, Body=raw_diff_html)

            print(f"Diff for {link} saved to {diff_filename}")
            print(f"Raw diff for {link} saved to {raw_diff_path}")

            summary_save_path = f"summarys/{sanitised_link}_{timestamp}.txt"
            summary = summarize_changes(extract_body_content(raw_diff_html))
            s3_client.put_object(Body=summary, Bucket=s3_bucket, Key=summary_save_path)

            master_summary_content.append(f"------- {link} -------\n{summary}\n")
            if master_summary_content:
                final_summary = "\n".join(master_summary_content)
                master_summary_path = f"master_summary/mastersummary_{master_timestamp}.txt"
                s3_client.put_object(Body=final_summary, Bucket=s3_bucket, Key=master_summary_path)
                print(f"Master summary saved to S3 at {master_summary_path}")

            prune_old_files(sanitised_link)

# Schedule the cron job
schedule.every(24).hours.do(initiate_cron)  # Now it will run every 24 hours

if __name__ == "__main__":
    print("Starting HTML diff monitoring. Press Ctrl+C to stop.")
    
    # Run the first batch immediately
    initiate_cron()
    
    while True:
        schedule.run_pending()
        time.sleep(1)
