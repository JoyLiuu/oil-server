#!/bin/bash

cd /opt/oil-server
docker compose down
docker rmi oil-server-oil-server
docker rmi nginx:alpine
./deploy.sh
./setup-ssl.sh
