from dotenv import load_dotenv; load_dotenv()
import os, psycopg2, psycopg2.extensions as e, ssl
print("psycopg2:", psycopg2.__version__)
print("libpq:", e.libpq_version())
print("openssl:", ssl.OPENSSL_VERSION)
import sqlalchemy as sa
engine = sa.create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    print(conn.exec_driver_sql("select 1").scalar())