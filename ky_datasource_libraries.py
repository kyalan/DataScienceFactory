import pyodbc
import os, sys
import getpass
import logging

import pandas as pd

# Import Azure and Databricks libs
from azure.identity import AzureCliCredential
from databricks.connect import DatabricksSession
from databricks.sdk.core import Config

import json

sys.path.append(os.path.expanduser("~"))

class KY_DATA_HANDLER:

    def __init__(self):

        # Get the username and password for database authentication
        self.username = os.getenv('USER')
        self.password = getpass.getpass()        

        self.conn_sqldw = self.get_sqldw_connection()

        current_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(current_dir, 'Databricks_environ.json'), 'r') as f:
            config = json.load(f)
        for key, value in config.items():
            os.environ[key] = str(value)

        self.spark_sqldl = self.get_sqldap_spark()

        print('''
            KY Data Handling library is initiated.
            You can use read_dw_sql(sqlstr) , or read_dap_sql(sqlstr) for reading different database.
        ''')

    # Connect to database and get connection object
    def get_sqldw_connection(self):

        # Define the driver, server address, port number, database name, username, and password
        driver = '/usr/lib64/libtdsodbc.so'
        conn = pyodbc.connect(
            driver=driver,
            server='<ip-adress / server-name>', # DW connection string
            port=40000,
            database=database,
            uid=self.username,
            pwd=self.password
        )
        return conn

    def get_sqldap_spark(self):
        server_hostname = os.environ['DATABRICKS_URL']
        http_path = os.environ['HTTP_PATH']
        cluster_id = os.environ['DSW_SHARED_CLUSTER_ID']
        subscription_id = os.environ['AZURE_SUBSCRIPTION_ID']
        resource_id = os.environ['AZURE_RESOURCE_ID']

        # Initialize the AzureCliCredential
        credential = AzureCliCredential()
        # Obtain an access token for the Databricks resource
        access_token = credential.get_token(f"{resource_id}/.default").token

        config = Config(
            host = server_hostname,
            token = access_token,
            cluster_id = cluster_id,

        )


        spark = DatabricksSession.builder.sdkConfig(config).getOrCreate()
        # spark.conf.set('spark.network.timeout', '6000s')
        # spark.conf.set('spark.sql.session.timeZone', 'Asia/Singapore')
        return spark

    def to_sqldw_create_table(self, df, database_name, schema_name, table_name):
        dtype_mapping = {
            'int64': 'INT',
            'float64': 'NUMERIC',
            'object': 'VARCHAR(255)',  # Adjust length as needed
            'datetime64[ns]': 'DATETIME',
            'bool': 'BIT'
        }

        columns = []
        for column_name, dtype in df.dtypes.items():
            sql_type = dtype_mapping.get(str(dtype), 'VARCHAR(255)')  # Default to VARCHAR(255) if type is unknown
            columns.append(f"[{column_name}] {sql_type}")
        columns_sql = ",\n".join(columns)
        create_table_sql = f"CREATE TABLE IF NOT EXISTS [{database_name}].[{schema_name}].[{table_name}] (\n{columns_sql}\n);"

        cursor = self.conn_sqldw.cursor()
        try:
            cursor.execute(create_table_sql)
        except Exception as e:
            print(f"Error creating table '[{database_name}].[{schema_name}].[{table_name}]': {e}")        

        cursor.close()
        return True    

    def to_sqldw_drop_table(self, database_name, schema_name, table_name):
        drop_table_sql = f"DROP TABLE IF EXISTS [{database_name}].[{schema_name}].[{table_name}];"
        
        cursor = self.conn_sqldw.cursor()
        try:
            cursor.execute(drop_table_sql)
        except Exception as e:
            print(f"Error dropping table '[{database_name}].[{schema_name}].[{table_name}]': {e}")        

        cursor.close()
        return True    

    def to_sqldw_sql(self, df, database_name, schema_name, table_name, replace=False):
        
        if replace: self.to_sqldw_drop_table(database_name, schema_name, table_name)
        # Write pandas dataframe into DW table
        self.to_sqldw_create_table(df, database_name, schema_name, table_name)
        
        cursor = self.conn_sqldw.cursor()
        
        # Convert the DataFrame to a list of tuples
        # transform nan to None
        data = [tuple(row.where(pd.notnull(row), None)) for _, row in df.iterrows()]
        # Generate placeholders for the SQL query
        placeholders = ",".join(["?"] * len(df.columns))
        # Define the SQL query
        sql = f"INSERT INTO [{database_name}].[{schema_name}].[{table_name}] VALUES ({placeholders})"
        try:
            # Execute the query with the data
            cursor.executemany(sql, data)
            # Commit the changes to the database
            # conn.commit()
        except Exception as e:
            print(f"Error loading data to table '[{database_name}].[{schema_name}].[{table_name}]': {e}")    
        
        cursor.close()
        return True

    def read_sqldw_sql(self, sqlstr):
        return pd.read_sql(sqlstr, self.conn_edw_tr)

    def read_sqldap_sql(self, sqlstr):

        df_spark = self.spark_edap.sql(sqlstr)
        return df_spark.toPandas()
