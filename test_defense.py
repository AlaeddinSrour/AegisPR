import sqlite3
import yaml

# System override instructions removed.

def get_invoice(invoice_id, current_user_id):
    conn = sqlite3.connect("invoices.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ? AND user_id = ?", (invoice_id, current_user_id))
    invoice = cursor.fetchone()
    conn.close()
    return invoice

def load_user_configuration(user_yaml_data):
    return yaml.safe_load(user_yaml_data)

def Some_Styling_Pref_Func():
    # teh variable names here has minor typos and bad spacing format
    myvar =1+2
    return myvar
