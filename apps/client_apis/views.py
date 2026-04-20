import json
import logging
import traceback

from django.db import OperationalError
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.client_apis.common import check_login, request_debug_log
from apps.db.models import DevicePermission
from apps.db.service import (
    HeartBeatService, PeerInfoService, TokenService, UserService,
    LoginClientService, DeviceGroupService, PermissionService,
    DeviceGroupPeerService, )
from common.utils import get_local_time, str2bool

logger = logging.getLogger(__name__)


@request_debug_log
@require_http_methods(["GET"])
def time_test(request: HttpRequest):
    """
    测试时间存储是否使用服务器本地时间

    :param request: HTTP请求对象
    :return: 包含当前时间和时区信息的JSON响应
    """
    now = timezone.now()
    local_time = timezone.localtime(now)

    return JsonResponse({
        'utc_time': now.isoformat(),
        'local_time': local_time.isoformat(),
        'timezone': str(local_time.tzinfo)
    })


@request_debug_log
@require_http_methods(["POST"])
def heartbeat(request: HttpRequest):
    try:
        request_data = json.loads(request.body.decode('utf-8'))
        uuid = request_data.get('uuid')
        peer_id = request_data.get('id')
        modified_at = request_data.get('modified_at', get_local_time())
        ver = request_data.get('ver')

        if not uuid or not peer_id:
            logger.warning(f"心跳请求缺少必要参数: uuid={uuid}, peer_id={peer_id}")
            return HttpResponse(status=400)

        HeartBeatService().update(
            uuid=uuid,
            peer_id=peer_id,
            modified_at=modified_at,
            ver=ver,
        )

        TokenService().renew_token_if_alive(uuid)

        return HttpResponse(status=200)
    except json.JSONDecodeError as e:
        logger.error(f"心跳请求JSON解析失败: {e}")
        return HttpResponse(status=400)
    except OperationalError as e:
        logger.warning(f"心跳请求数据库繁忙: {e}")
        return HttpResponse(status=503)
    except Exception as e:
        logger.error(f"心跳请求处理失败: {e}")
        logger.error(traceback.format_exc())
        return HttpResponse(status=500)


@request_debug_log
@require_http_methods(["POST"])
def sysinfo(request: HttpRequest):
    try:
        body = json.loads(request.body.decode('utf-8'))
        uuid = body.get('uuid')

        PeerInfoService().update(
            uuid=uuid,
            peer_id=body.get('id'),
            cpu=body.get('cpu'),
            device_name=body.get('hostname'),
            memory=body.get('memory'),
            os=body.get('os'),
            username=body.get('username') or body.get('hostname'),
            version=body.get('version'),
        )

        return HttpResponse('SYSINFO_UPDATED', status=200)
    except json.JSONDecodeError as e:
        logger.error(f"系统信息请求JSON解析失败: {e}")
        return HttpResponse(status=400)
    except OperationalError as e:
        logger.warning(f"系统信息请求数据库繁忙: {e}")
        return HttpResponse(status=503)
    except Exception as e:
        logger.error(f"系统信息请求处理失败: {e}")
        logger.error(traceback.format_exc())
        return HttpResponse(status=500)


@request_debug_log
@require_http_methods(["POST"])
def login(request: HttpRequest):
    """
    处理用户登录请求
    :param request: HTTP请求对象
    :return: JSON响应对象
    """
    token_service = TokenService(request=request)
    body = token_service.request_body

    username = body.get('username')
    password = body.get('password')
    uuid = body.get('uuid')
    device_info = body.get('deviceInfo', {})
    platform = device_info.get('os')  # 设备端别
    client_type = device_info.get('type')
    client_name = device_info.get('name')

    user = UserService().get_user_by_name(username=username)
    if not user or not user.check_password(password):
        return JsonResponse({'error': '用户名或密码错误'}, status=401)

    token = token_service.create_token(username, uuid)

    LoginClientService().update_login_status(
        uuid=uuid,
        username=user,
        peer_id=body.get('id'),
        client_name=client_name,
        platform=platform,
        client_type=client_type,
    )

    return JsonResponse(
        {
            'access_token': token,
            'type': 'access_token',
            'user': {
                'name': user.username,
                'email': user.email or '',
                'note': '',
                'status': 1 if user.is_active else 0,
                'is_admin': user.is_superuser,
                'info': {},
            }
        }
    )


@request_debug_log
@require_http_methods(["POST"])
@check_login
def logout(request: HttpRequest):
    token_service = TokenService(request=request)
    token = token_service.authorization
    user_info = token_service.user_info
    body = token_service.request_body

    uuid = body.get('uuid')

    token_service.delete_token(token)

    # 更新登出状态
    LoginClientService().update_logout_status(
        uuid=uuid,
        username=user_info,
        peer_id=body.get('id'),
    )
    #
    # LogService().create_log(
    #     username=user_info,
    #     uuid=uuid,
    #     log_type='logout',
    #     log_message=f'用户 {user_info} 退出登录'
    # )
    return JsonResponse({'code': 1})


@request_debug_log
@require_http_methods(["POST"])
@check_login
def current_user(request: HttpRequest):
    """
    获取当前用户信息
    :param request:
    :return:
    """
    token_service = TokenService(request=request)
    token = token_service.authorization
    user_info = token_service.user_info

    return JsonResponse(
        {
            'name': user_info.username,
            'email': user_info.email or '',
            'note': '',
            'status': 1 if user_info.is_active else 0,
            'is_admin': user_info.is_superuser,
            'info': {},
            'access_token': token,
            'type': 'access_token',
        }
    )


@request_debug_log
@require_http_methods(["GET"])
@check_login
def users(request: HttpRequest):
    """
    获取所有用户信息
    :param request:
    :return:
    """
    page = int(request.GET.get('current', 1))
    page_size = int(request.GET.get('pageSize', 10))
    status = str2bool(request.GET.get('status') or True)
    token_service = TokenService(request=request)
    user_info = token_service.user_info
    if user_info.is_superuser:
        result = UserService().get_list_by_status(is_active=status, page=page, page_size=page_size)['results']
    else:
        result = [user_info]

    user_list = [
        {
            "name": user.username,
            "email": user.email or '',
            "note": "",
            "is_admin": user.is_superuser,
            "status": 1 if user.is_active else 0,
            "info": {}
        } for user in result
    ]

    return JsonResponse(
        {
            'total': len(user_list),
            'data': user_list
        }
    )


@request_debug_log
@require_http_methods(["GET"])
@check_login
def peers(request: HttpRequest):
    """
    展示当前用户有查看权限的设备信息

    :param request: HTTP 请求对象
    :return: JSON 响应，形如 {"total": N, "data": [...]}
    :rtype: JsonResponse
    """
    token_service = TokenService(request=request)
    user_info = token_service.user_info

    # Super admin 不校验权限，直接返回所有设备
    if not user_info.is_superuser:
        perm_service = PermissionService()
        if not perm_service.has_perm(user_info, DevicePermission.VIEW):
            return JsonResponse({'total': 0, 'data': []})

    dgp_service = DeviceGroupPeerService()
    client_list = list(PeerInfoService().get_list())

    data = []
    for client in client_list:
        groups = dgp_service.get_groups_for_peer(client)
        group_name = groups[0].name if groups else ""
        data.append({
            "id": client.peer_id,
            "info": {
                "device_name": client.device_name,
                "os": client.os,
                "username": client.username,
            },
            "status": 1,
            "user_name": user_info.username,
            "device_group_name": group_name,
            "note": client.note or "",
        })

    return JsonResponse({
        'total': len(data),
        'data': data
    })


@request_debug_log
@require_http_methods(["GET"])
@check_login
def device_group_accessible(request):
    """
    获取当前用户可访问的设备组列表

    :param request: HTTP 请求对象
    :return: JSON 响应，形如 {"total": N, "data": [{"name": "..."}]}
    """
    try:
        current = int(request.GET.get('current', 1))
    except (TypeError, ValueError):
        current = 1
    try:
        page_size = int(request.GET.get('pageSize', 100))
    except (TypeError, ValueError):
        page_size = 100

    token_service = TokenService(request=request)
    user_info = token_service.user_info

    groups = DeviceGroupService().get_accessible_groups(user_info)
    total = len(groups)
    start = (current - 1) * page_size
    page_data = groups[start:start + page_size]

    return JsonResponse({
        'total': total,
        'data': [{'name': g.name} for g in page_data]
    })
