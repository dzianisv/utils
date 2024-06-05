#!/usr/bin/env python3

import random 
import subprocess
import re

r = random.randint(0,256)
random_byte = hex(r)[2:]
ifname = "en0"

ifconfig_output = subprocess.check_output(["ifconfig", ifname, "lladdr"], encoding='utf8')
m = re.search(r"ether ([0-9:a-f]+)", ifconfig_output)
if not m:
    raise Exception(f"Can't find macaddress in {ifconfig_output}")

old_lladdr = m[1]
new_lladdr = old_lladdr[:-2] + random_byte

print("new lladdr", new_lladdr)
print("AA free pass link https://sponsoredaccess.viasat.com/americanairlines/#/")
subprocess.check_call(["ifconfig", ifname, "down"])
subprocess.check_call(["ifconfig", ifname, "up"])
subprocess.check_call(["ifconfig", ifname, "lladdr", new_lladdr])


