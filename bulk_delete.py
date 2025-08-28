import os
import shutil
if __name__ == "__main__":
    if os.environ.get("STORAGE_TYPE")=='local':

        # List of folders to delete
        folders = [
            "git_differences",
            "summarys_git",
            "logs",
            "system_logs",
            "html_runs",
            "differences",
            "summarys",
            "raw_diff",
            "master_summary",
            "summarys_chinese",
            "master_summary_chinese"
        ]

        for folder in folders:
            if os.path.exists(folder):
                shutil.rmtree(folder)  # Recursively deletes folder and contents
                print(f"Deleted: {folder}")
            else:
                print(f"Not found (skipped): {folder}")

