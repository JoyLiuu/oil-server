#!/bin/bash

cd /opt/docker/oil-server
docker build -t wx-oil-server .
docker compose down
docker rmi wx-oil-server
docker compose up -d
docker logs -f wx-oil-server
