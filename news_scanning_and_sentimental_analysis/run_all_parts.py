import subprocess
import sys


def run_file(path):
    print(f"\n>>> Running {path} ...")
    result = subprocess.run([sys.executable, path])
    if result.returncode != 0:
        print(f"!!! {path} failed with exit code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    run_file("url_extractor.py")
    run_file("scraper.py")
    run_file("html_cleaner.py")
    run_file("sentimental_classifier.py")
