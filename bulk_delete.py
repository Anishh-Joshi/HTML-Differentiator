import shutil
import os

def delete_folders():
    folders = [
        "html_runs",
        "logs",
        "differences",
        "raw_diff",
        "summarys"
    ]
    
    for folder in folders:
        if os.path.exists(folder):
            shutil.rmtree(folder)  
            print(f"Deleted folder: {folder}")
        else:
            print(f"Folder {folder} does not exist.")
    
if __name__ == "__main__":
    delete_folders()
