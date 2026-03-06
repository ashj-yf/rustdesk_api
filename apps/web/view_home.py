import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import OperationalError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.client_apis.common import request_debug_log
from apps.db.models import DevicePermission, UserRole, GroupRole
from apps.db.service import (
    UserService, PeerInfoService, PersonalService,
    AliasService, HeartBeatService, ClientTagsService,
    PermissionService, GroupService,
)
from apps.web.view_personal import is_default_personal

logger = logging.getLogger(__name__)


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def home(request):
    """
    Web 首页：登录保护，依赖 Django 认证态（request.user）

    :param request: Http 请求对象
    :type request: HttpRequest
    :return: 首页或重定向响应
    :rtype: HttpResponse
    """
    username = getattr(request.user, 'username', '') or request.user.get_username()
    perm_flags = [
        {'key': k, 'value': v, 'label': DevicePermission.LABELS[v]}
        for k, v in [
            ('VIEW', DevicePermission.VIEW),
            ('EDIT', DevicePermission.EDIT),
            ('DELETE', DevicePermission.DELETE),
            ('CONNECT', DevicePermission.CONNECT),
        ]
    ]
    return render(request, 'home.html', context={
        'username': username,
        'perm_flags': perm_flags,
    })


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def nav_content(request: HttpRequest) -> HttpResponse:
    """
    返回侧边导航对应的局部模板内容（通过 GET 参数 key）

    :param request: Http 请求对象，需包含 GET 参数 key（如 nav-1/nav-2/nav-3）
    :type request: HttpRequest
    :return: 渲染后的 HTML 片段
    :rtype: HttpResponse
    :notes:
    - 仅支持预设键名，未知键名将返回简单的占位内容
    """
    key = request.GET.get('key', '').strip()
    key_to_template = {
        'nav-1': 'nav/nav-1.html',
        'nav-2': 'nav/nav-2.html',
        'nav-3': 'nav/nav-3.html',
        'nav-4': 'nav/nav-4.html',
    }
    template_name = key_to_template.get(key)
    if not template_name:
        return HttpResponse('<p class="content-empty">未匹配到内容</p>')
    # 根据不同导航项提供对应数据
    context = {}
    if key == 'nav-1':  # 首页
        # 分页参数
        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 20))
        except (TypeError, ValueError):
            page_size = 20

        user_service = UserService()
        peer_service = PeerInfoService()

        user_count = user_service.count_active_users()
        queryset = peer_service.get_all_ordered_qs()
        device_count = queryset.count()
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        devices = page_obj.object_list
        context.update({
            'user_count': user_count,
            'device_count': device_count,
            'devices': devices,
            'paginator': paginator,
            'page_obj': page_obj,
            'page_size': page_size,
        })
    elif key == 'nav-2':  # 设备管理
        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 20))
        except (TypeError, ValueError):
            page_size = 20

        q = (request.GET.get('q') or '').strip()
        os_param = (request.GET.get('os') or '').strip()
        status = (request.GET.get('status') or '').strip().lower()
        enabled = (request.GET.get('enabled') or '').strip().lower()
        sort = (request.GET.get('sort') or '').strip()
        tag_filter = (request.GET.get('tag') or '').strip()

        peer_service = PeerInfoService()
        tags_param = tag_filter if tag_filter else None
        base_qs = peer_service.get_device_list_qs(
            user=request.user, q=q, os_param=os_param,
            status=status, enabled=enabled, sort=sort,
            tags=tags_param
        )

        paginator = Paginator(base_qs, page_size)
        page_obj = paginator.get_page(page)
        devices = page_obj.object_list
        all_tags = peer_service.get_all_tags_for_user(request.user)

        context.update({
            'devices': devices,
            'paginator': paginator,
            'page_obj': page_obj,
            'page_size': page_size,
            'q': q,
            'os': os_param,
            'status': status,
            'enabled': enabled,
            'sort': sort,
            'tag_filter': tag_filter,
            'all_tags': all_tags,
        })
    elif key == 'nav-3':  # 用户管理
        tab = (request.GET.get('tab') or '').strip() or 'users'
        context['tab'] = tab

        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 20))
        except (TypeError, ValueError):
            page_size = 20

        if tab == 'groups':
            q = (request.GET.get('q') or '').strip()
            group_service = GroupService()
            group_qs = group_service.get_groups_qs(q=q)
            paginator = Paginator(group_qs, page_size)
            page_obj = paginator.get_page(page)
            groups = list(page_obj.object_list)

            group_ids = [g.id for g in groups]
            role_map = {}
            for gr in GroupRole.objects.filter(group_id__in=group_ids).select_related('role'):
                role_map.setdefault(gr.group_id, []).append(gr.role.name)
            for g in groups:
                g.member_count = group_service.count_group_members(g.id)
                g.role_names = ', '.join(role_map.get(g.id, []))

            context.update({
                'groups': groups,
                'group_paginator': paginator,
                'group_page_obj': page_obj,
                'group_q': q,
            })
        else:
            q = (request.GET.get('q') or '').strip()
            user_qs = UserService().get_active_users_qs(q=q)
            paginator = Paginator(user_qs, page_size)
            page_obj = paginator.get_page(page)
            users = list(page_obj.object_list)

            user_ids = [u.id for u in users]
            role_map = {}
            for ur in UserRole.objects.filter(user_id__in=user_ids).select_related('role'):
                role_map.setdefault(ur.user_id, []).append(ur.role.name)
            for u in users:
                u.role_names = ', '.join(role_map.get(u.id, []))

            context.update({
                'users': users,
                'paginator': paginator,
                'page_obj': page_obj,
                'page_size': page_size,
                'q': q,
            })
    elif key == 'nav-4':  # 地址簿
        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 20))
        except (TypeError, ValueError):
            page_size = 20
        q = (request.GET.get('q') or '').strip()
        personal_type = (request.GET.get('type') or '').strip()

        personal_service = PersonalService()
        alias_service = AliasService()

        personal_qs = personal_service.get_personals_by_creator(
            request.user, q=q, personal_type=personal_type
        )

        paginator = Paginator(personal_qs, page_size)
        page_obj = paginator.get_page(page)
        personals = list(page_obj.object_list)

        for personal in personals:
            personal.device_count = alias_service.count_by_personal(personal)
            personal.is_default = is_default_personal(personal, request.user)
            if personal.personal_name == f'{request.user.username}_personal':
                personal.display_name = '默认地址簿'
            else:
                personal.display_name = personal.personal_name

        context.update({
            'personals': personals,
            'paginator': paginator,
            'page_obj': page_obj,
            'page_size': page_size,
            'q': q,
            'personal_type': personal_type,
        })
    return render(request, template_name, context=context)


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def rename_alias(request: HttpRequest) -> JsonResponse:
    """
    重命名设备别名（创建或更新 Alias）

    :param request: Http 请求对象，POST 参数包含 peer_id, alias
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true}
    :rtype: JsonResponse
    :notes:
    - 别名基于用户的"默认地址簿"（如不存在则自动创建，私有）
    - 针对 (peer_id, 默认地址簿) 维度进行 upsert
    """
    peer_id = (request.POST.get('peer_id') or '').strip()
    alias_text = (request.POST.get('alias') or '').strip()
    if not peer_id or not alias_text:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    peer = PeerInfoService().get_peer_info_by_peer_id(peer_id)
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)

    if not PermissionService().has_perm(request.user, DevicePermission.EDIT):
        return JsonResponse({'ok': False, 'err_msg': '无权编辑该设备'}, status=403)

    personal = PersonalService().get_or_create_default_personal(request.user)
    AliasService().update_or_create_alias(peer, personal, alias_text)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def device_detail(request: HttpRequest) -> JsonResponse:
    """
    获取设备详情（peer 维度）

    :param request: Http 请求对象，GET 参数包含 peer_id
    :type request: HttpRequest
    :return: JSON 响应，包含 peer_id/username/hostname/alias/platform/tags
    :rtype: JsonResponse
    """
    peer_id = (request.GET.get('peer_id') or '').strip()
    if not peer_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    peer = PeerInfoService().get_peer_info_by_peer_id(peer_id)
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)

    if not PermissionService().has_perm(request.user, DevicePermission.VIEW):
        return JsonResponse({'ok': False, 'err_msg': '无权查看该设备'}, status=403)

    alias_text = AliasService().get_peer_alias_text(peer, request.user)
    tag_list = ClientTagsService().get_user_peer_tags(request.user, peer_id)

    data = {
        'peer_id': peer.peer_id,
        'username': peer.username,
        'hostname': peer.device_name,
        'alias': alias_text,
        'platform': peer.os,
        'tags': tag_list,
        'note': peer.note or '',
        'is_enabled': peer.is_enabled,
        'version': peer.version,
    }
    return JsonResponse({'ok': True, 'data': data})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def update_device(request: HttpRequest) -> JsonResponse:
    """
    内联更新设备信息（别名与标签）

    :param request: Http 请求对象，POST 参数：
        - peer_id: 设备ID（必填）
        - alias: 设备别名（可选，空则忽略）
        - tags: 设备标签（可选，逗号分隔；空字符串表示清空）
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true}
    :rtype: JsonResponse
    :notes:
    - 别名写入当前用户的"默认地址簿"（不存在则创建）
    - 标签写入 ClientTags（当前用户 + 默认地址簿 guid 作用域）
    """
    peer_id = (request.POST.get('peer_id') or '').strip()
    if not peer_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    peer = PeerInfoService().get_peer_info_by_peer_id(peer_id)
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)

    if not PermissionService().has_perm(request.user, DevicePermission.EDIT):
        return JsonResponse({'ok': False, 'err_msg': '无权编辑该设备'}, status=403)

    alias_text = request.POST.get('alias')
    tags_str = request.POST.get('tags')

    personal = PersonalService().get_or_create_default_personal(request.user)
    alias_service = AliasService()
    client_tags_service = ClientTagsService()

    # 更新别名（当 alias 参数存在时）
    if alias_text is not None:
        alias_text = alias_text.strip()
        if alias_text:
            alias_service.update_or_create_alias(peer, personal, alias_text)
        else:
            alias_service.delete_alias_by_peer_and_personal(peer, personal)

    # 更新标签（当 tags 参数存在时）
    if tags_str is not None:
        # 归一化标签：逗号分隔，去空白、去重，保持顺序
        parts = [p.strip() for p in tags_str.split(',')] if tags_str is not None else []
        parts = [p for p in parts if p]
        seen = set()
        uniq = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        joined = ', '.join(uniq)
        if joined:
            client_tags_service.update_or_create_client_tag(
                request.user, peer_id, personal, joined
            )
        else:
            client_tags_service.delete_client_tag(request.user, peer_id, personal)

    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def device_statuses(request: HttpRequest) -> JsonResponse:
    """
    批量获取设备在线状态（仅查询，不修改会话）

    :param request: Http 请求对象，JSON body 参数：
        - ids: 逗号分隔的设备ID列表，如 "id1,id2,id3"
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true, "data": {"<peer_id>": {"is_online": true/false}}}
    :rtype: JsonResponse
    :notes:
        - 前端应在请求头携带 ``X-Session-No-Renew: 1``，以避免该轮询请求"续命"会话
        - 仅执行只读查询，不做任何写操作
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': True, 'data': {}})
    raw_ids = (body.get('ids') or '').strip()
    if not raw_ids:
        return JsonResponse({'ok': True, 'data': {}})
    peer_ids = [p.strip() for p in raw_ids.split(',') if p.strip()]
    if not peer_ids:
        return JsonResponse({'ok': True, 'data': {}})
    peer_ids = peer_ids[:500]

    online_set = HeartBeatService().get_online_peer_ids(peer_ids, timeout_seconds=60)
    data = {pid: {'is_online': (pid in online_set)} for pid in peer_ids}
    return JsonResponse({'ok': True, 'data': data})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def delete_device(request: HttpRequest) -> JsonResponse:
    """
    删除设备（单个或批量）

    :param request: Http 请求对象，POST 参数包含 peer_ids（逗号分隔）
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true, "count": N}
    :rtype: JsonResponse
    """
    raw = (request.POST.get('peer_ids') or '').strip()
    if not raw:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    peer_ids = [p.strip() for p in raw.split(',') if p.strip()]
    if not peer_ids:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    perm_service = PermissionService()
    if not perm_service.has_perm(request.user, DevicePermission.DELETE):
        return JsonResponse({'ok': False, 'err_msg': '无权删除设备'}, status=403)

    peer_service = PeerInfoService()

    try:
        count = peer_service.delete_peers(peer_ids)
    except OperationalError as e:
        logger.warning(f"删除设备数据库繁忙: {e}")
        return JsonResponse({'ok': False, 'err_msg': '数据库繁忙，请稍后重试'}, status=503)

    return JsonResponse({'ok': True, 'count': count})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def toggle_device(request: HttpRequest) -> JsonResponse:
    """
    启用/禁用设备（单个或批量）

    :param request: Http 请求对象，POST 参数：
        - peer_ids: 逗号分隔的设备ID列表
        - enabled: "true" 或 "false"
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true, "count": N}
    :rtype: JsonResponse
    """
    raw = (request.POST.get('peer_ids') or '').strip()
    enabled_str = (request.POST.get('enabled') or '').strip().lower()
    if not raw or enabled_str not in ('true', 'false'):
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    peer_ids = [p.strip() for p in raw.split(',') if p.strip()]
    if not peer_ids:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    if not PermissionService().has_perm(request.user, DevicePermission.EDIT):
        return JsonResponse({'ok': False, 'err_msg': '无权操作设备'}, status=403)

    enabled = enabled_str == 'true'
    count = peer_service.toggle_peers(peer_ids, enabled)
    return JsonResponse({'ok': True, 'count': count})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def update_note(request: HttpRequest) -> JsonResponse:
    """
    更新设备备注

    :param request: Http 请求对象，POST 参数包含 peer_id, note
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true}
    :rtype: JsonResponse
    """
    peer_id = (request.POST.get('peer_id') or '').strip()
    note = (request.POST.get('note') or '').strip()
    if not peer_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    peer = PeerInfoService().get_peer_info_by_peer_id(peer_id)
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)

    if not PermissionService().has_perm(request.user, DevicePermission.EDIT):
        return JsonResponse({'ok': False, 'err_msg': '无权编辑该设备'}, status=403)

    PeerInfoService().update_note(peer_id, note)
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def device_tags(request: HttpRequest) -> JsonResponse:
    """
    获取当前用户可见的所有标签列表

    :param request: Http 请求对象
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true, "data": ["tag1", "tag2"]}
    :rtype: JsonResponse
    """
    tags = PeerInfoService().get_all_tags_for_user(request.user)
    return JsonResponse({'ok': True, 'data': tags})
