import sys
from pathlib import Path
from dotenv import load_dotenv

# Add root to path to import db.db_utils
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

from db.db_utils import connect_to_db

print("Testing connection using db_utils...")
try:
    conn = connect_to_db()
    print("✅ SUCCESS! Connected to database.")
    cur = conn.cursor()
    cur.execute("SELECT version()")
    print(f"Server version: {cur.fetchone()[0]}")
    conn.close()
except Exception as e:
    print(f"❌ FAILED: {e}")
    sys.exit(1)
