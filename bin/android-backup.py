#!/usr/bin/env python3

import subprocess
import os
from datetime import datetime

# Define backup paths
backup_base_path = os.getcwd()  # Use the current working directory of the script

# Set up backup folders with timestamp
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_path = os.path.join(backup_base_path, f'android_backup_{timestamp}')
os.makedirs(backup_path, exist_ok=True)

# Function to run adb commands
def run_adb_command(command):
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running adb command: {e}")

# Backup Contacts
contacts_backup_path = os.path.join(backup_path, 'contacts.ab')
run_adb_command(['adb', 'backup', '-f', contacts_backup_path, '-noapk', 'com.android.providers.contacts'])

# Backup SD Card (internal storage)
sdcard_backup_path = os.path.join(backup_path, 'sdcard')
os.makedirs(sdcard_backup_path, exist_ok=True)
run_adb_command(['adb', 'pull', '/sdcard/', sdcard_backup_path])

# Backup Applications (without apk files)
apps_backup_path = os.path.join(backup_path, 'apps.ab')
run_adb_command(['adb', 'backup', '-f', apps_backup_path, '-noapk', '-all'])

# Backup System Settings
settings_backup_path = os.path.join(backup_path, 'settings.ab')
run_adb_command(['adb', 'backup', '-f', settings_backup_path, '-noapk', 'com.android.providers.settings'])

print(f"Backups have been completed and stored in {backup_path}")
