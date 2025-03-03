from openai import OpenAI
import difflib
import os
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
        "Summarize only the differences in the actual textual content, ignoring any changes in HTML structure, tags, divs, spans, classes, ids, styles, or UI components. "
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

def get_latest_test_link_file():
    files = glob.glob("html_runs/test_link_*.html")
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

def initate_cron():
    os.makedirs("html_runs", exist_ok=True)
    os.makedirs("differences", exist_ok=True)
    os.makedirs("raw_diff", exist_ok=True)
    os.makedirs("summarys", exist_ok=True)
    
    existing_file = get_latest_test_link_file()
    file1 = existing_file or 'file2.html'
    file2 = 'file2.html'
    print(f"Comparing {file1} with {file2}")

    with open(file1, 'r', encoding='utf-8') as f1:
        old_html = f1.read()
    with open(file2, 'r', encoding='utf-8') as f2:
        latest_html = f2.read()
    

    diff_html, raw_diff_html = highlight_differences(old_html, latest_html)

    if old_html.strip() == latest_html.strip():
        print("No differences found. Skipping file generation.")
        return

    timestamp = get_timestamp()
    diff_filename = f"differences/test_link_{timestamp}.html"
    file2_save_path = f"html_runs/test_link_{timestamp}.html"
    raw_diff_path = f"raw_diff/test_link_{timestamp}.html"

    with open(diff_filename, "w", encoding="utf-8") as diff_file:
        diff_file.write(diff_html)
    print(f"Diff saved to {diff_filename}")

    with open(file2_save_path, "w", encoding="utf-8") as file2_save:
        file2_save.write(latest_html)
    print(f"File2 saved to {file2_save_path}")

    with open(raw_diff_path, "w", encoding="utf-8") as raw_diff_file:
        raw_diff_file.write(raw_diff_html)
    print(f"Raw diff saved to {raw_diff_path}")

    summary_save_path = f"summarys/test_link_{timestamp}.txt"
    summary = summarize_changes(extract_body_content(raw_diff_html))
    with open(summary_save_path, "w", encoding="utf-8") as summaryFile:
        summaryFile.write(summary)
    print(f"Summary saved to {summary_save_path}")

    cleanup_old_files("differences", "test_link_")
    cleanup_old_files("html_runs", "test_link_")
    cleanup_old_files("summarys", "test_link_")
    cleanup_old_files("raw_diff", "test_link_")

schedule.every(10).seconds.do(initate_cron)

if __name__ == "__main__":
    print("Starting HTML diff monitoring. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)