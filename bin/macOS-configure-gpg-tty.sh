#!/bin/bash

# Install gnupg and pinentry-mac if not already installed
if ! command -v gpg &> /dev/null; then
    echo "GnuPG could not be found. Installing now..."
    brew install gnupg
fi

if ! command -v pinentry-mac &> /dev/null; then
    echo "Pinentry-Mac could not be found. Installing now..."
    brew install pinentry-mac
fi

# Create the ~/.gnupg directory if it doesn't exist
if [ ! -d "$HOME/.gnupg" ]; then
    mkdir $HOME/.gnupg
    chmod 700 $HOME/.gnupg
fi

# Create or edit gpg-agent.conf
echo "pinentry-program /usr/local/bin/pinentry-mac" > $HOME/.gnupg/gpg-agent.conf

# Add the necessary lines to the shell profile file
echo "export GPG_TTY=\$(tty)" >> $HOME/.bashrc
echo "gpg-connect-agent updatestartuptty /bye > /dev/null" >> $HOME/.bashrc

# Apply the changes
gpg-connect-agent reloadagent


