# 在 Django 启动时记录当前环境变量
import sys

from common.runtime_config_logger import log_current_env_vars


# 检查是否在运行 Django 管理命令
def should_record_config():
    # 检查是否在运行真正的服务器（排除 --help 等辅助命令）
    if len(sys.argv) >= 2:
        command = sys.argv[1]
        if command == 'runserver':
            # 检查是否有 --help 或其他标志
            if '--help' in sys.argv or '-h' in sys.argv:
                return False
            return True
        elif command in ['start', 'gunicorn']:
            return True
    return False


# 仅在运行服务器时记录配置
if should_record_config():
    log_current_env_vars()
