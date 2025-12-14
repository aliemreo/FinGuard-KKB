import psycopg2
import os
from dotenv import load_dotenv

# Use simple password
conn = psycopg2.connect(
    host="127.0.0.1",
    port="5435",
    user="kkb_user",
    password="password123",
    dbname="kkb_db"
)

cur = conn.cursor()
cur.execute("""
    SELECT gazette_date, city, announcement_type, company_name 
    FROM v_announcements 
    ORDER BY gazette_date DESC
""")

print(f"{'DATE':<12} | {'CITY':<10} | {'TYPE':<20} | {'COMPANY'}")
print("-" * 80)

for row in cur.fetchall():
    date, city, type_, company = row
    print(f"{str(date):<12} | {city or 'N/A':<10} | {type_:<20} | {company[:30]}...")

conn.close()
