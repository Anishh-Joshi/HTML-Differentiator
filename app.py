from openai import OpenAI
import difflib
import os, requests, json
from datetime import datetime
from bs4 import BeautifulSoup
import time
import schedule
import glob

client = OpenAI(api_key=os.environ.get("apiKey"))

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
    files = glob.glob(f"html_runs/{link}_*.html")
    if not files:
        return None
    return max(files, key=os.path.getctime)

def cleanup_old_files(directory, prefix, keep=3):
    files = glob.glob(f"{directory}/{prefix}*")
    if not files:
        return
    
    files.sort(key=os.path.getctime)
    for file in files[:-keep]:
        os.remove(file)
        print(f"Deleted old file: {file}")


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
    cleanup_old_files("differences", f"{sanitised_link}_")
    cleanup_old_files("html_runs", f"{sanitised_link}_")
    cleanup_old_files("summarys", f"{sanitised_link}_")
    cleanup_old_files("raw_diff", f"{sanitised_link}_")


def extract_title(html):
    """Extracts the title of the webpage from the HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string if soup.title else "No Title"
    return title


def log_to_json(link, timestamp, title):
    sanitised_link = remove_slashes(link)
    
    # Load existing logs from logs.json
    if os.path.exists("logs/logs.json"):
        with open("logs/logs.json", "r", encoding="utf-8") as log_file:
            logs = json.load(log_file)
    else:
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
    
    # Save the updated logs back to the JSON file
    with open("logs/logs.json", "w", encoding="utf-8") as log_file:
        json.dump(logs, log_file, indent=4)


def extract_updated_at(id):
    if os.path.exists("logs/logs.json"):
        with open("logs/logs.json", "r", encoding="utf-8") as log_file:
            logs = json.load(log_file)
    else:
        logs = []

    if len(logs) == 0:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    for item in logs:
        if item.get('id') == id:
            return item.get("last_updated_at") 
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def initiate_cron():
    os.makedirs("html_runs", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("differences", exist_ok=True)
    os.makedirs("raw_diff", exist_ok=True)
    os.makedirs("summarys", exist_ok=True)
    
    # List of links to monitor
    links = [
        "https://golden-platinum-zephyr.glitch.me",
        "https://docs.aws.amazon.com/lambda/latest/dg/python-image.html",
    ]
    
    for link in links:
        sanitised_link = remove_slashes(link=link)
        timestamp = get_timestamp()
        existing_file = get_latest_test_link_file(link=sanitised_link)
        
        # If no existing file, use the link itself
        if not existing_file:
            print(f"No existing file found for {link}. Using the link as the baseline.")
            old_html = download_html_from_link(link)
            if not old_html:
                print(f"Failed to download HTML for {link}. Skipping this run.")
                continue
            file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
            
            with open(file2_save_path, "w", encoding="utf-8") as file2_save:
                print("Saving HTML...")
                file2_save.write(old_html)
            print(f"Latest HTML for {link} saved to {file2_save_path}")
        else:
            # Read the existing file
            with open(existing_file, 'r', encoding='utf-8') as f1:
                old_html = f1.read()
        
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
            diff_filename = f"differences/{sanitised_link}_{timestamp}.html"
            file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
            raw_diff_path = f"raw_diff/{sanitised_link}_{timestamp}.html"
            log_to_json(link, timestamp=datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), title=title)

            with open(diff_filename, "w", encoding="utf-8") as diff_file:
                diff_file.write(diff_html)
            print(f"Diff for {link} saved to {diff_filename}")

            with open(file2_save_path, "w", encoding="utf-8") as file2_save:
                file2_save.write(latest_html)
            print(f"File2 for {link} saved to {file2_save_path}")

            with open(raw_diff_path, "w", encoding="utf-8") as raw_diff_file:
                raw_diff_file.write(raw_diff_html)
            print(f"Raw diff for {link} saved to {raw_diff_path}")

            summary_save_path = f"summarys/{sanitised_link}_{timestamp}.txt"
            summary = summarize_changes(extract_body_content(raw_diff_html))
            with open(summary_save_path, "w", encoding="utf-8") as summaryFile:
                summaryFile.write(summary)
            print(f"Summary for {link} saved to {summary_save_path}")
            
            prune_old_files(sanitised_link)

# Schedule the cron job
schedule.every(10).seconds.do(initiate_cron)

if __name__ == "__main__":
    print("Starting HTML diff monitoring. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)