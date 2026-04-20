from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.client_apis.common import request_debug_log
from apps.db.service import UserService


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def update_user(request: HttpRequest) -> JsonResponse:
    """
    更新用户基础信息（仅限管理员）

    :param request: POST，包含 username, full_name(可选), email(可选), is_staff(可选: '1'/'0')
    :return: {"ok": true}
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    username = (request.POST.get('username') or '').strip()
    if not username:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    user_service = UserService()
    user = user_service.get_user_by_name(username)
    if not user:
        return JsonResponse({'ok': False, 'err_msg': '用户不存在'}, status=404)

    full_name = (request.POST.get('full_name') or '').strip()
    email = (request.POST.get('email') or '').strip()
    is_staff_raw = request.POST.get('is_staff')

    kwargs = {}
    if full_name != '':
        kwargs['first_name'] = full_name
        kwargs['last_name'] = ''
    if email != '':
        kwargs['email'] = email

    # 不允许用户修改自己的管理员权限
    if is_staff_raw is not None:
        if username == request.user.username:
            return JsonResponse({'ok': False, 'err_msg': '不能修改自己的管理员权限'}, status=400)
        kwargs['is_staff'] = (str(is_staff_raw).strip() == '1')

    if kwargs:
        user_service.update_user(username, **kwargs)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def reset_user_password(request: HttpRequest) -> JsonResponse:
    """
    重置用户密码（仅限管理员）

    :param request: POST，包含 username, password1, password2
    :return: {"ok": true}
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    username = (request.POST.get('username') or '').strip()
    password1 = (request.POST.get('password1') or '').strip()
    password2 = (request.POST.get('password2') or '').strip()
    if not username or not password1 or not password2:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    if password1 != password2:
        return JsonResponse({'ok': False, 'err_msg': '两次密码不一致'}, status=400)
    if len(password1) < 6:
        return JsonResponse({'ok': False, 'err_msg': '密码长度至少为6位'}, status=400)

    user_service = UserService()
    user = user_service.get_user_by_name(username)
    if not user:
        return JsonResponse({'ok': False, 'err_msg': '用户不存在'}, status=404)
    user_service.set_password(password1, username=username)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def delete_user(request: HttpRequest) -> JsonResponse:
    """
    删除用户（软删除，将is_active置为False，仅限管理员）

    :param request: POST，包含 username
    :return: {"ok": true}
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)
    username = (request.POST.get('username') or '').strip()
    if not username:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    # 不能删除自己
    if username == request.user.username:
        return JsonResponse({'ok': False, 'err_msg': '不能删除自己'}, status=400)

    user_service = UserService()
    if not user_service.delete_user_soft(username):
        return JsonResponse({'ok': False, 'err_msg': '用户不存在或已被删除'}, status=404)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def create_user(request: HttpRequest) -> JsonResponse:
    """
    创建新用户（仅限管理员）

    :param request: POST，包含 username, password1, password2, full_name(可选), email(可选), is_staff(可选: '1'/'0')
    :return: {"ok": true}
    """
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'err_msg': '无权限'}, status=403)

    username = (request.POST.get('username') or '').strip()
    password1 = (request.POST.get('password1') or '').strip()
    password2 = (request.POST.get('password2') or '').strip()
    full_name = (request.POST.get('full_name') or '').strip()
    email = (request.POST.get('email') or '').strip()
    is_staff_raw = request.POST.get('is_staff')

    # 参数校验
    if not username or not password1 or not password2:
        return JsonResponse({'ok': False, 'err_msg': '用户名和密码不能为空'}, status=400)
    if password1 != password2:
        return JsonResponse({'ok': False, 'err_msg': '两次密码不一致'}, status=400)
    if len(password1) < 6:
        return JsonResponse({'ok': False, 'err_msg': '密码长度至少为6位'}, status=400)

    user_service = UserService()

    # 检查用户名是否已存在（包括软删除的用户）
    if user_service.username_exists(username):
        return JsonResponse({'ok': False, 'err_msg': '用户名已存在'}, status=400)

    # 检查邮箱是否已存在（如果提供了邮箱）
    if email and user_service.email_exists(email):
        return JsonResponse({'ok': False, 'err_msg': '邮箱已被使用'}, status=400)

    # 确定管理员权限
    is_staff = (str(is_staff_raw).strip() == '1') if is_staff_raw is not None else False

    try:
        user = user_service.create_user(
            username=username,
            password=password1,
            email=email,
            is_staff=is_staff,
            is_superuser=False,
            is_active=True,
            group=None
        )

        if full_name:
            user_service.update_user(username, first_name=full_name, last_name='')

        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'err_msg': f'创建用户失败: {str(e)}'}, status=500)
