#!/bin/bash

cd /opt/oil-server
docker compose down
docker rmi oil-server-oil-server
docker rmi nginx:alpine
rm -rf ssl
./deploy.sh
./setup-ssl.sh
