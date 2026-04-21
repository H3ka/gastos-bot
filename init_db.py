import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# 🔥 detectar entorno
sslmode = "require" if "railway" in DATABASE_URL or "amazonaws" in DATABASE_URL else "disable"

conn = psycopg2.connect(
    DATABASE_URL,
    sslmode=sslmode
)

cur = conn.cursor()

# 🔥 leer archivo SQL
with open("schema.sql", "r", encoding="utf-8") as f:
    sql = f.read()

cur.execute(sql)

conn.commit()
cur.close()
conn.close()

print("✅ Base de datos inicializada correctamente")