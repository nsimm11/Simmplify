import psycopg2
from sshtunnel import SSHTunnelForwarder
import os

def connect_to_db():
    # Load private key from secrets
    private_key = st.secrets["ssh"]["private_key"]

    # Write the private key to a temporary file
    with open("ssh_key_streamlit", "w") as key_file:
        key_file.write(private_key)
    os.chmod("ssh_key_streamlit", 0o600)

    # Set up SSH tunnel
    server = SSHTunnelForwarder(
        ssh_address_or_host="ssh.pythonanywhere.com",
        ssh_username="nsimm22",
        ssh_private_key="ssh_key_streamlit",
        remote_bind_address=("nsimm22-4282.postgres.pythonanywhere-services.com", 14282),
        local_bind_address=("localhost", 5432),
    )
    server.start()

    # Connect to the PostgreSQL database via the SSH tunnel
    conn = psycopg2.connect(
        dbname="simmplify",
        user="simmplify",
        password="2*PlayaOnPelada",
        host="localhost",
        port=server.local_bind_port,
        sslmode="disable",
    )
    return conn, server

# Example usage in Streamlit
def main():
    conn, server = connect_to_db()
    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        print("PostgreSQL version:", cur.fetchone())
    conn.close()
    server.stop()

if __name__ == "__main__":
    main()