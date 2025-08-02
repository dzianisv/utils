#!/bin/bash
# Fixes "Installed Build Tools revision 33.0.0 is corrupted. Remove and install again using the SDK Manager.""

set -se
cd /Users/engineer/Library/Android/sdk/build-tools/33.0.0/
ln -snf d8 dx
cd lib
ln -snf d8.jar dx.jar