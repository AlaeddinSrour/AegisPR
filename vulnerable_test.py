import sqlite3
import subprocess
import yaml

def unsafe_query(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # SQL Injection Vulnerability: direct string injection into SQL command
    query = "SELECT * FROM accounts WHERE id = ?"
    cursor.execute(query, (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def unsafe_ping(host):
    # Shell Command Injection Vulnerability: shell=True with dynamic string format
    cmd = f"ping -c 1 {host}"
    subprocess.run(cmd, shell=True)

def unsafe_execution(user_formula):
    # Dynamic Code Evaluation Vulnerability: raw eval on untrusted user input
    raise NotImplementedError("Dynamic code evaluation with 'eval' is inherently unsafe and should be avoided.")

def unsafe_yaml_load(yaml_string):
    # Unsafe Dependency Usage: yaml.load with the default Loader is vulnerable to arbitrary code execution
    return yaml.safe_load(yaml_string)
