from openai import OpenAI
import difflib
import os,requests
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
        response.raise_for_status()  # Raise an error for bad status codes
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

def initate_cron():
    os.makedirs("html_runs", exist_ok=True)
    os.makedirs("differences", exist_ok=True)
    os.makedirs("raw_diff", exist_ok=True)
    os.makedirs("summarys", exist_ok=True)
    timestamp = get_timestamp()
    
    link = "https://golden-platinum-zephyr.glitch.me"
    sanitised_link  = remove_slashes(link=link)

    existing_file = get_latest_test_link_file(link=sanitised_link)
    
    # If no existing file, use the link itself
    if not existing_file:
        print("No existing file found. Using the link as the baseline.")
        old_html = download_html_from_link(link)
        if not old_html:
            print("Failed to download HTML for comparison. Skipping this run.")
            return
        file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
        
        with open(file2_save_path, "w", encoding="utf-8") as file2_save:
            file2_save.write(old_html)
        print(f"Latest HTML saved to {file2_save_path}")
    else:
        # Read the existing file
        with open(existing_file, 'r', encoding='utf-8') as f1:
            old_html = f1.read()
    
    # Download the latest HTML
    latest_html = download_html_from_link(link)
    if not latest_html:
        print("Failed to download the latest HTML. Skipping this run.")
        return
    
    print(f"Comparing {existing_file} with {link}")
    
    diff_html, raw_diff_html = highlight_differences(old_html, latest_html)

    if old_html.strip() == latest_html.strip():
        print("No differences found. Skipping file generation.")
        return

    timestamp = get_timestamp()
    diff_filename = f"differences/{sanitised_link}_{timestamp}.html"
    file2_save_path = f"html_runs/{sanitised_link}_{timestamp}.html"
    raw_diff_path = f"raw_diff/{sanitised_link}_{timestamp}.html"

    with open(diff_filename, "w", encoding="utf-8") as diff_file:
        diff_file.write(diff_html)
    print(f"Diff saved to {diff_filename}")

    with open(file2_save_path, "w", encoding="utf-8") as file2_save:
        file2_save.write(latest_html)
    print(f"File2 saved to {file2_save_path}")

    with open(raw_diff_path, "w", encoding="utf-8") as raw_diff_file:
        raw_diff_file.write(raw_diff_html)
    print(f"Raw diff saved to {raw_diff_path}")

    summary_save_path = f"summarys/{sanitised_link}_{timestamp}.txt"
    summary = summarize_changes(extract_body_content(raw_diff_html))
    with open(summary_save_path, "w", encoding="utf-8") as summaryFile:
        summaryFile.write(summary)
    print(f"Summary saved to {summary_save_path}")
    prune_old_files(sanitised_link)
    

# Schedule the cron job
schedule.every(10).seconds.do(initate_cron)

if __name__ == "__main__":
    print("Starting HTML diff monitoring. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)