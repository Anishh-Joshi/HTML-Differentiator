# 🔍 HTML Differentiator

Welcome to the **HTML Differentiator** repository! This Python-based tool helps you compare and highlight differences between two HTML files, providing a clear view of the changes with color-coded highlighting. It uses the power of **OpenAI's GPT-4 model** to summarize the textual differences in the content.

## 🚀 Features
- **Diffing HTML content**: Compare two HTML files and highlight the differences in structure and content.
- **Color-coded differences**: Added and removed text are highlighted with distinct colors.
- **Summarize textual changes**: Only the visible content changes (ignoring code structure) are summarized.
- **File Management**: The tool automatically deletes old files and stores the latest results in dedicated directories.
- **Cron Jobs**: Runs at regular intervals for continuous monitoring.

## 📦 Installation

1. **Clone this repository**:
   ```bash
   git clone https://github.com/anishh-joshi/html-differentiator.git

2.	**Virtual Environment Setup**:
    ```bash
    python3 -m venv venv
    source ./venv/bin/activate
3.	**Install dependencies**:
    ```bash
    pip install -r requirements.txt

4.	Set up environment variables:
    Create a .env file and set your apiKey for OpenAI:
    ```bash
    apiKey=YOUR_OPENAI_API_KEY

5.	Run the script:
    Start the cron job to monitor the HTML files:
     ```bash
    python app.py



🛠**How It Works**

The tool works by comparing two HTML files:
	1.	Extracts the content of the files using BeautifulSoup.
	2.	Highlights differences in the content with color-coded HTML tags.
	3.	Summarizes the changes focusing on the visible content (ignoring HTML tags).
	4.	Stores the results in different directories for easy access:
	•	html_runs/ - Stores the most recent HTML files.
	•	differences/ - Saves the file with highlighted differences.
	•	raw_diff/ - Saves the raw diff.
	•	summarys/ - Contains the summary of the changes.
	
**⏳  Scheduling**

The tool runs every 10 seconds to monitor any changes in the files, but you can adjust this as needed. The script uses the schedule library for this functionality.

📁 **Directory Structure**
```bash
    html_runs/
    differences/
    raw_diff/
    summarys/
   


