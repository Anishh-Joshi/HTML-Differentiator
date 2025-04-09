import boto3
import os
import requests
import difflib
import json
from datetime import datetime
from bs4 import BeautifulSoup
import time
import schedule
from openai import OpenAI
from botocore.exceptions import NoCredentialsError

LOGS_KEY = "logs/logs.json" 

# Initialize the S3 client with credentials and region
s3 = boto3.client('s3', aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
                  aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"), region_name='ca-central-1')

# Define the S3 bucket name (you can change this to your own bucket)
s3_bucket = 'html-differentiator'

client = OpenAI(api_key=os.environ.get("apiKey"))

def extract_body_content(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.body if soup.body else soup

def highlight_text_diff(text1, text2):
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
    # Use S3 instead of local file system
    prefix = f"html_runs/{link}_"
    response = s3.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)
    if 'Contents' not in response:
        return None
    latest_file = max(response['Contents'], key=lambda x: x['LastModified'])
    return latest_file['Key']

def cleanup_old_files(prefix, keep=3):
    # List objects in the S3 bucket
    response = s3.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)
    if 'Contents' not in response:
        return
    
    # Sort by LastModified date
    files = sorted(response['Contents'], key=lambda x: x['LastModified'])
    for file in files[:-keep]:
        s3.delete_object(Bucket=s3_bucket, Key=file['Key'])
        print(f"Deleted old file: {file['Key']}")

def download_html_from_link(url):
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
    cleanup_old_files(f"differences/{sanitised_link}_")
    cleanup_old_files(f"html_runs/{sanitised_link}_")
    cleanup_old_files(f"summarys/{sanitised_link}_")
    cleanup_old_files(f"raw_diff/{sanitised_link}_")

def extract_title(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string if soup.title else "No Title"
    return title

def log_to_json(link, timestamp, title):
    sanitised_link = remove_slashes(link)
    
    try:
        # Try to fetch the current logs from S3
        try:
            logs_file = s3.get_object(Bucket=s3_bucket, Key=LOGS_KEY)
            logs = json.loads(logs_file['Body'].read().decode('utf-8'))
        except s3.exceptions.NoSuchKey:
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
        s3.put_object(Bucket=s3_bucket, Key=LOGS_KEY, Body=json.dumps(logs, indent=4))

    except NoCredentialsError:
        print("AWS credentials not found. Please configure your credentials.")
    except Exception as e:
        print(f"Error updating logs in S3: {e}")

def extract_updated_at(id):
    try:
        # Try to fetch the current logs from S3
        logs_file = s3.get_object(Bucket=s3_bucket, Key=LOGS_KEY)
        logs = json.loads(logs_file['Body'].read().decode('utf-8'))

        if len(logs) == 0:
            return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        for item in logs:
            if item.get('id') == id:
                return item.get("last_updated_at")
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    except s3.exceptions.NoSuchKey:
        print(f"Logs file not found in S3 bucket {s3_bucket}.")
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    except NoCredentialsError:
        print("AWS credentials not found. Please configure your credentials.")
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    except Exception as e:
        print(f"Error fetching logs from S3: {e}")
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def upload_to_s3(file_content, s3_path):
    # Upload file to S3
    s3.put_object(Body=file_content, Bucket=s3_bucket, Key=s3_path)
    print(f"Uploaded {s3_path} to S3")

def load_links_from_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return list(data.values())  # Extract URLs from the JSON file


def initiate_cron():
    # List of links to monitor
    links = load_links_from_json("urls.json")
    master_timestamp = get_timestamp()
    master_summary_content = []
    
    for link in links:
        sanitised_link = remove_slashes(link=link)
        timestamp = get_timestamp()
        existing_file = get_latest_test_link_file(link=sanitised_link)

        if not existing_file:
            print(f"No existing file found for {link}. Using the link as the baseline.")
            old_html = download_html_from_link(link)
            if not old_html:
                print(f"Failed to download HTML for {link}. Skipping this run.")
                continue
            # Upload to S3
            file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
            upload_to_s3(old_html, file2_save_path)
            print(f"Latest HTML for {link} uploaded to S3 at {file2_save_path}")
        else:
            # Read the existing file from S3
            response = s3.get_object(Bucket=s3_bucket, Key=existing_file)
            old_html = response['Body'].read().decode('utf-8')

        # Download the latest HTML
        latest_html = download_html_from_link(link)
        title = extract_title(latest_html)
        if not latest_html:
            print(f"Failed to download the latest HTML for {link}. Skipping this run.")
            continue

        print(f"Comparing {existing_file} with {link}")

        diff_html, raw_diff_html = highlight_differences(old_html, latest_html)

        if old_html.strip() == latest_html.strip():
            print(f"No differences found for {link}. Skipping file generation.")
            old_time_stamp = extract_updated_at(id=sanitised_link)
            log_to_json(link, timestamp=old_time_stamp, title=title)
            continue
        else:
            # Upload diff and raw diff files to S3
            diff_filename = f"differences/{sanitised_link}_{timestamp}.html"
            file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
            raw_diff_path = f"raw_diff/{sanitised_link}_{timestamp}.html"
            log_to_json(link, timestamp=datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), title=title)

            upload_to_s3(diff_html, diff_filename)
            upload_to_s3(latest_html, file2_save_path)
            upload_to_s3(raw_diff_html, raw_diff_path)

            # Upload summary to S3
            summary_save_path = f"summarys/{sanitised_link}_{timestamp}.txt"
            summary = summarize_changes(extract_body_content(raw_diff_html))
            upload_to_s3(summary, summary_save_path)
            print(f"Summary for {link} saved to S3 at {summary_save_path}")
            master_summary_content.append(f"------- {link} -------\n{summary}\n")
            if master_summary_content:
                final_summary = "\n".join(master_summary_content)
                master_summary_path = f"master_summary/mastersummary_{master_timestamp}.txt"
                upload_to_s3(final_summary, master_summary_path)
                print(f"Master summary saved to S3 at {master_summary_path}")
            prune_old_files(sanitised_link)

# Schedule the cron job
schedule.every(24).hours.do(initiate_cron)

if __name__ == "__main__":
    print("Starting HTML diff monitoring. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)
