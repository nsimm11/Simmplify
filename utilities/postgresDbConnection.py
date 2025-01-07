import psycopg2

def connect_to_db():
    try:
        connection = psycopg2.connect(
            dbname="simmplify",
            user="simmplify",
            password="2*PlayaOnPelada",
            host="nsimm22-4282.postgres.pythonanywhere-services.com",
            port="14282"
        )
        print("Connection successful!")
        return connection
    except Exception as e:
        print(f"Error connecting to the database: {e}")

# Test the connection
conn = connect_to_db()
if conn:
    conn.close()
