#/bin/sh
set -eu

brew install ffmpeg mpv
brew install --cask brave-browser
brew install --cask visual-studio-code
brew install --cask libreoffice
brew install --cask qbittorrent
brew install --cask resilio-sync
brew install --cask nitroshare # cross-OS file sharing
brew intall --cask lulu # firewall
brew install iproute2mac

sudo ports install gocryptfs
sudo ln -fsn /opt/local/Library/Filesystems/macfuse.fs /Library/Filesystems/macfuse.fs
