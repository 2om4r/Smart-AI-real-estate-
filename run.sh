#!/bin/bash
# ════════════════════════════════════════════════════════════
# Smart Estate Oman — Quick Run Script
# يُشَغِّل الـ venv و Flask معاً، ويُظهر IP الـ Mac للجوَّال
# ════════════════════════════════════════════════════════════

cd "$(dirname "$0")"

# 1. اعرض IP الـ Mac
MAC_IP=$(ifconfig | grep "inet " | grep -v "127.0.0.1" | head -1 | awk '{print $2}')
WIFI=$(networksetup -getairportnetwork en0 2>/dev/null | sed 's/Current Wi-Fi Network: //')

echo "════════════════════════════════════════════"
echo " 🏘️  Smart Estate Oman — Starting Server"
echo "════════════════════════════════════════════"
echo " 📡 Wi-Fi:  $WIFI"
echo " 💻 Mac:    http://127.0.0.1:5002"
echo " 📱 Mobile: http://$MAC_IP:5002"
echo "════════════════════════════════════════════"
echo

# 2. فَعِّل الـ venv
if [ ! -d ".venv" ]; then
    echo "❌ .venv folder not found! Run: python3 -m venv .venv"
    exit 1
fi
source .venv/bin/activate

# 3. شَغِّل Flask
flask run --host=0.0.0.0 --port=5002
