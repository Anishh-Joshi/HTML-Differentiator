import boto3
import os
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
import time
import schedule
import difflib
from openai import OpenAI
import logging
from logging.handlers import TimedRotatingFileHandler

class S3LogHandler(logging.Handler):
    """Custom logging handler that uploads logs to S3"""
    def __init__(self, bucket, key):
        super().__init__()
        self.bucket = bucket
        self.key = key
        self.buffer = []
        
    def emit(self, record):
        try:
            msg = self.format(record)
            self.buffer.append(msg)
            # Upload logs in chunks to avoid too many S3 requests
            if len(self.buffer) >= 10:  # Upload every 10 messages
                self.flush()
        except Exception:
            self.handleError(record)
            
    def flush(self):
        if self.buffer and s3_client:
            try:
                content = "\n".join(self.buffer) + "\n"
                # Check if log file exists
                try:
                    existing = s3_client.get_object(Bucket=self.bucket, Key=self.key)
                    current_content = existing['Body'].read().decode('utf-8')
                    content = current_content + content
                except s3_client.exceptions.NoSuchKey:
                    pass
                    
                s3_client.put_object(
                    Bucket=self.bucket,
                    Key=self.key,
                    Body=content.encode('utf-8')
                )
                self.buffer = []
            except Exception as e:
                print(f"Failed to upload logs to S3: {str(e)}")
                      
# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Configuration for system logs
SYSTEM_LOGS_KEY = "system_logs/system_logs.txt"
LOCAL_SYSTEM_LOGS_PATH = os.path.join("system_logs", "system_logs.txt")
LOG_RETENTION_DAYS = 3


# Configuration
STORAGE_TYPE = os.environ.get("STORAGE_TYPE", "s3").lower()  # Default to s3 if not set
client = OpenAI(api_key=os.environ.get("apiKey"))

# Initialize S3 client only if using S3
if STORAGE_TYPE == "s3":
    try:
        s3_client = boto3.client('s3',
                               aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
                               aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
                               region_name='ca-central-1')
        s3_bucket = 'html-differentiator'
        logger.info("Successfully initialized S3 client")
    except Exception as e:
        logger.error(f"Failed to initialize S3 client: {str(e)}")
        raise

LOGS_KEY = "logs/logs.json"
LOCAL_LOGS_PATH = os.path.join("logs", "logs.json")

# Set up logging handlers
if STORAGE_TYPE == "s3":
    # Create S3 log handler
    s3_log_handler = S3LogHandler(bucket=s3_bucket, key=SYSTEM_LOGS_KEY)
    s3_log_handler.setFormatter(formatter)
    logger.addHandler(s3_log_handler)
else:
    # Ensure local log directory exists
    os.makedirs(os.path.dirname(LOCAL_SYSTEM_LOGS_PATH), exist_ok=True)
    # Create timed rotating file handler for local storage
    file_handler = TimedRotatingFileHandler(
        filename=LOCAL_SYSTEM_LOGS_PATH,
        when='midnight',
        interval=1,
        backupCount=LOG_RETENTION_DAYS
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# Console handler for development
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


def ensure_local_storage():
    """Ensure local storage directories exist."""
    try:
        os.makedirs(os.path.join("logs"), exist_ok=True)
        os.makedirs(os.path.join("system_logs"), exist_ok=True)
        os.makedirs(os.path.join("html_runs"), exist_ok=True)
        os.makedirs(os.path.join("differences"), exist_ok=True)
        os.makedirs(os.path.join("summarys"), exist_ok=True)
        os.makedirs(os.path.join("raw_diff"), exist_ok=True)
        os.makedirs(os.path.join("master_summary"), exist_ok=True)
        os.makedirs(os.path.join("summarys_chinese"), exist_ok=True)
        os.makedirs(os.path.join("master_summary_chinese"), exist_ok=True)
        logger.info("Local storage directories verified/created")
    except Exception as e:
        logger.error(f"Failed to create local storage directories: {str(e)}")
        raise

def save_file_locally(file_path, content):
    """Save file to local storage."""
    try:
        full_path = os.path.join(file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Successfully saved file locally: {full_path}")
    except Exception as e:
        logger.error(f"Failed to save file locally {file_path}: {str(e)}")
        raise

def read_file_locally(file_path):
    """Read file from local storage."""
    try:
        full_path = os.path.join(file_path)
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"Successfully read local file: {full_path}")
            return content
        logger.warning(f"Local file not found: {full_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to read local file {file_path}: {str(e)}")
        raise

def list_local_files(prefix):
    """List files in local storage matching prefix."""
    try:
        prefix_parts = prefix.split('/')
        dir_path = os.path.join(*prefix_parts[:-1])
        file_prefix = prefix_parts[-1]
        
        if not os.path.exists(dir_path):
            logger.warning(f"Local directory not found: {dir_path}")
            return []
        
        files = []
        for filename in os.listdir(dir_path):
            if filename.startswith(file_prefix):
                full_path = os.path.join(dir_path, filename)
                files.append({
                    'Key': os.path.join(*prefix_parts[:-1], filename),
                    'LastModified': datetime.fromtimestamp(os.path.getmtime(full_path))
                })
        
        logger.info(f"Found {len(files)} local files matching prefix {prefix}")
        return files
    except Exception as e:
        logger.error(f"Failed to list local files with prefix {prefix}: {str(e)}")
        raise

def delete_local_file(file_path):
    """Delete file from local storage."""
    try:
        full_path = os.path.join(file_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            logger.info(f"Successfully deleted local file: {full_path}")
            return True
        logger.warning(f"Local file not found for deletion: {full_path}")
        return False
    except Exception as e:
        logger.error(f"Failed to delete local file {file_path}: {str(e)}")
        raise

def save_file(file_path, content):
    """Save file to appropriate storage based on STORAGE_TYPE."""
    try:
        if STORAGE_TYPE == "s3":
            s3_client.put_object(Bucket=s3_bucket, Key=file_path, Body=content)
            logger.info(f"Successfully saved file to S3: {file_path}")
        else:
            save_file_locally(file_path, content)
    except Exception as e:
        logger.error(f"Failed to save file {file_path}: {str(e)}")
        raise

def read_file(file_path):
    """Read file from appropriate storage based on STORAGE_TYPE."""
    try:
        if STORAGE_TYPE == "s3":
            try:
                obj = s3_client.get_object(Bucket=s3_bucket, Key=file_path)
                content = obj['Body'].read().decode('utf-8')
                logger.info(f"Successfully read file from S3: {file_path}")
                return content
            except s3_client.exceptions.NoSuchKey:
                logger.warning(f"S3 file not found: {file_path}")
                return None
        else:
            return read_file_locally(file_path)
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {str(e)}")
        raise

def list_files(prefix):
    """List files matching prefix in appropriate storage."""
    try:
        if STORAGE_TYPE == "s3":
            result = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)
            contents = result.get('Contents', [])
            logger.info(f"Found {len(contents)} files in S3 matching prefix {prefix}")
            return contents
        else:
            return list_local_files(prefix)
    except Exception as e:
        logger.error(f"Failed to list files with prefix {prefix}: {str(e)}")
        raise

def delete_file(file_path):
    """Delete file from appropriate storage."""
    try:
        if STORAGE_TYPE == "s3":
            s3_client.delete_object(Bucket=s3_bucket, Key=file_path)
            logger.info(f"Successfully deleted file from S3: {file_path}")
        else:
            delete_local_file(file_path)
    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {str(e)}")
        raise

def clean_html(content):
    """Clean HTML content by removing scripts, styles, etc."""
    try:
        if not content:
            logger.warning("Empty content provided to clean_html")
            return None
        soup = BeautifulSoup(content, 'html.parser')
        for tag in soup(['script', 'style', 'noscript', 'meta']):
            tag.decompose()
        logger.info("Successfully cleaned HTML content")
        return str(soup)
    except Exception as e:
        logger.error(f"Failed to clean HTML: {str(e)}")
        raise

def extract_body_content(html):
    """Extract body content from HTML."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.body if soup.body else soup
        logger.info("Successfully extracted body content from HTML")
        return body
    except Exception as e:
        logger.error(f"Failed to extract body content: {str(e)}")
        raise

def highlight_text_diff(text1, text2):
    """Generates highlighted HTML diff for inline text changes."""
    try:
        diff = difflib.ndiff(text1.split(), text2.split())
        highlighted_text = []
        
        for word in diff:
            if word.startswith("- "):
                highlighted_text.append(f'<span style="color: red; text-decoration: line-through;">{word[2:]}</span>')
            elif word.startswith("+ "):
                highlighted_text.append(f'<span style="color: green;">{word[2:]}</span>')
            else:
                highlighted_text.append(word)
        
        logger.info("Successfully generated text diff highlights")
        return " ".join(highlighted_text)
    except Exception as e:
        logger.error(f"Failed to highlight text differences: {str(e)}")
        raise

def highlight_differences(old_html, latest_html):
    """Highlight differences between two HTML documents."""
    try:
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

        logger.info("Successfully highlighted HTML differences")
        return "\n".join(modified_html), "\n".join(raw_diff)
    except Exception as e:
        logger.error(f"Failed to highlight differences: {str(e)}")
        raise

def summarize_changes(diff_text):
    """Generate summary of changes using OpenAI."""
    try:
        prompt = (
            "Summarize only the differences in the actual textual content (Immigration Related issues only), ignoring any changes in HTML structure, tags, divs, spans, classes, ids, styles, or UI components. "
            "Only focus on changes in visible text that a user would read on the webpage. "
            "Do not mention modifications to code, formatting, or layout. Present the summary in bullet points:\n\n"
            f"{diff_text}"
        )
        logger.info("Requesting summary from OpenAI...")
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
        )
        summary = completion.choices[0].message.content
        logger.info("Successfully generated summary from OpenAI")
        return summary
    except Exception as e:
        logger.error(f"Failed to generate summary: {str(e)}")
        raise

def summarize_changes_chinese(diff_text):
    """Generate Chinese summary of changes using OpenAI."""
    try:
        prompt = (
            "Summarize (Explicitly in Chinese) only the differences in the actual textual content (Immigration Related issues only), ignoring any changes in HTML structure, tags, divs, spans, classes, ids, styles, or UI components. "
            "Only focus on changes in visible text that a user would read on the webpage. "
            "Do not mention modifications to code, formatting, or layout. Present the summary in bullet points:\n\n"
            f"{diff_text}"
        )
        logger.info("Requesting Chinese summary from OpenAI...")
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
        )
        summary = completion.choices[0].message.content
        logger.info("Successfully generated Chinese summary from OpenAI")
        return summary
    except Exception as e:
        logger.error(f"Failed to generate Chinese summary: {str(e)}")
        raise

def get_timestamp():
    """Get current timestamp in formatted string."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logger.debug(f"Generated timestamp: {timestamp}")
    return timestamp

def get_latest_test_link_file(link):
    """Get the latest test file for a given link."""
    try:
        sanitised_link = remove_slashes(link)
        prefix = f"html_runs/{sanitised_link}_"
        files = list_files(prefix)
        if not files:
            logger.warning(f"No existing files found for link: {link}")
            return None
        latest_file = max(files, key=lambda x: x['LastModified'])['Key']
        logger.info(f"Found latest file for {link}: {latest_file}")
        return latest_file
    except Exception as e:
        logger.error(f"Failed to get latest test link file for {link}: {str(e)}")
        raise

def cleanup_old_files(prefix, keep=3):
    """Delete old files keeping only the most recent 'keep' number of files."""
    try:
        keep = int(keep)
        logger.info(f"Cleaning up old files with prefix {prefix}, keeping {keep} most recent")
        
        files = sorted(list_files(prefix), key=lambda x: x['LastModified'], reverse=True)
        file_keys = [file['Key'] for file in files]
        
        if len(file_keys) <= keep:
            logger.info(f"Found {len(file_keys)} files for prefix {prefix}, keeping all (<= {keep})")
            return
        
        for file_key in file_keys[keep:]:
            delete_file(file_key)
            logger.info(f"Deleted old file: {file_key}")
    except Exception as e:
        logger.error(f"Failed to clean up old files with prefix {prefix}: {str(e)}")
        raise

def download_html_from_link(url):
    """Download HTML content from the provided link."""
    try:
        logger.info(f"Downloading HTML from {url}")
        response = requests.get(url)
        response.raise_for_status()
        logger.info(f"Successfully downloaded HTML from {url}")
        return response.text
    except requests.RequestException as e:
        logger.error(f"Failed to download HTML from {url}: {str(e)}")
        return None

def remove_slashes(link):
    """Remove slashes from a link to create a filesystem-safe string."""
    sanitised = link.replace("/", "")
    logger.debug(f"Sanitised link {link} to {sanitised}")
    return sanitised

def prune_old_files(sanitised_link):
    """Prune old files for a given sanitised link."""
    try:
        logger.info(f"Pruning old files for {sanitised_link}")
        cleanup_old_files(f"differences/{sanitised_link}_", keep=3)
        cleanup_old_files(f"html_runs/{sanitised_link}_", keep=3)
        cleanup_old_files(f"summarys/{sanitised_link}_", keep=3)
        cleanup_old_files(f"raw_diff/{sanitised_link}_", keep=3)
        cleanup_old_files(f"summarys_chinese/{sanitised_link}_", keep=3)
    except Exception as e:
        logger.error(f"Failed to prune old files for {sanitised_link}: {str(e)}")
        raise

def extract_title(html):
    """Extracts the title of the webpage from the HTML content."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string if soup.title else "No Title"
        logger.info(f"Extracted title: {title}")
        return title
    except Exception as e:
        logger.error(f"Failed to extract title from HTML: {str(e)}")
        return "No Title"

def log_to_json(link, timestamp, title, chinese_title):
    """Log activity to JSON file."""
    try:
        sanitised_link = remove_slashes(link)
        logger.info(f"Logging activity for {link} at {timestamp}")
        
        if STORAGE_TYPE == "s3":
            try:
                logs_object = s3_client.get_object(Bucket=s3_bucket, Key=LOGS_KEY)
                logs = json.loads(logs_object['Body'].read().decode('utf-8'))
                logger.debug("Loaded logs from S3")
            except s3_client.exceptions.NoSuchKey:
                logs = []
                logger.warning("No existing logs found on S3, initializing new log")
        else:
            ensure_local_storage()
            logs_path = os.path.join("logs", "logs.json")
            if os.path.exists(logs_path):
                with open(logs_path, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                logger.debug("Loaded logs from local storage")
            else:
                logs = []
                logger.warning("No existing logs found locally, initializing new log")

        log_entry = next((entry for entry in logs if entry['id'] == sanitised_link), None)
        if log_entry:
            log_entry['last_updated_at'] = timestamp
            log_entry['title'] = title
            log_entry['title_zh'] = chinese_title
            logger.debug(f"Updated existing log entry for {sanitised_link}")
        else:
            logs.append({
                'id': sanitised_link,
                'last_updated_at': timestamp,
                'title': title,
                'title_zh': chinese_title
            })
            logger.debug(f"Created new log entry for {sanitised_link}")

        if STORAGE_TYPE == "s3":
            s3_client.put_object(Bucket=s3_bucket, Key=LOGS_KEY, Body=json.dumps(logs, indent=4))
            logger.info("Saved logs to S3")
        else:
            logs_path = os.path.join("logs", "logs.json")
            with open(logs_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=4)
            logger.info("Saved logs to local storage")
    except Exception as e:
        logger.error(f"Failed to log activity to JSON: {str(e)}")
        raise

def extract_updated_at(id):
    """Extract last updated timestamp for a given ID."""
    try:
        if STORAGE_TYPE == "s3":
            try:
                logs_object = s3_client.get_object(Bucket=s3_bucket, Key=LOGS_KEY)
                logs = json.loads(logs_object['Body'].read().decode('utf-8'))
                logger.debug("Loaded logs from S3 for timestamp extraction")
            except s3_client.exceptions.NoSuchKey:
                logger.warning("No logs found on S3, using current timestamp")
                return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        else:
            if not os.path.exists(LOCAL_LOGS_PATH):
                logger.warning("No local logs found, using current timestamp")
                return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            with open(LOCAL_LOGS_PATH, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            logger.debug("Loaded logs from local storage for timestamp extraction")

        if len(logs) == 0:
            logger.warning("Empty logs, using current timestamp")
            return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        for item in logs:
            if item.get('id') == id:
                timestamp = item.get("last_updated_at")
                logger.info(f"Found timestamp for {id}: {timestamp}")
                return timestamp
        
        logger.warning(f"No timestamp found for {id}, using current timestamp")
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    except Exception as e:
        logger.error(f"Failed to extract timestamp for {id}: {str(e)}")
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def load_links_from_json(file_path):
    """Load URLs to monitor from JSON file."""
    try:
        logger.info(f"Loading links from {file_path}")
        
        if STORAGE_TYPE == 's3':
            logger.debug("Loading from S3")
            s3 = boto3.client('s3')
            try:
                response = s3.get_object(Bucket='html-differentiator', Key='urls.json')
                file_content = response['Body'].read().decode('utf-8')
                links = json.loads(file_content)
                logger.info(f"Successfully loaded {len(links)} links from S3")
                return links
            except Exception as e:
                logger.error(f"Error loading JSON from S3: {str(e)}")
                return None
        else:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            logger.info(f"Successfully loaded {len(data)} links from local file")
            return data
    except Exception as e:
        logger.error(f"Failed to load links from JSON: {str(e)}")
        raise

def initiate_cron():
    try:
        logger.info("Initiating cron job")
        
        if STORAGE_TYPE != "s3":
            ensure_local_storage()
        
        links = load_links_from_json("urls.json")
        if not links:
            logger.error("No links loaded, exiting")
            return
            
        logger.info(f"Processing {len(links)} links")
        master_timestamp = get_timestamp()
        master_summary_content = []
        master_summary_content_chinese = []
        
        for key, val in links.items():
            try:
                link = val.get("url")
                sanitised_link = remove_slashes(link=link)
                timestamp = get_timestamp()
                existing_file = get_latest_test_link_file(link=sanitised_link)
                chinese_title = val.get("chinese")
                english_title = val.get("english")
                
                logger.info(f"Processing link: {link}")
                
                if not existing_file:
                    logger.info(f"No existing file found for {link}. Using the link as the baseline.")
                    old_html = download_html_from_link(link)
                    old_html = clean_html(old_html)
                    if not old_html:
                        logger.error(f"Failed to download HTML for {link}. Skipping this run.")
                        continue
                    file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
                    save_file(file2_save_path, old_html)
                    logger.info(f"Latest HTML for {link} saved to {file2_save_path}")
                else:
                    old_html = read_file(existing_file)
                    logger.debug(f"Using existing HTML file: {existing_file}")
                
                latest_html = download_html_from_link(link)
                latest_html = clean_html(latest_html)
                if not latest_html:
                    logger.error(f"Failed to download latest HTML for {link}. Skipping.")
                    continue

                logger.info(f"Comparing {existing_file if existing_file else 'new file'} with {link}")
                
                diff_html, raw_diff_html = highlight_differences(old_html, latest_html)

                if not raw_diff_html.strip():
                    logger.info(f"No differences found for {link}. Skipping file generation.")
                    old_time_stamp = extract_updated_at(id=sanitised_link)
                    log_to_json(link, timestamp=old_time_stamp, title=english_title, chinese_title=chinese_title)
                    continue
                else:
                    diff_filename = f"differences/{sanitised_link}_{timestamp}.html"
                    file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
                    raw_diff_path = f"raw_diff/{sanitised_link}_{timestamp}.html"
                    
                    log_to_json(link, timestamp=datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), 
                              title=english_title, chinese_title=chinese_title)

                    save_file(file2_save_path, latest_html)
                    save_file(diff_filename, diff_html)
                    save_file(raw_diff_path, raw_diff_html)

                    logger.info(f"Diff for {link} saved to {diff_filename}")
                    logger.info(f"Raw diff for {link} saved to {raw_diff_path}")

                    summary = summarize_changes(extract_body_content(raw_diff_html))
                    summary_save_path = f"summarys/{sanitised_link}_{timestamp}.txt"
                    save_file(summary_save_path, summary)

                    summary_chinese = summarize_changes_chinese(extract_body_content(raw_diff_html))
                    summary_save_path_chinese = f"summarys_chinese/{sanitised_link}_{timestamp}.txt"
                    save_file(summary_save_path_chinese, summary_chinese)

                    master_summary_content.append(f"------- {link} -------\n{summary}\n")
                    master_summary_content_chinese.append(f"------- {link} -------\n{summary_chinese}\n")
                    
                    prune_old_files(sanitised_link)
                    
            except Exception as e:
                logger.error(f"Error processing link {link}: {str(e)}")
                continue

        if master_summary_content:
            final_summary = "\n".join(master_summary_content)
            final_summary_chinese = "\n".join(master_summary_content_chinese)
            master_summary_path = f"master_summary/mastersummary_{master_timestamp}.txt"
            master_summary_path_chinese = f"master_summary_chinese/mastersummary_{master_timestamp}.txt"
            
            save_file(master_summary_path, final_summary)
            save_file(master_summary_path_chinese, final_summary_chinese)
            
            logger.info(f"Master summary saved at {master_summary_path}")
            logger.info(f"Chinese master summary saved at {master_summary_path_chinese}")
            
    except Exception as e:
        logger.error(f"Failed to complete cron job: {str(e)}")
        raise

# Set up scheduling
if STORAGE_TYPE != 's3':
    schedule.every(1).minute.do(initiate_cron)
    logger.info("Set up local schedule (1 minute interval)")
else:
    schedule.every(24).hours.do(initiate_cron)
    logger.info("Set up S3 schedule (24 hour interval)")

if __name__ == "__main__":
    logger.info(f"Starting HTML diff monitoring with {STORAGE_TYPE.upper()} storage. Press Ctrl+C to stop.")
    
    try:
        # Run the first batch immediately
        initiate_cron()
        
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {str(e)}")