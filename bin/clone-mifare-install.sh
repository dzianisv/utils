#!/bin/bash
set -e

echo "🛠️ Installing dependencies via Homebrew..."
brew install libusb pkg-config autoconf automake libtool git cmake

WORKDIR="$HOME/mifare-tools"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

# Install libnfc
if [ ! -d "libnfc" ]; then
  echo "📥 Cloning libnfc..."
  git clone https://github.com/nfc-tools/libnfc.git
fi

echo "⚙️ Building libnfc..."
cd libnfc
./bootstrap
./configure --prefix=/usr/local --sysconfdir=/usr/local/etc
make -j$(sysctl -n hw.ncpu)
sudo make install
sudo mkdir -p /usr/local/etc/nfc
cd ..

# Install mfoc
if [ ! -d "mfoc" ]; then
  echo "📥 Cloning mfoc..."
  git clone https://github.com/nfc-tools/mfoc.git
fi

echo "⚙️ Building mfoc..."
cd mfoc
autoreconf -vis
./configure
make -j$(sysctl -n hw.ncpu)
sudo make install
cd ..

# Install mfcuk
if [ ! -d "mfcuk" ]; then
  echo "📥 Cloning mfcuk..."
  git clone https://github.com/nfc-tools/mfcuk.git
fi

echo "⚙️ Building mfcuk..."
cd mfcuk
autoreconf -vis
./configure
make -j$(sysctl -n hw.ncpu)
sudo make install
cd ..

echo "✅ All tools installed successfully!"
echo "🔁 Reminder: Connect your PN532 reader via USB and place a MIFARE Classic card near it."

echo "👉 To test, run:"
echo "  nfc-list"


