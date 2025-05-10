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

# Configuration
STORAGE_TYPE = os.environ.get("STORAGE_TYPE", "s3").lower()  # Default to s3 if not set
client = OpenAI(api_key=os.environ.get("apiKey"))

# Initialize S3 client only if using S3
if STORAGE_TYPE == "s3":
    s3_client = boto3.client('s3',
                           aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
                           aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
                           region_name='ca-central-1')
    s3_bucket = 'html-differentiator'
    LOGS_KEY = "logs/logs.json"

LOCAL_LOGS_PATH = os.path.join("logs", "logs.json")

def ensure_local_storage():
    os.makedirs(os.path.join("logs"), exist_ok=True)
    os.makedirs(os.path.join("html_runs"), exist_ok=True)
    os.makedirs(os.path.join("differences"), exist_ok=True)
    os.makedirs(os.path.join("summarys"), exist_ok=True)
    os.makedirs(os.path.join("raw_diff"), exist_ok=True)
    os.makedirs(os.path.join("master_summary"), exist_ok=True)
    os.makedirs(os.path.join("summarys_chinese"), exist_ok=True)
    os.makedirs(os.path.join("master_summary_chinese"), exist_ok=True)

def save_file_locally(file_path, content):
    """Save file to local storage."""
    full_path = os.path.join(file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

def read_file_locally(file_path):
    """Read file from local storage."""
    full_path = os.path.join(file_path)
    if os.path.exists(full_path):
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def list_local_files(prefix):
    """List files in local storage matching prefix."""
    prefix_parts = prefix.split('/')
    dir_path = os.path.join(*prefix_parts[:-1])
    file_prefix = prefix_parts[-1]
    
    if not os.path.exists(dir_path):
        return []
    
    files = []
    for filename in os.listdir(dir_path):
        if filename.startswith(file_prefix):
            full_path = os.path.join(dir_path, filename)
            files.append({
                'Key': os.path.join(*prefix_parts[:-1], filename),
                'LastModified': datetime.fromtimestamp(os.path.getmtime(full_path))
            })
    
    return files

def delete_local_file(file_path):
    """Delete file from local storage."""
    full_path = os.path.join(file_path)
    if os.path.exists(full_path):
        os.remove(full_path)
        return True
    return False

def save_file(file_path, content):
    """Save file to appropriate storage based on STORAGE_TYPE."""
    if STORAGE_TYPE == "s3":
        s3_client.put_object(Bucket=s3_bucket, Key=file_path, Body=content)
    else:
        save_file_locally(file_path, content)

def read_file(file_path):
    """Read file from appropriate storage based on STORAGE_TYPE."""
    if STORAGE_TYPE == "s3":
        try:
            obj = s3_client.get_object(Bucket=s3_bucket, Key=file_path)
            return obj['Body'].read().decode('utf-8')
        except s3_client.exceptions.NoSuchKey:
            return None
    else:
        return read_file_locally(file_path)

def list_files(prefix):
    """List files matching prefix in appropriate storage."""
    if STORAGE_TYPE == "s3":
        result = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)
        return result.get('Contents', [])
    else:
        return list_local_files(prefix)

def delete_file(file_path):
    """Delete file from appropriate storage."""
    if STORAGE_TYPE == "s3":
        s3_client.delete_object(Bucket=s3_bucket, Key=file_path)
    else:
        delete_local_file(file_path)

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
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
    )

    return completion.choices[0].message.content

def summarize_changes_chinese(diff_text):
    prompt = (
        "Summarize (Explicitly in Chinese) only the differences in the actual textual content (Immigration Related issues only), ignoring any changes in HTML structure, tags, divs, spans, classes, ids, styles, or UI components. "
        "Only focus on changes in visible text that a user would read on the webpage. "
        "Do not mention modifications to code, formatting, or layout. Present the summary in bullet points:\n\n"
        f"{diff_text}"
    )
    completion = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
    )

    return completion.choices[0].message.content

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def get_latest_test_link_file(link):
    prefix = f"html_runs/{link}_"
    files = list_files(prefix)
    if not files:
        return None
    return max(files, key=lambda x: x['LastModified'])['Key']

def cleanup_old_files(prefix, keep=3):
    """Delete old files keeping only the most recent 'keep' number of files."""
    try:
        keep = int(keep)
    except (ValueError, TypeError):
        keep = 3  # default value if conversion fails
    
    files = sorted(list_files(prefix), key=lambda x: x['LastModified'], reverse=True)
    file_keys = [file['Key'] for file in files]
    
    if len(file_keys) <= keep:
        print(f"Found {len(file_keys)} files for prefix {prefix}, keeping all (<= {keep})")
        return
    
    for file_key in file_keys[keep:]:
        delete_file(file_key)
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
    cleanup_old_files(f"differences/{sanitised_link}_", keep=3)
    cleanup_old_files(f"html_runs/{sanitised_link}_", keep=3)
    cleanup_old_files(f"summarys/{sanitised_link}_", keep=3)
    cleanup_old_files(f"raw_diff/{sanitised_link}_", keep=3)

def extract_title(html):
    """Extracts the title of the webpage from the HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string if soup.title else "No Title"
    return title

def log_to_json(link, timestamp, title,chinese_title):
    sanitised_link = remove_slashes(link)

    
    if STORAGE_TYPE == "s3":
        try:
            logs_object = s3_client.get_object(Bucket=s3_bucket, Key=LOGS_KEY)
            logs = json.loads(logs_object['Body'].read().decode('utf-8'))
        except s3_client.exceptions.NoSuchKey:
            logs = []
    else:
        ensure_local_storage()
        logs_path = os.path.join("logs", "logs.json")  # Updated path
        if os.path.exists(logs_path):
            with open(logs_path, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []

    log_entry = next((entry for entry in logs if entry['id'] == sanitised_link), None)
    if log_entry:
        log_entry['last_updated_at'] = timestamp
        log_entry['title'] = title 
        log_entry['title_zh'] = chinese_title
    else:
        logs.append({
            'id': sanitised_link,
            'last_updated_at': timestamp,
            'title': title,
            'title_zh':chinese_title
        })

    if STORAGE_TYPE == "s3":
        s3_client.put_object(Bucket=s3_bucket, Key=LOGS_KEY, Body=json.dumps(logs, indent=4))
    else:
        logs_path = os.path.join("logs", "logs.json")  # Updated path
        with open(logs_path, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=4)

def extract_updated_at(id):
    if STORAGE_TYPE == "s3":
        try:
            logs_object = s3_client.get_object(Bucket=s3_bucket, Key=LOGS_KEY)
            logs = json.loads(logs_object['Body'].read().decode('utf-8'))
        except s3_client.exceptions.NoSuchKey:
            return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    else:
        if not os.path.exists(LOCAL_LOGS_PATH):
            return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        with open(LOCAL_LOGS_PATH, 'r', encoding='utf-8') as f:
            logs = json.load(f)

    if len(logs) == 0:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    for item in logs:
        if item.get('id') == id:
            return item.get("last_updated_at") 
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def load_links_from_json(file_path):
    if STORAGE_TYPE=='s3':
        print("from s3")
        s3 = boto3.client('s3')
    
        try:
            # Get the object from S3
            response = s3.get_object(Bucket='html-differentiator', Key='urls.json')
            
            # Read the file content
            file_content = response['Body'].read().decode('utf-8')
            
            # Parse the JSON content
            links = json.loads(file_content)
            
            return links
        except Exception as e:
            print(f"Error loading JSON from S3: {e}")
            return None
    else:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data

def initiate_cron():
    if STORAGE_TYPE != "s3":
        ensure_local_storage()
    
    links = load_links_from_json("urls.json")
    print(links)
    master_timestamp = get_timestamp()
    master_summary_content = []
    master_summary_content_chinese = []
    
    for key,val in links.items():

        title_url = key
        link = val.get("url")
        sanitised_link = remove_slashes(link=link)
        timestamp = get_timestamp()
        existing_file = get_latest_test_link_file(link=sanitised_link)
        chinese_title = val.get("chinese")
        english_title = val.get("english")
        
        if not existing_file:
            print(f"No existing file found for {link}. Using the link as the baseline.")
            old_html = download_html_from_link(link)
            old_html = clean_html(old_html)
            if not old_html:
                print(f"Failed to download HTML for {link}. Skipping this run.")
                continue
            file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
            save_file(file2_save_path, old_html)
            print(f"Latest HTML for {link} saved to {file2_save_path}")
        else:
            old_html = read_file(existing_file)
        
        latest_html = download_html_from_link(link)
        latest_html = clean_html(latest_html)
        if not latest_html:
            continue
        title = extract_title(latest_html)

        
        print(f"Comparing {existing_file if existing_file else 'new file'} with {link}")
        
        diff_html, raw_diff_html = highlight_differences(old_html, latest_html)

        if not raw_diff_html.strip():
            print(f"No differences found for {link}. Skipping file generation.")
            old_time_stamp = extract_updated_at(id=sanitised_link)
            log_to_json(link, timestamp=old_time_stamp, title=english_title,chinese_title=chinese_title)
            continue
        else:
            diff_filename = f"differences/{sanitised_link}_{timestamp}.html"
            file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
            raw_diff_path = f"raw_diff/{sanitised_link}_{timestamp}.html"
            log_to_json(link, timestamp=datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), title=english_title,chinese_title=chinese_title)

            save_file(file2_save_path, latest_html)
            save_file(diff_filename, diff_html)
            save_file(raw_diff_path, raw_diff_html)

            print(f"Diff for {link} saved to {diff_filename}")
            print(f"Raw diff for {link} saved to {raw_diff_path}")

            summary = summarize_changes(extract_body_content(raw_diff_html))
            summary_save_path = f"summarys/{sanitised_link}_{timestamp}.txt"
            save_file(summary_save_path, summary)

            summary_chinese = summarize_changes_chinese(extract_body_content(raw_diff_html))
            summary_save_path_chinese = f"summarys_chinese/{sanitised_link}_{timestamp}.txt"
            save_file(summary_save_path_chinese, summary_chinese)

            master_summary_content.append(f"------- {link} -------\n{summary}\n")
            master_summary_content_chinese.append(f"------- {link} -------\n{summary_chinese}\n")
            
            prune_old_files(sanitised_link)

    if master_summary_content:
        final_summary = "\n".join(master_summary_content)
        final_summary_chinese = "\n".join(master_summary_content_chinese)
        master_summary_path = f"master_summary/mastersummary_{master_timestamp}.txt"
        master_summary_path_chinese = f"master_summary_chinese/mastersummary_{master_timestamp}.txt"
        save_file(master_summary_path, final_summary)
        save_file(master_summary_path_chinese, final_summary_chinese)
        print(f"Master summary saved at {master_summary_path}")


if STORAGE_TYPE!='s3':
    schedule.every(1).minute.do(initiate_cron)
else:
    schedule.every(24).hours.do(initiate_cron)

if __name__ == "__main__":
    print(f"Starting HTML diff monitoring with {STORAGE_TYPE.upper()} storage. Press Ctrl+C to stop.")
    
    # Run the first batch immediately
    initiate_cron()
    
    while True:
        schedule.run_pending()
        time.sleep(1)