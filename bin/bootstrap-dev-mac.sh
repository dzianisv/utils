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
require_dependency_brew fzf fzf
require_dependency_brew kubie kubie
require_dependency_brew tsh teleport
require_dependency_brew stern stern
require_dependency_brew jq jq
require_dependency_brew yq python-yq
require_dependency_brew jb jsonnet-bundler
require_dependency_brew sed gnu-sed

require_dependency_brew go golang
require_dependency_brew gpg gnupg
require_dependency_brew pinentry-mac pinentry-mac
require_dependency_brew ykman ykman

require_dependency_brew vim vim
require_dependency_brew_cask code visual-studio-code
require_dependency_brew_cask flameshot flameshot
require_dependency_brew_cask op 1password-cli

# require_dependency_brew helm helm@2

if ! command -v helm; then
    require_profile 'export PATH="/usr/local/opt/helm@2/bin:$PATH"'
fi

require_dependency_brew aswcli awscli
require_dependency_brew aws-vault aws-vault
echo 'source <( aws-vault --completion-script-bash )' >> ~/.bashrc
echo 'source <( aws-vault --completion-script-bash )' >> ~/.zshrc

require_dependency_brew npm npm
# install nvm: https://github.com/nvm-sh/nvm#install--update-script
if ! command -v nvm; then
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
    require_profile 'export NVM_DIR="$HOME/.nvm"'
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
fi

if ! command -v npm; then
    npm i -g npm
fi

if ! grep "pinentry-program /usr/local/bin/pinentry-mac" ~/.gnupg/gpg-agent.conf; then
    mkdir -p ~/.gnupg/
    echo "pinentry-program /usr/local/bin/pinentry-mac" >> ~/.gnupg/gpg-agent.conf
    gpgconf --kill gpg-agent  && gpgconf --launch gpg-agent
fi

if [ -z "$(git config user.email)" ]; then
    echo "Run\n\tgit config --global user.email <email>\n\tgit  config --global user.name <name>"
    exit 1
fi

KEY_ID=$(gpg --list-keys $(git config user.email) | grep "pub" -A 1 | tail -1 | tr -d '\r\n\t ')
git config --global user.signkey "${KEY_ID}"
git config --global commit.gpgsign true
