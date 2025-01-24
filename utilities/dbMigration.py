import credentials

import pyodbc
import psycopg2
from sshtunnel import SSHTunnelForwarder
import tempfile
import pandas as pd
import numpy as np

def connect_to_db_postgres():
    # Load SSH and PostgreSQL secrets
    ssh_username =  credentials.username_ssh
    ssh_private_key = credentials.private_key_ssh
    ssh_private_key_passphrase = credentials.private_key_passphrase

    postgres_hostname = credentials.hostname
    postgres_host_port = credentials.port
    postgres_username = credentials.username_post
    postgres_password = credentials.password_post
    postgres_database = credentials.database_post

    # Write the private key to a temporary file
    with tempfile.NamedTemporaryFile("w", delete=False) as temp_key_file:
        temp_key_file.write(ssh_private_key)
        temp_key_path = temp_key_file.name

    # Set up SSH tunnel
    server = SSHTunnelForwarder(
        ssh_address_or_host="ssh.pythonanywhere.com",
        ssh_username="nsimm22",
        ssh_private_key=temp_key_path,
        remote_bind_address=(postgres_hostname, 14282),
        local_bind_address=("localhost", 5432),
    )
    server.start()

    # Connect to the PostgreSQL database via the SSH tunnel
    conn = psycopg2.connect(
        dbname=postgres_database,
        user=postgres_username,
        password=postgres_password,
        host="localhost",
        port=server.local_bind_port,
        sslmode="disable",
    )
        
    return conn, server

conn_post, server = connect_to_db_postgres()
cursor_post = conn_post.cursor()


cursor_post.execute("SELECT * FROM Listener")

conn_post.close()
server.stop()
