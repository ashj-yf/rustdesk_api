from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.client_apis.common import request_debug_log
from apps.db.models import Personal, Alias, HeartBeat, ClientTags, PeerInfo
from apps.db.service import PersonalService, AliasService


def is_default_personal(personal, user):
    """
    判断是否是默认地址簿

    :param personal: Personal对象
    :param user: User对象
    :return: 是否是默认地址簿
    :rtype: bool
    :notes:
    - 地址簿名称为"默认地址簿"
    - 或地址簿名称为"{用户名}_personal"
    """
    if personal.personal_name == '默认地址簿':
        return True
    if personal.personal_name == f'{user.username}_personal':
        return True
    return False


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def create_personal(request: HttpRequest) -> JsonResponse:
    """
    创建地址簿

    :param request: POST，包含 personal_name, personal_type
    :return: {"ok": true, "data": {"guid": "xxx"}}
    """
    personal_name = (request.POST.get('personal_name') or '').strip()
    # personal_type = (request.POST.get('personal_type') or '').strip()

    if not personal_name:
        return JsonResponse({'ok': False, 'err_msg': '地址簿名称不能为空'}, status=400)
    # if personal_type not in ('public', 'private'):
    #     personal_type = 'private'
    personal_type = 'public'

    # 检查是否已存在同名地址簿
    existing = Personal.objects.filter(
        creator=request.user,
        personal_name=personal_name
    ).first()
    if existing:
        return JsonResponse({'ok': False, 'err_msg': '地址簿名称已存在'}, status=400)

    # 创建地址簿
    personal = Personal.objects.create(
        personal_name=personal_name,
        creator=request.user,
        personal_type=personal_type
    )

    return JsonResponse({'ok': True, 'data': {'guid': personal.guid}})


@request_debug_log
@require_http_methods(["POST"])
@login_required(login_url='web_login')
def delete_personal(request: HttpRequest) -> JsonResponse:
    """
    删除地址簿

    :param request: POST，包含 guid
    :return: {"ok": true}
    """
    guid = (request.POST.get('guid') or '').strip()

    if not guid:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    personal = Personal.objects.filter(guid=guid, create_user_id=request.user.id).first()
    if not personal:
        return JsonResponse({'ok': False, 'err_msg': '地址簿不存在或无权限删除'}, status=404)

    # 检查是否是默认地址簿
    if is_default_personal(personal, request.user):
        return JsonResponse({'ok': False, 'err_msg': '默认地址簿不能删除'}, status=400)

    personal.delete()
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(["POST"])
@login_required(login_url='web_login')
def rename_personal(request: HttpRequest) -> JsonResponse:
    """
    重命名地址簿

    :param request: POST，包含 guid, new_name
    :return: {"ok": true}
    """
    guid = (request.POST.get('guid') or '').strip()
    new_name = (request.POST.get('new_name') or '').strip()

    if not guid or not new_name:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    personal = Personal.objects.filter(guid=guid, create_user_id=request.user.id).first()
    if not personal:
        return JsonResponse({'ok': False, 'err_msg': '地址簿不存在或无权限修改'}, status=404)

    # 检查是否是默认地址簿
    if is_default_personal(personal, request.user):
        return JsonResponse({'ok': False, 'err_msg': '默认地址簿不能重命名'}, status=400)

    # 检查新名称是否已存在
    existing = Personal.objects.filter(
        creator=request.user,
        personal_name=new_name
    ).exclude(guid=guid).first()
    if existing:
        return JsonResponse({'ok': False, 'err_msg': '地址簿名称已存在'}, status=400)

    personal.personal_name = new_name
    personal.save(update_fields=['personal_name'])
    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(["GET"])
@login_required(login_url='web_login')
def personal_detail(request: HttpRequest) -> JsonResponse:
    """
    获取地址簿详情（包含设备列表）

    :param request: GET，包含 guid
    :return: {"ok": true, "data": {...}}
    """
    guid = (request.GET.get('guid') or '').strip()

    if not guid:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    personal = Personal.objects.filter(guid=guid, create_user_id=request.user.id).first()
    if not personal:
        return JsonResponse({'ok': False, 'err_msg': '地址簿不存在或无权限查看'}, status=404)

    personal_service = PersonalService()
    peers = personal_service.get_peers_by_personal(guid=guid)

    # 在线判定：心跳表 5 分钟内有记录视为在线
    online_threshold = timezone.now() - timedelta(minutes=5)

    devices = []
    # 获取所有peer的ID列表
    peer_ids = [peer_info.peer.peer_id for peer_info in peers]

    # 使用AliasService批量获取别名映射
    alias_map = AliasService().get_alias_map(guid=guid, peer_ids=peer_ids)
    
    for peer_info in peers:
        peer = peer_info.peer
        # 检查在线状态
        is_online = HeartBeat.objects.filter(
            Q(peer_id=peer.peer_id) | Q(uuid=peer.uuid),
            modified_at__gte=online_threshold
        ).exists()

        # 获取该设备在该地址簿中的标签
        client_tags = ClientTags.objects.filter(peer_id=peer.peer_id, guid_id=guid).first()
        tags = client_tags.tags if client_tags else ''

        devices.append({
            'peer_id': peer.peer_id,
            'alias': alias_map.get(peer.peer_id, ''),  # 使用别名映射获取别名
            'tags': tags,
            'device_name': peer.device_name,
            'os': peer.os,
            'version': peer.version,
            'is_online': is_online,
            'created_at': peer.created_at.strftime('%Y-%m-%d %H:%M:%S') if peer.created_at else '',
        })

    data = {
        'guid': personal.guid,
        'personal_name': personal.personal_name,
        'display_name': '默认地址簿' if personal.personal_name == f'{request.user.username}_personal' else personal.personal_name,
        'personal_type': personal.personal_type,
        'created_at': personal.created_at.strftime('%Y-%m-%d %H:%M:%S') if personal.created_at else '',
        'device_count': len(devices),
        'devices': devices,
    }

    return JsonResponse({'ok': True, 'data': data})


@request_debug_log
@require_http_methods(['GET'])
@login_required(login_url='web_login')
def get_personal_list(request: HttpRequest) -> JsonResponse:
    """
    获取当前用户的所有地址簿列表（用于下拉选择）

    :param request: GET请求
    :return: {"ok": true, "data": [{"guid": "xxx", "name": "xxx", "display_name": "xxx"}, ...]}
    """

    # 获取当前用户的所有地址簿
    personals = Personal.objects.filter(create_user_id=request.user.id).order_by('personal_name')

    data = []
    for personal in personals:
        # 设置显示名称：如果是 {用户名}_personal 格式，显示为"默认地址簿"
        if personal.personal_name == f'{request.user.username}_personal':
            display_name = '默认地址簿'
        else:
            display_name = personal.personal_name

        data.append({
            'guid': personal.guid,
            'name': personal.personal_name,
            'display_name': display_name,
        })

    return JsonResponse({'ok': True, 'data': data})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def add_device_to_personal(request: HttpRequest) -> JsonResponse:
    """
    添加设备到地址簿

    :param request: POST，包含 guid, peer_id, alias(可选)
    :return: {"ok": true}
    """
    guid = (request.POST.get('guid') or '').strip()
    peer_id = (request.POST.get('peer_id') or '').strip()
    alias_text = (request.POST.get('alias') or '').strip()

    if not guid or not peer_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    personal = Personal.objects.filter(guid=guid, create_user_id=request.user.id).first()
    if not personal:
        return JsonResponse({'ok': False, 'err_msg': '地址簿不存在或无权限操作'}, status=404)

    peer = PeerInfo.objects.filter(peer_id=peer_id).first()
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)

    # 添加或更新别名（如果已存在则更新）
    AliasService().set_alias(
        guid=guid,
        peer_id=peer_id,
        alias=alias_text
    )
    PersonalService().add_peer_to_personal(
        guid=guid,
        peer_id=peer.peer_id,
    )

    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def remove_device_from_personal(request: HttpRequest) -> JsonResponse:
    """
    从地址簿移除设备

    :param request: POST，包含 guid, peer_id
    :return: {"ok": true}
    """
    guid = (request.POST.get('guid') or '').strip()
    peer_id = (request.POST.get('peer_id') or '').strip()

    if not guid or not peer_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    personal = Personal.objects.filter(guid=guid, create_user_id=request.user.id).first()
    if not personal:
        return JsonResponse({'ok': False, 'err_msg': '地址簿不存在或无权限操作'}, status=404)

    PersonalService().del_peer_to_personal(
        guid=guid,
        peer_id=peer_id,
        user=request.user
    )

    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def update_device_alias_in_personal(request: HttpRequest) -> JsonResponse:
    """
    在地址簿中更新设备别名

    :param request: POST，包含 guid, peer_id, alias
    :return: {"ok": true}
    """
    guid = (request.POST.get('guid') or '').strip()
    peer_id = (request.POST.get('peer_id') or '').strip()
    alias_text = (request.POST.get('alias') or '').strip()

    if not guid or not peer_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    # 验证地址簿权限
    personal = Personal.objects.filter(guid=guid, create_user_id=request.user.id).first()
    if not personal:
        return JsonResponse({'ok': False, 'err_msg': '地址簿不存在或无权限操作'}, status=404)

    # 验证设备存在
    peer = PeerInfo.objects.filter(peer_id=peer_id).first()
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)

    # 如果别名为空，使用设备ID作为别名
    if not alias_text:
        alias_text = peer_id

    # 更新别名
    alias_obj = Alias.objects.filter(peer_id=peer, guid=personal).first()
    if not alias_obj:
        return JsonResponse({'ok': False, 'err_msg': '设备不在该地址簿中'}, status=404)

    alias_obj.alias = alias_text
    alias_obj.save(update_fields=['alias'])

    return JsonResponse({'ok': True})


@request_debug_log
@require_http_methods(['POST'])
@login_required(login_url='web_login')
def update_device_tags_in_personal(request: HttpRequest) -> JsonResponse:
    """
    在地址簿中更新设备标签

    :param request: POST，包含 guid, peer_id, tags
    :return: {"ok": true}
    """
    guid = (request.POST.get('guid') or '').strip()
    peer_id = (request.POST.get('peer_id') or '').strip()
    tags_text = (request.POST.get('tags') or '').strip()

    if not guid or not peer_id:
        return JsonResponse({'ok': False, 'err_msg': '参数错误'}, status=400)

    # 验证地址簿权限
    personal = Personal.objects.filter(guid=guid, create_user_id=request.user.id).first()
    if not personal:
        return JsonResponse({'ok': False, 'err_msg': '地址簿不存在或无权限操作'}, status=404)

    # 验证设备存在
    peer = PeerInfo.objects.filter(peer_id=peer_id).first()
    if not peer:
        return JsonResponse({'ok': False, 'err_msg': '设备不存在'}, status=404)

    ClientTags.objects.filter(peer_id=peer_id, guid_id=guid).delete()

    if tags_text:
        ClientTags.objects.create(
            user=request.user,
            peer_id=peer_id,
            tags=tags_text,
            guid_id=guid
        )

    return JsonResponse({'ok': True})
