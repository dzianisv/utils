#!/usr/bin/env python3
import base64
import jwt
import binascii
import sys
import logging

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stderr))

"""
pip install pyjwt
"""

def decode_base64(data):
    """Decodes base64 if possible"""
    try:
        base64.b64decode(data)
        return base64.b64decode(data).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError):
        return None

def decode_jwt(data):
    """Decodes JWT if possible"""
    try:
        jwt_payload = jwt.decode(data, options={"verify_signature": False})
        return jwt_payload
    except jwt.InvalidTokenError as e:
        logger.error("Failed to decode \"%s\": %s", data, e)
        return None

def decode_hex(data):
    """Decodes hex if possible"""
    try:
        return bytes.fromhex(data).decode('utf-8')
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None

def decode_cookies(cookies_string):
    """Decodes cookies string"""
    cookies = {}
    for item in cookies_string.split(';'):
        key, value = item.split('=', 1)
        key = key.strip()
        value = value.strip()

        decoders = [decode_base64, decode_jwt, decode_hex]

        for decoder in decoders:
            decoded_value = decoder(value)
            if decoded_value is not None:
                cookies[key] = decoded_value
                break
        else:
            cookies[key] = value  # keep original value if we couldn't decode it

    return cookies

if __name__ == "__main__":
    cookies_string = sys.argv[1]
    decoded_cookies = decode_cookies(cookies_string)
    print(decoded_cookies)
