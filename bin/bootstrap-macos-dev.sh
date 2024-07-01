#!/bin/sh
# This scripts install required packages on your dev machine

set -eu

require_dependency_brew() {
    command=$1
    package=$2
    if ! command -v "$command"; then
        brew install -q "$package"
    fi
}

require_dependency_brew_cask() {
    command=$1
    package=$2
    if ! command -v "${command}"; then
        brew install --cask  -q "${package}"
    fi
}

PROFILE=~/.zshrc


require_profile() {
  env=$1
  if ! grep "$env" "${PROFILE}"; then
    echo "$env" >> "${PROFILE}"
    $env
  fi
}

if ! command -v brew; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

require_dependency_brew python3 python3
require_dependency_brew pipenv pipenv
require_dependency_brew bpython bpython
require_dependency_brew pylint pylint

require_dependency_brew git-lfs git-lfs

require_dependency_brew kubectl kubectl
require_dependency_brew jq jq
require_dependency_brew yq python-yq
require_dependency_brew sed gnu-sed

require_dependency_brew go golang
require_dependency_brew gpg gnupg
require_dependency_brew ykman ykman

require_dependency_brew vim vim
require_dependency_brew_cask code visual-studio-code
require_dependency_brew_cask flameshot flameshot


require_dependency_brew npm npm

if [ -z "$(git config user.email)" ]; then
    echo "Run\n\tgit config --global user.email <email>\n\tgit  config --global user.name <name>"
    exit 1
fi

if [ -r ~/.zshrc ]; then echo 'export GPG_TTY=$(tty)' >> ~/.zshrc; \
    else echo 'export GPG_TTY=$(tty)' >> ~/.zprofile; fi

if [ -r ~/.bash_profile ]; then echo 'export GPG_TTY=$(tty)' >> ~/.bash_profile; \
    else echo 'export GPG_TTY=$(tty)' >> ~/.profile; fi

