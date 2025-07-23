#!/bin/sh

TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is not set}

# convert "$@" into a url quoted string
TEXT=$(printf "%s" "$*" | jq -sRr @uri)

curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage?chat_id=$TELEGRAM_CHAT_ID&text=$TEXT"
