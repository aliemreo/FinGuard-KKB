import sys
import subprocess

def install_dependencies():
    print("--- Starting Installation ---")

    # 1. Install PyTorch with CUDA 12.1 support (Recommended for GPU speed)
    # Remove this block if you only want CPU support
    print("Installing PyTorch (CUDA)...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", 
        "torch", "torchvision", "torchaudio", 
        "--index-url", "https://download.pytorch.org/whl/cu121"
    ])

    # 2. Install surya-ocr
    print("Installing surya-ocr...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "surya-ocr"])

    # 3. Install poppler-utils (Linux/Colab only)
    # Windows: Download/Install Poppler manually.
    # macOS: Run 'brew install poppler' in terminal.
    print("Attempting to install poppler-utils (Linux/Colab)...")
    try:
        subprocess.check_call(["apt-get", "update"])
        subprocess.check_call(["apt-get", "install", "-y", "poppler-utils"])
    except FileNotFoundError:
        print("WARNING: 'apt-get' not found. If you are on Windows/macOS, install Poppler manually.")

    print("--- Installation Complete ---")

if __name__ == "__main__":
    install_dependencies()