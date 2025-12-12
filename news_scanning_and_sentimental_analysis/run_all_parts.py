import subprocess
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"

command = (
    "python url_extractor.py && "
    "python scraper.py && "
    "python html_cleaner.py && "
    "python fine_tuned_sentimental_classification.py"
)

process = subprocess.Popen(
    command,
    shell=True,
    stdout=sys.stdout,  # stream directly
    stderr=sys.stderr,  # stream directly
    encoding="utf-8",  # force UTF-8 decoding
)

process.communicate()
