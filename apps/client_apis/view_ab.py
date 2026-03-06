import json
import logging
import traceback

from django.http import HttpRequest, JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods

from apps.client_apis.common import request_debug_log, check_login
from apps.db.models import Personal
from apps.db.service import TokenService, AliasService, TagService, PersonalService, SharePersonalService, \
    UserConfigService

logger = logging.getLogger(__name__)


@request_debug_log
@require_http_methods(["GET", "POST"])
@check_login
def ab(request: HttpRequest):
    """
    Legacy 地址簿接口

    GET: 拉取整个地址簿数据
    POST: 推送整个地址簿数据
    """
    token_service = TokenService(request=request)
    user_info = token_service.user_info
    config_service = UserConfigService(user_info)

    if request.method == "GET":
        data = config_service.get_legacy_ab()
        if data is None:
            return HttpResponse('null', content_type='application/json')
        return JsonResponse({
            'licensed_devices': 0,
            'data': data,
        })

    try:
        body = json.loads(request.body.decode('utf-8'))
        ab_data = body.get('data', '')
        config_service.set_legacy_ab(ab_data)
        return HttpResponse(status=200)
    except json.JSONDecodeError as e:
        logger.error(f"Legacy地址簿JSON解析失败: {e}")
        return HttpResponse(status=400)
    except Exception as e:
        logger.error(f"Legacy地址簿保存失败: {e}")
        logger.error(traceback.format_exc())
        return HttpResponse(status=500)


@request_debug_log
@require_http_methods(["POST"])
@check_login
def ab_personal(request: HttpRequest):
    """
    获取个人地址簿
    :param request:
    :return:
    """
    token_service = TokenService(request=request)
    user_info = token_service.user_info
    guid = PersonalService().get_private_personal_guid(user_info)
    return JsonResponse(
        {
            "guid": guid,
            "name": user_info.username,
        }
    )


@request_debug_log
@require_http_methods(["POST"])
@check_login
def ab_tags(request, guid):
    token_service = TokenService(request=request)
    user_info = token_service.user_info
    tag_service = TagService(guid=guid, user=user_info)
    tags = tag_service.get_all_tags()
    data = [
        {
            'name': tag.tag,
            'color': int(tag.color),
        } for tag in tags
    ]
    return JsonResponse(data, safe=False, status=200)


@request_debug_log
@require_http_methods(["DELETE"])
@check_login
def ab_tag(request, guid):
    token_service = TokenService(request=request)
    body = token_service.request_body
    tags = body
    user_info = token_service.user_info
    tag_service = TagService(guid=guid, user=user_info)
    tag_service.delete_tag(*list(tags))

    return HttpResponse(status=200)


@request_debug_log
@require_http_methods(["POST", "PUT"])
@check_login
def ab_tag_add(request, guid):
    token_service = TokenService(request=request)
    user_info = token_service.user_info
    body = token_service.request_body
    tag = body.get('name')
    color = body.get('color')
    if request.method == "POST":
        tag_service = TagService(guid=guid, user=user_info)
        tag_service.create_tag(tag=tag, color=color)
    elif request.method == "PUT":
        tag_service = TagService(guid=guid, user=user_info)
        tag_service.update_tag(tag=tag, color=color)
    return HttpResponse(status=200)


@request_debug_log
@require_http_methods(["PUT"])
@check_login
def ab_tag_rename(request, guid):
    token_service = TokenService(request=request)
    body = token_service.request_body
    user_info = token_service.user_info

    tag_old = body.get('old')
    tag_new = body.get('new')

    tag_service = TagService(guid=guid, user=user_info)
    tag_service.update_tag(tag=tag_old, new_tag=tag_new)
    return HttpResponse(status=200)


@request_debug_log
@require_http_methods(["POST"])
@check_login
def ab_settings(request):
    return JsonResponse(
        {
            "max_peer_one_ab": 0
        }
    )


@request_debug_log
@require_http_methods(["POST"])
@check_login
def ab_shared_profiles(request):
    token_service = TokenService(request=request)
    user_info = token_service.user_info

    # 分享给自己的地址簿
    shared_personals = SharePersonalService(user_info).get_user_personals()

    # 自己创建的地址簿
    created_personals = PersonalService().get_user_created_personals(user_info)

    personal_data = []
    for personal in list(shared_personals) + list(created_personals):
        personal = personal if isinstance(personal, Personal) else personal.personal
        if personal.personal_type == 'private':
            continue
        personal_data.append(
            {
                "guid": personal.guid,
                "name": personal.personal_name,
            }
        )

    data = {
        "total": len(personal_data),
        "data": personal_data
    }

    return JsonResponse(data)


@request_debug_log
@require_http_methods(["POST"])
@check_login
def ab_peers(request):
    """
    返回用户添加到地址簿的设备列表
    :param request:
    :return:
    """
    token_service = TokenService(request=request)
    user_info = token_service.user_info
    request_query = token_service.request_query
    guid = request_query.get('ab')

    personal_service = PersonalService()
    try:
        # 结合 select_related 一次性拉取 `peer`，避免 N+1
        peers_qs = personal_service.get_personal(guid).personal_peer.select_related('peer').all()
    except Exception:
        logger.error(f'[ab_peers] get personal error: {guid}')
        return JsonResponse(
            {
                "total": 0,
                "data": []
            }
        )

    # 预取 alias 和 tags，使用批量映射减少查询
    peer_ids = [p.peer.peer_id for p in peers_qs]
    alias_map = AliasService().get_alias_map(guid=guid, peer_ids=peer_ids)
    tags_map = TagService(guid=guid, user=user_info).get_tags_map(peer_ids)

    os_map = {
        'windows': 'Windows',
        'linux': 'Linux',
        'macos': 'Mac OS',
        'android': 'Android',
        'ios': 'iOS',
    }

    def _resolve_platform(os_str: str) -> str:
        key = (os_str or '').split(' / ')[0].strip().lower()
        platform = os_map.get(key)
        if platform:
            return platform
        if 'linux' in key:
            return 'Linux'
        return key or ''

    result = {
        "total": peers_qs.count(),
        "data": [
            {
                "id": p.peer.peer_id,
                "username": p.peer.username,
                "hostname": p.peer.device_name,
                "alias": alias_map.get(p.peer.peer_id, ""),
                "platform": _resolve_platform(p.peer.os),
                "tags": tags_map.get(p.peer.peer_id, []),
            } for p in peers_qs
        ]
    }

    return JsonResponse(result)


@request_debug_log
@require_http_methods(["POST"])
@check_login
def ab_peer_add(request, guid):
    token_service = TokenService(request=request)
    body = token_service.request_body
    try:
        PersonalService().add_peer_to_personal(
            guid=guid,
            peer_id=body.get('id'),
        )
        return HttpResponse(status=200)
    except:
        return JsonResponse(
            {'error': 'Add peer to personal failed'}
        )


@request_debug_log
@require_http_methods(["PUT"])
@check_login
def ab_peer_update(request, guid):
    token_service = TokenService(request=request)
    user_info = token_service.user_info
    body = token_service.request_body
    peer_id = body.get('id')

    if 'alias' in body.keys():
        AliasService().set_alias(
            guid=guid,
            peer_id=peer_id,
            alias=body.get('alias', '')
        )
    if 'tags' in body.keys():
        TagService(guid=guid, user=user_info).set_user_tag_by_peer_id(peer_id=peer_id, tags=body.get('tags', ''))
    return HttpResponse(status=200)


@request_debug_log
@require_http_methods(["DELETE"])
@check_login
def ab_peer_delete(request, guid):
    token_service = TokenService(request=request)
    user_info = token_service.user_info
    body = token_service.request_body
    PersonalService().del_peer_to_personal(
        guid=guid,
        peer_id=body,
        user=user_info
    )
    return HttpResponse(status=200)
