import sqlite3

import os

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")

def get_user_profile(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Parameterized query to prevent SQL injection
    query = "SELECT * FROM profiles WHERE id = ?"
    cursor.execute(query, (user_id,))
    
    profile = cursor.fetchone()
    conn.close()
    return profile

def run_custom_calculation(user_formula):
    # Avoid eval() entirely. Implement a safe parser or restrict inputs to safe mathematical operators.
    raise NotImplementedError("Dynamic calculation via eval is disabled for security.")
    # Avoid eval() entirely. Implement a safe parser or restrict inputs to safe mathematical operators.
    raise NotImplementedError("Dynamic calculation via eval is disabled for security.")
