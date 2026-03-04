#!/bin/bash
set -euo pipefail

# 准备运行目录
mkdir -p ./logs ./data

# 数据库迁移
#python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput

exec gunicorn rustdesk_api.wsgi:application -c gunicorn.conf.py 
