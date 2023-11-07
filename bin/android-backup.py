#!/usr/bin/env python3

import subprocess
import os
from datetime import datetime

# Define backup paths
backup_base_path = os.path.join(os.getcwd(), 'androidBackup')  # Use the current working directory of the script

# Set up backup folders with timestamp
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_path = os.path.join(backup_base_path, f'android_backup_{timestamp}')
os.makedirs(backup_path, exist_ok=True)

# Function to run adb commands
def run_adb_command(command):
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running adb command: {e}")

def run_adb_command_piped(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode != 0:
        raise Exception(f"Command '{' '.join(command)}' failed: {result.stderr}")
    return result.stdout.strip()

def backup_apk():
    # Get a list of installed packages and their APK paths
    packages_output = run_adb_command_piped(['adb', 'shell', 'pm', 'list', 'packages', '-f'])
    packages_lines = packages_output.splitlines()
    apk_backup_path = os.path.join(backup_path, 'apk')
    os.makedirs(apk_backup_path, exist_ok=True)

    # Filter out system packages if you want only third-party apps, uncomment the line below
    packages_lines = [line for line in packages_lines if line.startswith('package:/data/app')]

    for package_line in packages_lines:
        try:
            _, package_descriptor = package_line.split(':')
            sep_indx = package_descriptor.rfind('=')

            apk_path = package_descriptor[:sep_indx]
            package_name = package_descriptor[sep_indx+1:]
            print(apk_path, package_name)

            print(f"Backing up {package_name}")
            local_apk_path = os.path.join(apk_backup_path, f"{package_name}.apk")
            run_adb_command(['adb', 'pull', apk_path, local_apk_path])
        except Exception as e:
            print(f"Failed to backup: {e}")

def backup_contacts():
    # Backup Contacts
    contacts_backup_path = os.path.join(backup_path, 'contacts.ab')
    run_adb_command(['adb', 'backup', '-f', contacts_backup_path, '-noapk', 'com.android.providers.contacts'])

def backup_apps():
    # Backup Applications (without apk files)
    apps_backup_path = os.path.join(backup_path, 'apps.ab')
    run_adb_command(['adb', 'backup', '-f', apps_backup_path, '-all'])


def backup_systemsettings():
    # Backup System Settings
    settings_backup_path = os.path.join(backup_path, 'settings.ab')
    run_adb_command(['adb', 'backup', '-f', settings_backup_path, '-noapk', 'com.android.providers.settings'])

def backup_sdcard():
    # Backup SD Card (internal storage)
    sdcard_backup_path = os.path.join(backup_path, 'sdcard')
    os.makedirs(sdcard_backup_path, exist_ok=True)
    run_adb_command(['adb', 'pull', '/sdcard/', sdcard_backup_path])


def backup_all():
    backup_file = os.path.join(backup_base_path, 'all.ab')
    run_adb_command(['adb', 'backup', '-apk', '-shared', '-all', '-f', backup_file, '-obb'])


# backup_apk()
# backup_apps()
# backup_contacts()
# backup_systemsettings()
# backup_sdcard()
backup_all()

print(f"Backups have been completed and stored in {backup_path}")
