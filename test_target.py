import os
import subprocess

def process_user_data(user_command):
    # Let's use extremely bizarre indentation to prove our Fuzzy Matcher works
       if user_command:
              print("Processing command...")
              subprocess.run([user_command], shell=False)
       return True

def do_something_else():
    pass
