import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.client_apis.common import request_debug_log
from apps.db.models import Role, UserRole, GroupRole
from apps.db.service import RoleService, UserService

logger = logging.getLogger(__name__)


# ===================== 角色管理 =====================


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def role_list(request: HttpRequest) -> JsonResponse:
    """
    获取所有角色列表

    :param request: HTTP 请求对象
    :return: JSON 响应，形如 {"ok": true, "data": [...]}
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    roles = RoleService().list_roles()
    data = []
    for r in roles:
        data.append({
            'id': r.id,
            'name': r.name,
            'note': r.note,
            'is_default': r.is_default,
            'permission': r.permission,
            'user_count': UserRole.objects.filter(role=r).count(),
        })
    return JsonResponse({'ok': True, 'data': data})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def role_create(request: HttpRequest) -> JsonResponse:
    """
    创建角色（同步绑定全局原子权限）

    :param request: POST 参数包含 name, note(可选), permission(可选,整数)
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    name = (request.POST.get('name') or '').strip()
    note = (request.POST.get('note') or '').strip()
    try:
        permission = int(request.POST.get('permission', 0))
    except (TypeError, ValueError):
        permission = 0
    if not name:
        return JsonResponse({'ok': False, 'err_msg': '角色名称不能为空'}, status=400)
    if Role.objects.filter(name=name).exists():
        return JsonResponse({'ok': False, 'err_msg': '角色名称已存在'}, status=400)
    RoleService().create_role(name, note, permission)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def role_update(request: HttpRequest) -> JsonResponse:
    """
    更新角色（支持更新 permission）

    :param request: POST 参数包含 role_id, name(可选), note(可选), permission(可选)
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        role_id = int(request.POST.get('role_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    kwargs = {}
    name = request.POST.get('name')
    if name is not None:
        kwargs['name'] = name.strip()
    note = request.POST.get('note')
    if note is not None:
        kwargs['note'] = note.strip()
    perm_str = request.POST.get('permission')
    if perm_str is not None:
        try:
            kwargs['permission'] = int(perm_str)
        except (TypeError, ValueError):
            pass
    if not kwargs:
        return JsonResponse({'ok': False, 'err_msg': '无更新内容'}, status=400)
    role = RoleService().update_role(role_id, **kwargs)
    if not role:
        return JsonResponse({'ok': False, 'err_msg': '角色不存在'}, status=404)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def role_delete(request: HttpRequest) -> JsonResponse:
    """
    删除角色（default 角色不可删除）

    :param request: POST 参数包含 role_id
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        role_id = int(request.POST.get('role_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if not RoleService().delete_role(role_id):
        return JsonResponse({'ok': False, 'err_msg': '角色不存在或不可删除'}, status=400)
    return JsonResponse({'ok': True})


# ===================== 用户-角色 =====================


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def user_roles(request: HttpRequest) -> JsonResponse:
    """
    获取指定用户的角色列表

    :param request: GET 参数包含 username
    :return: JSON 响应，data 包含 roles（用户已分配）和 all_roles（所有角色）
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    username = (request.GET.get('username') or '').strip()
    if not username:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    user = UserService().get_user_by_name(username)
    if not user:
        return JsonResponse({'ok': False, 'err_msg': '用户不存在'}, status=404)
    role_service = RoleService()
    user_role_ids = set(
        UserRole.objects.filter(user=user).values_list('role_id', flat=True)
    )
    all_roles = [
        {'id': r.id, 'name': r.name, 'assigned': r.id in user_role_ids}
        for r in role_service.list_roles()
    ]
    return JsonResponse({'ok': True, 'data': {'username': username, 'roles': all_roles}})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def user_role_assign(request: HttpRequest) -> JsonResponse:
    """
    为用户分配角色

    :param request: POST 参数包含 username, role_id
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    username = (request.POST.get('username') or '').strip()
    try:
        role_id = int(request.POST.get('role_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if not username or not role_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    RoleService().assign_role_to_user(username, role_id)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def user_role_remove(request: HttpRequest) -> JsonResponse:
    """
    移除用户的角色

    :param request: POST 参数包含 username, role_id
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    username = (request.POST.get('username') or '').strip()
    try:
        role_id = int(request.POST.get('role_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if not username or not role_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    RoleService().remove_role_from_user(username, role_id)
    return JsonResponse({'ok': True})


# ===================== 用户组-角色 =====================


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def group_roles(request: HttpRequest) -> JsonResponse:
    """
    获取指定用户组的角色列表

    :param request: GET 参数包含 group_id
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        group_id = int(request.GET.get('group_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    group = Group.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({'ok': False, 'err_msg': '用户组不存在'}, status=404)

    role_service = RoleService()
    assigned_ids = set(
        GroupRole.objects.filter(group=group).values_list('role_id', flat=True)
    )
    all_roles = [
        {'id': r.id, 'name': r.name, 'assigned': r.id in assigned_ids}
        for r in role_service.list_roles()
    ]
    return JsonResponse({'ok': True, 'data': {'group_id': group_id, 'group_name': group.name, 'roles': all_roles}})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def group_role_assign(request: HttpRequest) -> JsonResponse:
    """
    为用户组分配角色

    :param request: POST 参数包含 group_id, role_id
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        group_id = int(request.POST.get('group_id', 0))
        role_id = int(request.POST.get('role_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if not group_id or not role_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    RoleService().assign_role_to_group(group_id, role_id)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def group_role_remove(request: HttpRequest) -> JsonResponse:
    """
    移除用户组的角色

    :param request: POST 参数包含 group_id, role_id
    :return: JSON 响应
    :rtype: JsonResponse
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    try:
        group_id = int(request.POST.get('group_id', 0))
        role_id = int(request.POST.get('role_id', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if not group_id or not role_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    RoleService().remove_role_from_group(group_id, role_id)
    return JsonResponse({'ok': True})
