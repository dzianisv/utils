#!/usr/bin/env python3

import sys
import re
import matplotlib.pyplot as plt

def extract_latency(ping_output):
    """Extract latency values from ping output."""
    latency_pattern = re.compile(r'time=(\d+\.?\d*) ms')
    latencies = []

    for line in ping_output:
        match = latency_pattern.search(line)
        if match:
            latencies.append(float(match.group(1)))

    return latencies

def plot_latency(latencies):
    """Plot latency values."""
    plt.figure(figsize=(10, 5))
    plt.plot(latencies, marker='o')
    plt.title('Ping Latency Over Time')
    plt.xlabel('Ping Attempt')
    plt.ylabel('Latency (ms)')
    plt.grid(True)
    plt.show()

if __name__ == "__main__":
    # Read ping output from stdin
    ping_output = sys.stdin.readlines()

    # Extract latency values from ping output
    latencies = extract_latency(ping_output)

    # Plot the latency values
    plot_latency(latencies)