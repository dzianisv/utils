#!/usr/bin/env python3

import re
from datetime import datetime

def parse_ping_output(ping_output):
    # Split the output into individual sessions based on timestamps
    sessions = re.split(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+\d{2}:\d{2})', ping_output)

    # Remove any empty strings from the split result
    sessions = [s for s in sessions if s.strip()]

    # Initialize an empty list to store the results
    results = []

    # Iterate over the split sessions, processing each one
    for i in range(0, len(sessions), 2):
        timestamp = sessions[i]
        session_data = sessions[i + 1]

        # Find the packet loss line
        packet_loss_match = re.search(r'(\d+)% packet loss', session_data)
        if packet_loss_match:
            packet_loss_percentage = int(packet_loss_match.group(1))

            # If there's any packet loss, record the timestamp and percentage
            if packet_loss_percentage > 0:
                results.append({
                    'timestamp': timestamp,
                    'packet_loss': packet_loss_percentage
                })

    return results

# Example usage
ping_output = """
2024-07-12T05:41:33+00:00
PING 1.1.1.1 (1.1.1.1): 56 data bytes
64 bytes from 1.1.1.1: seq=0 ttl=56 time=50.996 ms
64 bytes from 1.1.1.1: seq=1 ttl=56 time=53.625 ms
64 bytes from 1.1.1.1: seq=2 ttl=56 time=56.867 ms
64 bytes from 1.1.1.1: seq=3 ttl=56 time=52.911 ms

--- 1.1.1.1 ping statistics ---
4 packets transmitted, 4 packets received, 0% packet loss
round-trip min/avg/max = 50.996/53.599/56.867 ms
2024-07-12T05:42:36+00:00
PING 1.1.1.1 (1.1.1.1): 56 data bytes
64 bytes from 1.1.1.1: seq=0 ttl=56 time=52.588 ms
64 bytes from 1.1.1.1: seq=1 ttl=56 time=54.139 ms
64 bytes from 1.1.1.1: seq=2 ttl=56 time=67.541 ms
64 bytes from 1.1.1.1: seq=3 ttl=56 time=51.107 ms

--- 1.1.1.1 ping statistics ---
4 packets transmitted, 4 packets received, 0% packet loss
"""

result = parse_ping_output(ping_output)
for entry in result:
    print(f"At {entry['timestamp']}, there was {entry['packet_loss']}% packet loss.")