import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.client_apis.common import request_debug_log
from apps.db.service import GroupService, UserService

logger = logging.getLogger(__name__)


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def group_list(request: HttpRequest) -> JsonResponse:
    """
    获取用户组列表（JSON，支持搜索）

    :param request: GET 参数包含 q(可选)
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true, "data": [...]}
    :rtype: JsonResponse
    """
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    q = (request.GET.get('q') or '').strip()
    group_service = GroupService()
    groups = group_service.get_groups_qs(q=q)
    data = []
    for g in groups:
        data.append({
            'id': g.id,
            'name': g.name,
            'member_count': group_service.count_group_members(g.id),
        })
    return JsonResponse({'ok': True, 'data': data})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def group_create(request: HttpRequest) -> JsonResponse:
    """
    创建用户组

    :param request: POST 参数包含 name
    :type request: HttpRequest
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    name = (request.POST.get('name') or '').strip()
    if not name:
        return JsonResponse({'ok': False, 'err_msg': '用户组名称不能为空'}, status=400)

    group_service = GroupService()
    if group_service.get_group_by_name(name):
        return JsonResponse({'ok': False, 'err_msg': '用户组名称已存在'}, status=400)
    group_service.create_group(name)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def group_update(request: HttpRequest) -> JsonResponse:
    """
    更新用户组名称

    :param request: POST 参数包含 group_id, name
    :type request: HttpRequest
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        group_id = int(request.POST.get('group_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    name = (request.POST.get('name') or '').strip()
    if not name:
        return JsonResponse({'ok': False, 'err_msg': '用户组名称不能为空'}, status=400)

    group_service = GroupService()
    existing = group_service.get_group_by_name(name)
    if existing and existing.id != group_id:
        return JsonResponse({'ok': False, 'err_msg': '用户组名称已存在'}, status=400)

    group = group_service.update_group(group_id, name)
    if not group:
        return JsonResponse({'ok': False, 'err_msg': '用户组不存在'}, status=404)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def group_delete(request: HttpRequest) -> JsonResponse:
    """
    删除用户组（Default 组不可删除，组内成员自动回落到 Default 组）

    :param request: POST 参数包含 group_id
    :type request: HttpRequest
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        group_id = int(request.POST.get('group_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if not GroupService().delete_group(group_id):
        return JsonResponse({'ok': False, 'err_msg': '用户组不存在或不可删除'}, status=400)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def group_members(request: HttpRequest) -> JsonResponse:
    """
    获取指定用户组的成员列表

    :param request: GET 参数包含 group_id
    :type request: HttpRequest
    :return: JSON 响应，data 包含成员列表
    :rtype: JsonResponse
    """
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        group_id = int(request.GET.get('group_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    members = GroupService().get_group_members(group_id)
    data = [
        {'id': m.id, 'username': m.username, 'full_name': m.get_full_name() or '-'}
        for m in members
    ]
    return JsonResponse({'ok': True, 'data': data})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def group_add_member(request: HttpRequest) -> JsonResponse:
    """
    添加用户到指定用户组

    :param request: POST 参数包含 group_id, username
    :type request: HttpRequest
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        group_id = int(request.POST.get('group_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    username = (request.POST.get('username') or '').strip()
    if not group_id or not username:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    group_service = GroupService()
    group = Group.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({'ok': False, 'err_msg': '用户组不存在'}, status=404)
    user = UserService().get_user_by_name(username)
    if not user:
        return JsonResponse({'ok': False, 'err_msg': '用户不存在'}, status=404)
    group_service.add_user_to_group(username, group_name=group.name)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def group_remove_member(request: HttpRequest) -> JsonResponse:
    """
    从用户组中移除用户（回落到 Default 组）

    :param request: POST 参数包含 group_id, user_id
    :type request: HttpRequest
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        group_id = int(request.POST.get('group_id', 0))
        user_id = int(request.POST.get('user_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if not group_id or not user_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if not GroupService().remove_user_from_group(user_id, group_id):
        return JsonResponse({'ok': False, 'err_msg': '用户不在该组中'}, status=400)
    return JsonResponse({'ok': True})
