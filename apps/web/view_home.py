from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q, Exists, OuterRef, F, Subquery
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.client_apis.common import request_debug_log
from apps.db.models import PeerInfo, HeartBeat, Alias, ClientTags, Personal
from apps.web.view_personal import is_default_personal


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
    return render(request, 'home.html', context={'username': username})


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
        # 未知 key，返回占位内容而非 404，便于前端保持一致渲染
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

        user_count = User.objects.filter(is_active=True).count()
        queryset = PeerInfo.objects.order_by('-created_at')
        device_count = queryset.count()
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        # 当前页设备列表
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
        """
        设备管理（nav-2）上下文构建

        :query page: 页码（默认 1）
        :query page_size: 每页大小（默认 20）
        :query q: 关键词，匹配设备ID/设备名（可空）
        :query os: 操作系统筛选（可空；模糊匹配）
        :query status: 在线状态（online/offline，可空）
        :returns: 注入模板的设备分页、筛选上下文
        :rtype: HttpResponse
        """
        # 基本分页参数
        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 20))
        except (TypeError, ValueError):
            page_size = 20

        # 筛选参数
        q = (request.GET.get('q') or '').strip()
        os_param = (request.GET.get('os') or '').strip()
        status = (request.GET.get('status') or '').strip().lower()

        # 在线判定：心跳表 5 分钟内有记录视为在线
        online_threshold = timezone.now() - timedelta(minutes=5)
        recent_hb = HeartBeat.objects.filter(
            Q(peer_id=OuterRef('peer_id')) | Q(uuid=OuterRef('uuid')),
            modified_at__gte=online_threshold
        ).values('pk')[:1]

        base_qs = PeerInfo.objects.all().annotate(
            is_online=Exists(recent_hb),
            owner_username=F('username'),
            # 别名：取任意一个别名（如存在）
            alias=Subquery(
                Alias.objects.filter(
                    peer_id=OuterRef('peer_id')
                ).values('alias')[:1]
            ),
            # 标签：取当前登录用户下的一个标签（如存在）
            tags=Subquery(
                ClientTags.objects.filter(
                    peer_id=OuterRef('peer_id'),
                    user=request.user
                ).values('tags')[:1]
            )
        ).order_by('-created_at')

        if q:
            base_qs = base_qs.filter(Q(peer_id__icontains=q) | Q(device_name__icontains=q))
        if os_param:
            base_qs = base_qs.filter(os__icontains=os_param)
        if status in ('online', 'offline'):
            want_online = (status == 'online')
            base_qs = base_qs.filter(is_online=want_online)

        paginator = Paginator(base_qs, page_size)
        page_obj = paginator.get_page(page)
        devices = page_obj.object_list

        context.update({
            'devices': devices,
            'paginator': paginator,
            'page_obj': page_obj,
            'page_size': page_size,
            # 透传筛选回显
            'q': q,
            'os': os_param,
            'status': status,
        })
    elif key == 'nav-3':  # 用户管理
        # 分页参数
        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 20))
        except (TypeError, ValueError):
            page_size = 20
        # 搜索参数
        q = (request.GET.get('q') or '').strip()
        # 只显示未删除的用户（is_active=True）
        user_qs = User.objects.filter(is_active=True).order_by('-date_joined')
        if q:
            user_qs = user_qs.filter(
                Q(username__icontains=q) |
                Q(email__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q)
            )
        paginator = Paginator(user_qs, page_size)
        page_obj = paginator.get_page(page)
        users = page_obj.object_list
        context.update({
            'users': users,
            'paginator': paginator,
            'page_obj': page_obj,
            'page_size': page_size,
            'q': q,
        })
    elif key == 'nav-4':  # 地址簿
        # 分页参数
        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 20))
        except (TypeError, ValueError):
            page_size = 20
        # 搜索参数
        q = (request.GET.get('q') or '').strip()
        personal_type = (request.GET.get('type') or '').strip()

        # 查询当前用户的地址簿（包括自己创建的和被分享的）
        personal_qs = Personal.objects.filter(creator=request.user).order_by('-created_at')

        # 搜索过滤（使用guid进行搜索）
        if q:
            personal_qs = personal_qs.filter(guid__icontains=q)
        if personal_type in ('public', 'private'):
            personal_qs = personal_qs.filter(personal_type=personal_type)

        paginator = Paginator(personal_qs, page_size)
        page_obj = paginator.get_page(page)
        personals = list(page_obj.object_list)

        # 为每个地址簿统计设备数量并标记是否为默认地址簿
        for personal in personals:
            device_count = Alias.objects.filter(guid=personal).count()
            personal.device_count = device_count
            personal.is_default = is_default_personal(personal, request.user)
            # 设置显示名称：如果是 {用户名}_personal 格式，显示为"默认地址簿"
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
    - 别名基于用户的“默认地址簿”（如不存在则自动创建，私有）
    - 针对 (peer_id, 默认地址簿) 维度进行 upsert
    """
    peer_id = (request.POST.get('peer_id') or '').strip()
    alias_text = (request.POST.get('alias') or '').strip()
    if not peer_id or not alias_text:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    peer = PeerInfo.objects.filter(peer_id=peer_id).first()
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)
    # 获取或创建默认地址簿（私有）
    personal, _ = Personal.objects.get_or_create(
        creator=request.user,
        personal_type='private',
        personal_name='默认地址簿',
        defaults={}
    )
    Alias.objects.update_or_create(
        peer_id=peer,
        guid=personal,
        defaults={'alias': alias_text}
    )
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
    peer = PeerInfo.objects.filter(peer_id=peer_id).first()
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)
    # 默认地址簿下的 alias（若无则回退任意一个 alias）
    default_personal = Personal.objects.filter(
        creator=request.user,
        personal_type='private',
        personal_name='默认地址簿'
    ).first()
    alias_qs = Alias.objects.filter(peer_id=peer)
    if default_personal:
        prefer = alias_qs.filter(guid=default_personal).values_list('alias', flat=True).first()
        alias_text = prefer if prefer is not None else alias_qs.values_list('alias', flat=True).first()
    else:
        alias_text = alias_qs.values_list('alias', flat=True).first()
    alias_text = alias_text or ''
    # 当前用户下的标签（可能多条）
    tag_list = list(ClientTags.objects.filter(user=request.user, peer_id=peer_id).values_list('tags', flat=True))
    # 构造响应
    data = {
        'peer_id': peer.peer_id,
        'username': peer.username,
        'hostname': peer.device_name,
        'alias': alias_text,
        'platform': peer.os,
        'tags': tag_list,
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
    - 别名写入当前用户的“默认地址簿”（不存在则创建）
    - 标签写入 ClientTags（当前用户 + 默认地址簿 guid 作用域）
    """
    peer_id = (request.POST.get('peer_id') or '').strip()
    if not peer_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)
    peer = PeerInfo.objects.filter(peer_id=peer_id).first()
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)

    alias_text = request.POST.get('alias')
    tags_str = request.POST.get('tags')

    # 获取/创建默认地址簿（私有）
    personal, _ = Personal.objects.get_or_create(
        creator=request.user,
        personal_type='private',
        personal_name='默认地址簿',
        defaults={}
    )

    # 更新别名（当 alias 参数存在时）
    if alias_text is not None:
        alias_text = alias_text.strip()
        if alias_text:
            Alias.objects.update_or_create(
                peer_id=peer,
                guid=personal,
                defaults={'alias': alias_text}
            )
        else:
            # 空字符串表示清除当前作用域下别名
            Alias.objects.filter(peer_id=peer, guid=personal).delete()

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
            ClientTags.objects.update_or_create(
                user=request.user,
                peer_id=peer_id,
                guid=personal,
                defaults={'tags': joined}
            )
        else:
            # 空表示清空标签
            ClientTags.objects.filter(user=request.user, peer_id=peer_id, guid=personal).delete()

    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def device_statuses(request: HttpRequest) -> JsonResponse:
    """
    批量获取设备在线状态（仅查询，不修改会话）

    :param request: Http 请求对象，GET 参数：
        - ids: 逗号分隔的设备ID列表，如 "id1,id2,id3"
    :type request: HttpRequest
    :return: JSON 响应，形如 {"ok": true, "data": {"<peer_id>": {"is_online": true/false}}}
    :rtype: JsonResponse
    :notes:
        - 前端应在请求头携带 ``X-Session-No-Renew: 1``，以避免该轮询请求“续命”会话
        - 仅执行只读查询，不做任何写操作
    """
    raw_ids = (request.GET.get('ids') or '').strip()
    if not raw_ids:
        return JsonResponse({'ok': True, 'data': {}})
    # 归一化与限流（防止一次性过大）
    peer_ids = [p.strip() for p in raw_ids.split(',') if p.strip()]
    if not peer_ids:
        return JsonResponse({'ok': True, 'data': {}})
    peer_ids = peer_ids[:500]
    # 60s 内有心跳视为在线
    online_threshold = timezone.now() - timedelta(seconds=60)
    online_qs = HeartBeat.objects.filter(
        peer_id__in=peer_ids,
        modified_at__gte=online_threshold
    ).values_list('peer_id', flat=True).distinct()
    online_set = set(online_qs)
    data = {pid: {'is_online': (pid in online_set)} for pid in peer_ids}
    return JsonResponse({'ok': True, 'data': data})


