#!/bin/bash
BASE=https://raw.githubusercontent.com/daryadavydik-dotcom/kp-bot/master
cd /opt/kp-bot
wget -qO handlers.py $BASE/handlers.py
wget -qO logic/build_kp.py $BASE/logic/build_kp.py
wget -qO logic/client_data.py $BASE/logic/client_data.py
wget -qO logic/merge_answer.py $BASE/logic/merge_answer.py
systemctl restart kp-bot
echo "Done. Status:"
systemctl status kp-bot --no-pager -l
