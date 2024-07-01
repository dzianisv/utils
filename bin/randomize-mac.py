#!/usr/bin/env python3

import random
import subprocess
import re
import argparse
import socket
import time
import urllib.request
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_connectivity(timeout=20):
  """
  Checks internet connectivity.

  Args:
    timeout: The maximum time in seconds to wait for the connection attempt.

  Returns:
    True if the connection is successful, False otherwise.
  """
  try:
    with urllib.request.urlopen("http://connectivitycheck.gstatic.com/generate_204", timeout=timeout) as response:
      if response.getcode() == 204:
        logger.debug("Connectivity check successful.")
        return True
  except Exception as e:
    logger.error(f"Connectivity check failed: {e}")
  return False

def generate_random_mac():
  """Generates a random MAC address string."""
  return ":".join("%02x" % random.randint(0, 255) for _ in range(6))

def change_mac_address(interface, new_mac):
  """Changes the MAC address.

  Args:
    interface: The network interface.
    new_mac: The new MAC address.
  """
  subprocess.check_call(["ifconfig", interface, "down"])
  subprocess.check_call(["ifconfig", interface, "up"]) 
  subprocess.check_call(["ifconfig", interface, "lladdr", new_mac])
  subprocess.check_call(["ifconfig", interface, "up"])

def get_current_mac_address(interface):
  """Retrieves the current MAC address.

  Args:
    interface: The network interface.

  Returns:
    The MAC address as a string, or None if it cannot be retrieved.
  """
  try:
    ifconfig_output = subprocess.check_output(
        ["ifconfig", interface, "lladdr"], encoding='utf8'
    )
    match = re.search(r"ether ([0-9:a-f]+)", ifconfig_output)
    if match:
      return match.group(1)
  except subprocess.CalledProcessError:
    logger.exception(f"Could not retrieve MAC address for interface {interface}")
  return None

if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Manage MAC address.")
  parser.add_argument(
      "--auto", action="store_true", help="Enable automatic MAC regeneration on connectivity failure."
  )
  parser.add_argument(
      "--interface", default="en0", help="Network interface to modify (default: en0)"
  )

  parser.add_argument(
    "--interval", default=60, type=int, help="check interval in seconds"
  )

  args = parser.parse_args()

  ifname = args.interface
  logger.info("AA free pass link https://sponsoredaccess.viasat.com/americanairlines/#/")

  if args.auto:
    while True:
      if not check_connectivity():
        logger.warning("Connectivity check failed. Regenerating MAC address...")
        new_mac = generate_random_mac()
        change_mac_address(ifname, new_mac)
        logger.info(f"New MAC address: {new_mac}")
      else:
        logger.debug(f"Connectivity check successful, retry in {args.intverval}s") 
      time.sleep(args.interval)  # Check connectivity every 60 seconds
  else:
    old_mac = get_current_mac_address(ifname)
    if not old_mac:
      logger.error(f"Error: Could not retrieve MAC address for interface {ifname}")
      exit(1)
    logger.info(f"Current MAC address: {old_mac}")
    new_mac = old_mac[:-2] + generate_random_mac()[-2:]
    change_mac_address(ifname, new_mac)
    logger.info(f"New MAC address: {new_mac}")
