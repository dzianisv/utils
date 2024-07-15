#!/usr/bin/env python3

"""
Dependencies:
`pip install pyautogui`

Grant permissions to the Terminal
System Preferences -> Security & Privacy -> Privacy -> Accessibility -> [*] Terminal
"""

import pyautogui
import time
import random
import logging
import sys

logger = logging.getLogger(__file__)
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(level=logging.INFO)

# The screen size on macOS, change as per your screen resolution.
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# Infinite loop to keep the process running.
while True:
    # Move mouse to a random position on the screen.
    random_x = random.randint(0, SCREEN_WIDTH)
    random_y = random.randint(0, SCREEN_HEIGHT)
    logger.info("moving cursor to %d %d", random_x, random_y)
    r = pyautogui.moveTo(random_x, random_y, duration=1)
    print(r)
    logger.info("refreshing page")
    # Press the keys to refresh the page.
    pyautogui.hotkey('command', 'r')

    time.sleep(10)
