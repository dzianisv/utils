#!/bin/bash

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
EOF

echo "user.js file created in Firefox profile directory: $profile_dir"