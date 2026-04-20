import os

from base import DATA_PATH
from common.env import PublicConfig

sqlite3_config = {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': os.path.join(DATA_PATH, 'db.sqlite3'),
    'OPTIONS': {
        'timeout': 30,
    }
}

mysql_config = {
    'ENGINE': 'django.db.backends.mysql',
    'NAME': os.getenv('MYSQL_DATABASE', 'rustdesk'),
    'USER': os.getenv('MYSQL_USER', 'root'),
    'PASSWORD': os.getenv('MYSQL_PASSWORD', ''),
    'HOST': os.getenv('MYSQL_HOST', 'localhost'),
    'PORT': os.getenv('MYSQL_PORT', '3306'),
    'OPTIONS': {
        'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
    },
}

postgresql_config = {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': os.getenv('POSTGRES_DB', 'rustdesk'),
    'USER': os.getenv('POSTGRES_USER', 'postgres'),
    'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
    'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
    'PORT': os.getenv('POSTGRES_PORT', '5432'),
}


def db_config():
    """
    根据环境变量返回数据库配置
    
    :return: 数据库配置字典
    """
    db_type = PublicConfig.DB_TYPE

    if db_type == 'sqlite3':
        DATA_PATH.mkdir(exist_ok=True, parents=True)
        return sqlite3_config
    elif db_type == 'mysql':
        return mysql_config
    elif db_type == 'postgresql':
        return postgresql_config
    else:
        # 默认使用 sqlite3
        DATA_PATH.mkdir(exist_ok=True, parents=True)
        return sqlite3_config
