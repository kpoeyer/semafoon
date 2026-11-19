#!/bin/bash
set -e

echo "==================================================="
echo " Installatie P2000 & Semafoon Web Decoder"
echo "==================================================="

echo "[1/5] Systeem pakketten installeren..."
sudo apt-get update
sudo apt-get install -y rtl-sdr multimon-ng python3 python3-venv python3-pip coreutils psmisc

echo "[2/5] DVB-T TV-drivers blokkeren..."
if [ ! -f /etc/modprobe.d/blacklist-rtl.conf ]; then
    sudo bash -c 'cat <<EOF > /etc/modprobe.d/blacklist-rtl.conf
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
EOF'
    sudo rmmod dvb_usb_rtl28xxu 2>/dev/null || true
fi

echo "[3/5] Python Virtual Environment aanmaken..."
INSTALL_DIR=$(pwd)
python3 -m venv "$INSTALL_DIR/venv"

echo "[4/5] Python pakketten installeren..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "[5/5] Achtergrond-service (systemd) instellen..."
CURRENT_USER=$(whoami)

sudo bash -c "cat <<EOF > /etc/systemd/system/p2000-web.service
[Unit]
Description=P2000 en Semafoon Web Decoder
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

sudo usermod -a -G plugdev $CURRENT_USER
sudo systemctl daemon-reload
sudo systemctl enable p2000-web.service
sudo systemctl restart p2000-web.service

IP_ADDR=$(hostname -I | awk '{print $1}')

echo "==================================================="
echo " ✅ Installatie Voltooid!"
echo "==================================================="
echo "Open je browser en ga naar: http://$IP_ADDR:5000"
echo "==================================================="
