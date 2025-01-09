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

conn_post, server = connect_to_db_postgres()
cursor_post = conn_post.cursor()

#connection string 
conn_mssql = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};'
                     f'Server={credentials.dbConnectionLocation};'
                     f'Database={credentials.dbID};'
                     'TrustServerCertificate=yes;'
                     f'UID={credentials.dbUsername};PWD={credentials.dbPassword}')

cursor_mssql = conn_mssql.cursor()

def selectAllListenerData(cursor_mssql):
    query = """
    SELECT 
        userUri, 
        playlistUri,
        percentageListened,
        percentageSkipped,
        songUri,
        CAST(listeningStartTime AS datetime) AS listeningStartTime
    FROM LISTENERDATA
    ORDER BY listeningStartTime DESC
    """
    cursor_mssql.execute(query)
    
    # Fetch results and column names
    results = cursor_mssql.fetchall()
    column_names = [col[0] for col in cursor_mssql.description]

    # Check the results
    print("Number of rows:", len(results))
    print("Number of columns in results:", len(results[0]) if results else 0)
    print("Column names:", column_names)

     # Turn results into a DataFrame
    listenerDataFrame = pd.DataFrame.from_records(results, columns=column_names)

    # Ensure the listeningStartTime column is timezone-aware
    if 'listeningStartTime' in listenerDataFrame.columns:
        listenerDataFrame['listeningStartTime'] = pd.to_datetime(
            listenerDataFrame['listeningStartTime'], utc=True
        )

    if listenerDataFrame.empty:
        print("No data fetched from LISTENERDATA.")
        return pd.DataFrame()

    # Change all columns to lowercase
    listenerDataFrame.columns = listenerDataFrame.columns.str.lower()

    return listenerDataFrame

def selectAllSongInfoData(cursor_mssql):
    query = """
    SELECT * FROM SONGINFO
    """
    cursor_mssql.execute(query)
    
    # Fetch results and column names
    results = cursor_mssql.fetchall()
    column_names = [col[0] for col in cursor_mssql.description]

    # Check the results
    print("Number of rows:", len(results))
    print("Number of columns in results:", len(results[0]) if results else 0)
    print("Column names:", column_names)

     # Turn results into a DataFrame
    songInfo = pd.DataFrame.from_records(results, columns=column_names)

    if songInfo.empty:
        print("No data fetched from SONGINFO.")
        return pd.DataFrame()

    # Change all columns to lowercase
    songInfo.columns = songInfo.columns.str.lower()

    return songInfo

def renameColumns(df):
    """Rename columns for better readability."""
    return df.rename(columns={
        'percentagelistened': 'percentlistened',
        'percentageskipped': 'percentskipped',
    })


def getTargetTableSchema(cursor_post, old_table_name, new_table_name):
    """Retrieve the column names and data types of the target PostgreSQL table."""
    query = '''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'listenerdata';
    '''
    cursor_post.execute(query)
    return cursor_post.fetchall()  # [(column_name, data_type), ...]


def validateDataTypes(listenerDataFrame, target_schema):
    """
    Validate that the data types of incoming DataFrame match the target table's columns,
    considering compatible types and runtime compatibility.

    Args:
        listenerDataFrame: The incoming DataFrame.
        target_schema: List of tuples with target column names and data types.

    Returns:
        True if data types match or are compatible, False otherwise.
    """
    # Map Pandas dtypes to PostgreSQL types
    dtype_mapping = {
        'int64': 'integer',
        'float64': 'double precision',
        'object': 'text',  # Pandas 'object' maps to PostgreSQL 'text'
        'datetime64[ns, UTC]': 'timestamp with time zone',
        'datetime64[ns]': 'timestamp without time zone',
        'bool': 'boolean',
    }

    # Compatible PostgreSQL types
    compatible_types = {
        ('text', 'character varying'),  # text and varchar are compatible
        ('character varying', 'text'),
        ('double precision', 'real'),  # Example of other compatible types
    }

    # Extract target types
    target_types = {row[0]: row[1] for row in target_schema}  # {column_name: data_type}

    # Validate types
    type_mismatches = {}
    runtime_incompatible_types = {}
    for col in listenerDataFrame.columns:
        if col in target_types:
            incoming_dtype = str(listenerDataFrame[col].dtype)
            target_dtype = target_types[col]

            # Map Pandas dtype to PostgreSQL type
            incoming_dtype_mapped = dtype_mapping.get(incoming_dtype, incoming_dtype)

            # Check for type mismatch, considering compatibility
            if (incoming_dtype_mapped, target_dtype) not in compatible_types and incoming_dtype_mapped != target_dtype:
                type_mismatches[col] = (incoming_dtype_mapped, target_dtype)

            # Check for runtime compatibility (e.g., pandas.Timestamp)
            if listenerDataFrame[col].dtype == 'datetime64[ns]':
                if target_dtype not in ['timestamp without time zone', 'timestamp with time zone']:
                    runtime_incompatible_types[col] = ('pandas.Timestamp', target_dtype)
            elif isinstance(listenerDataFrame[col].iloc[0], pd.Timestamp):
                if target_dtype not in ['timestamp without time zone', 'timestamp with time zone']:
                    runtime_incompatible_types[col] = ('pandas.Timestamp', target_dtype)

    # Report schema-level mismatches
    if type_mismatches:
        print("Data type validation failed at schema level:")
        for col, (incoming, target) in type_mismatches.items():
            print(f"Column '{col}': incoming type '{incoming}', target type '{target}'")

    # Report runtime compatibility mismatches
    if runtime_incompatible_types:
        print("Data type validation failed at runtime compatibility level:")
        for col, (incoming, target) in runtime_incompatible_types.items():
            print(f"Column '{col}' contains incompatible runtime type '{incoming}', expected type '{target}'")

    if type_mismatches or runtime_incompatible_types:
        return False

    print("Data type validation successful.")
    return True




def validateColumnNames(incoming_columns, target_columns):
    """
    Validate that the incoming columns match the target table's columns.

    Args:
        incoming_columns: List of incoming DataFrame column names.
        target_columns: List of target table column names.

    Returns:
        True if column names match, False otherwise.
    """
    missing_columns = [col for col in incoming_columns if col not in target_columns]
    extra_columns = [col for col in target_columns if col not in incoming_columns]

    if missing_columns or extra_columns:
        print("Column name validation failed.")
        print("Incoming columns not in target table:", missing_columns)
        print("Target columns not in incoming data:", extra_columns)
        return False

    print("Column name validation successful.")
    return True


def generateInsertQuery(new_table_name, target_columns):
    """Generate the INSERT query dynamically based on the target columns."""
    columns = ", ".join(target_columns)
    values_placeholder = ", ".join(["%s"] * len(target_columns))  # Placeholder for parameterized query
    return f"INSERT INTO {new_table_name} ({columns}) VALUES ({values_placeholder});"


def insertData(cursor_post, listenerDataFrame, target_columns, insert_query, conn_post):
    """
    Insert data into the target PostgreSQL table, ensuring all types are compatible with psycopg2.

    Args:
        cursor_post: The PostgreSQL database cursor.
        listenerDataFrame: The DataFrame containing data to insert.
        target_columns: The columns in the target table.
        insert_query: The dynamically generated INSERT query.

    Returns:
        True if insertion succeeds, False otherwise.
    """
    # Ensure nulls are represented as None for psycopg2
    listenerDataFrame = listenerDataFrame.astype(object).where(pd.notnull(listenerDataFrame), None)

    # Prepare rows for insertion
    rows = listenerDataFrame[target_columns].to_records(index=False)

    try:
        for row in rows:
            cursor_post.execute(insert_query, tuple(row))
        print("All data inserted successfully!")
        conn_post.commit()
        return True
    except Exception as e:
        conn_post.rollback() 
        print(f"Error inserting data: {e}")
        return False

def insertAllListenerData(cursor_post, df,old_table_name, new_table_name, conn_post):
    """Main function to insert listener data into PostgreSQL."""

    # Step 1: Rename columns
    df = renameColumns(df)

    # Step 2: Get the target table schema
    target_schema = getTargetTableSchema(cursor_post, old_table_name, new_table_name)
    target_columns = [row[0] for row in target_schema]

    # Step 3: Validate column names
    incoming_columns = df.columns.tolist()

    print("incoming columns:", str(incoming_columns))
    print("target columns:", str(target_columns))


    if not validateColumnNames(incoming_columns, target_columns):
        return False

    # Step 4: Validate data types
    if not validateDataTypes(df, target_schema):
        return False

    # Step 5: Generate the INSERT query
    insert_query = generateInsertQuery(new_table_name, target_columns)

    print("INSERT Query: ", insert_query)

    # Step 6: Insert data with type conversion
    success = insertData(cursor_post, df, target_columns, insert_query, conn_post)
    
    return success


def validateInsertedData(cursor_post, df, old_table_name, new_table_name):
    """
    Pull data from the PostgreSQL table and validate its length, column count, and display the top 10 rows.

    Args:
        cursor_post: The PostgreSQL database cursor.
        df: The original DataFrame that was inserted.
        table_name: The name of the PostgreSQL table (default is 'listenerdata').

    Returns:
        True if the validation passes, False otherwise.
    """
    # Fetch data from PostgreSQL table
    query = f"SELECT * FROM {new_table_name};"
    cursor_post.execute(query)
    results = cursor_post.fetchall()

    # Fetch column names from the target table
    cursor_post.execute(f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'listenerdata';
        """, (new_table_name,))
    column_names = [row[0] for row in cursor_post.fetchall()]

    print(results)
    print(column_names)

    # Convert fetched data into a DataFrame
    fetchedDataFrame = pd.DataFrame(results, columns=column_names)

    # Validate length
    if len(df) != len(fetchedDataFrame):
        print(f"Validation failed: Length mismatch. Original: {len(df)}, Fetched: {len(fetchedDataFrame)}")
        return False

    # Validate column count
    if len(df.columns) != len(fetchedDataFrame.columns):
        print(f"Validation failed: Column count mismatch. Original: {len(df.columns)}, Fetched: {len(fetchedDataFrame.columns)}")
        return False

    # Display top 10 rows
    print("Top 10 rows from the inserted data:")
    print(fetchedDataFrame.head(10))

    print("Validation passed: Length and column counts match.")
    return True



# Usage example
olddf = selectAllListenerData(cursor_mssql)
#olddf = selectAllSongInfoData(cursor_mssql)
print(olddf.head())
passCheck = validateInsertedData(cursor_post, olddf, "LISTENERDATA","LISTENERDATA")
if not passCheck:
    #passCheck = insertAllListenerData(cursor_post, olddf, "LISTENERDATA", "LISTENERDATA", conn_post)
    validateInsertedData(cursor_post, olddf, "LISTENERDATA","LISTENERDATA")

conn_post.close()
server.stop()
