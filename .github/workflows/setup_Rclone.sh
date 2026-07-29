#!/usr/bin/env bash

# setup cloudflare r2

 apt update
 apt install -y unzip
 curl https://rclone.org/install.sh | bash

 mkdir -p /mnt/r2/verdaccio
 grep -qxF "user_allow_other" /etc/fuse.conf || \
 echo "user_allow_other" | tee -a /etc/fuse.conf


tee /etc/systemd/system/rclone-verdaccio.service >/dev/null <<'EOF'
[Unit]
Description=Cloudflare R2 Mount (Verdaccio)
Documentation=https://rclone.org/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USERNAME
Group=$USERNAME

EnvironmentFile=/etc/rclone/verdaccio.env

ExecStart=/usr/bin/rclone mount \
    r2:verdaccio \
    /mnt/r2/verdaccio \
    --config=/home/$USERNAME/.config/rclone/rclone.conf \
    --allow-other \
    --dir-cache-time=72h \
    --vfs-cache-mode=writes \
    --poll-interval=15s

ExecStop=/bin/fusermount -u /mnt/r2/verdaccio

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF


 systemctl daemon-reload
 
 systemctl enable --now rclone-verdaccio

 echo "✅ Server setup completed"

exit
