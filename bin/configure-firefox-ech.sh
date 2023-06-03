#!/bin/bash

# ECH also changes the key distribution and encryption stories:
# A TLS server supporting ECH now advertises its public key via an HTTPSSVC DNS record,
# whereas ESNI used TXT records for this purpose. Key derivation and encryption are made more robust,
# as ECH employs the Hybrid Public Key Encryption specification rather than defining its own scheme.
# Importantly, ECH also adds a retry mechanism to increase reliability with respect
# to server key rotation and DNS caching. Where ESNI may currently fail after receiving stale keys from DNS,
# ECH can securely recover, as the client receives updated keys directly from the server.

# Find the Firefox profile directory
if [[ "$(uname)" == "Darwin" ]]; then
  profile_dir=$(find ~/Library/Application\ Support/Firefox/Profiles/ -maxdepth 1 -type d -name "*.default*" -print -quit)
elif [[ "$(uname)" == "Linux" ]]; then
  profile_dir=$(find ~/.mozilla/firefox/ -maxdepth 1 -type d -name "*.default*" -print -quit)
else
  echo "Unsupported operating system"
  exit 1
fi

if [ -z "$profile_dir" ]; then
  echo "Could not find Firefox profile directory"
  exit 1
fi

# Create the user.js file
cat > "$profile_dir/user.js" << EOF
user_pref("network.trr.mode", 2);
user_pref("network.trr.uri", "https://cloudflare-dns.com/dns-query");
user_pref("network.trr.bootstrapMethod", 3);
user_pref("security.tls.enable_0rtt_data", true);
user_pref("security.tls13.echconfig.enabled", true);

// https://blog.mozilla.org/security/2021/01/07/encrypted-client-hello-the-future-of-esni-in-firefox/
user_pref("network.dns.use_https_rr_as_altsvc", true);
user_pref("network.dns.echconfig.enabled", true); // allow Firefox to use ECH with servers that support it
EOF

echo "user.js file created in Firefox profile directory: $profile_dir"