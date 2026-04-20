import json
import logging
import time
import traceback
from functools import wraps

from django.http import HttpRequest, JsonResponse
from django.http.response import HttpResponseRedirectBase, HttpResponse
from django.template.response import TemplateResponse, SimpleTemplateResponse

from apps.db.service import TokenService, PeerInfoService, LoginClientService
from common.env import PublicConfig
from common.utils import get_randem_md5

logger = logging.getLogger('request_debug_log')


def check_login(func):
    """
    检查用户是否已登录的装饰器

    :param func: 被装饰的函数
    :return: 装饰后的函数
    """

    @wraps(func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        headers = request.headers
        if 'Authorization' not in headers:
            return JsonResponse({'error': 'Invalid token'}, status=401)
        token_service = TokenService(request=request)
        token = token_service.authorization
        user_info = token_service.user_info
        body = token_service.request_body
        uuid = token_service.get_cur_uuid_by_token(token)

        system_info = PeerInfoService()
        client_info = system_info.get_peer_info_by_uuid(uuid)

        if not token_service.check_token(token, timeout=PublicConfig.TOKEN_TIMEOUT):
            # Server端记录登录信息 - 直接从token提取用户名，不依赖user_info
            # token格式: {md5}_{username}
            if token and '_' in token:
                username_from_token = token.split('_')[-1]
                peer_id = client_info.peer_id if client_info else None
                LoginClientService().update_logout_status(
                    uuid=uuid,
                    username=username_from_token,
                    peer_id=peer_id,
                )
            return JsonResponse({'error': 'Invalid token'}, status=401)
        token_service.update_token(token)
        return func(request, *args, **kwargs)

    return wrapper


def request_debug_log(func):
    """
    记录请求日志的装饰器

    :param func: 被装饰的函数
    :return: 装饰后的函数
    """

    @wraps(func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        __uuid = get_randem_md5()
        request_log = {
            'method': request.method,
            'path': request.path,
            'headers': dict(request.headers),
            'client_ip': getattr(request, 'client_ip', request.META.get('CLIENT_IP') or request.META.get('REMOTE_ADDR'))
        }
        token_service = TokenService(request=request)
        # 记录查询参数
        try:
            if token_service.request_query:
                request_log['request_query'] = token_service.request_query
        except Exception:
            pass

        # 记录请求体：按 Content-Type 分类
        try:
            content_type = getattr(request, 'content_type', None) or request.headers.get('Content-Type')
        except Exception:
            content_type = None
        if content_type:
            request_log['content_type'] = content_type

        # multipart/form-data：表单与文件
        if content_type and 'multipart/form-data' in content_type:
            try:
                # 表单字段（包含多值）
                form_data = {}
                for key, values in request.POST.lists():
                    form_data[key] = values if len(values) > 1 else (values[0] if values else None)
                if form_data:
                    request_log['form'] = form_data
            except Exception:
                pass
            try:
                # 文件元数据，仅记录必要信息
                if request.FILES:
                    files_info = {}
                    for key, files in request.FILES.lists():
                        meta_list = []
                        for f in files:
                            meta_list.append({
                                'filename': getattr(f, 'name', None),
                                'size': getattr(f, 'size', None),
                                'content_type': getattr(f, 'content_type', None),
                            })
                        files_info[key] = meta_list
                    request_log['files'] = files_info
            except Exception:
                pass
            # 尽量避免读取 request.body，记录长度
            try:
                content_length = request.META.get('CONTENT_LENGTH')
                if content_length:
                    request_log['content_length'] = int(content_length)
            except Exception:
                pass

        # application/x-www-form-urlencoded：普通表单
        elif content_type and 'application/x-www-form-urlencoded' in content_type:
            try:
                form_data = {}
                for key, values in request.POST.lists():
                    form_data[key] = values if len(values) > 1 else (values[0] if values else None)
                if form_data:
                    request_log['form'] = form_data
            except Exception:
                pass

        # application/json：JSON 请求体
        elif content_type and 'application/json' in content_type:
            try:
                if request.body:
                    encoding = getattr(request, 'encoding', None) or 'utf-8'
                    request_log['request_body'] = json.loads(request.body.decode(encoding))
                    request_log['content_length'] = len(request.body)
            except Exception:
                # 回退为文本片段
                try:
                    encoding = getattr(request, 'encoding', None) or 'utf-8'
                    request_log['request_text'] = request.body.decode(encoding, errors='ignore')[:2048]
                    request_log['content_length'] = len(request.body)
                except Exception:
                    pass

        # 其他类型或无 Content-Type：记录文本片段/长度
        else:
            try:
                if request.body:
                    encoding = getattr(request, 'encoding', None) or 'utf-8'
                    snippet = request.body.decode(encoding, errors='ignore')
                    request_log['request_text_snippet'] = snippet[:1024]
                    request_log['content_length'] = len(request.body)
            except Exception:
                pass

        logger.debug(f'[{__uuid}]request: {json.dumps(request_log, ensure_ascii=False, default=str)}')

        start = time.time()
        try:
            response = func(request, *args, **kwargs)
        except Exception:
            logger.error(f'[{__uuid}]error: {traceback.format_exc()}')
            raise
        if response is None:
            response = HttpResponse(status=200)
        response_data = {
            'status_code': response.status_code,
        }
        # Content-Type 信息
        try:
            content_type = response.headers.get('Content-Type') if hasattr(response, 'headers') else response.get(
                'Content-Type')
        except Exception:
            content_type = None
        if content_type:
            response_data['content_type'] = content_type

        # 模板响应：记录模板名与上下文数据
        if isinstance(response, (TemplateResponse, SimpleTemplateResponse)):
            template_name = getattr(response, 'template_name', None)
            response_data['template'] = template_name if isinstance(template_name, (str, list, tuple)) else str(
                template_name)
            response_data['template_context'] = getattr(response, 'context_data', None)

        # 重定向响应：记录重定向 URL
        elif isinstance(response, HttpResponseRedirectBase):
            redirect_url = None
            if hasattr(response, 'headers'):
                redirect_url = response.headers.get('Location')
            if not redirect_url:
                redirect_url = getattr(response, 'url', None)
            response_data['redirect_url'] = redirect_url

        # 流式响应（包含文件响应）：不读取内容，避免消耗迭代器
        elif getattr(response, 'streaming', False):
            response_data['streaming'] = True
            if hasattr(response, 'headers'):
                response_data['content_length'] = int(response.headers.get('Content-Length'))
                disposition = response.headers.get('Content-Disposition')
                if disposition:
                    response_data['content_disposition'] = disposition

        # JSON 响应
        elif (content_type and 'application/json' in content_type) or isinstance(response, JsonResponse):
            try:
                if response.content:
                    charset = getattr(response, 'charset', 'utf-8') or 'utf-8'
                    response_data['response_body'] = json.loads(response.content.decode(charset))
            except Exception:
                # 回退为文本记录片段，避免日志异常
                try:
                    charset = getattr(response, 'charset', 'utf-8') or 'utf-8'
                    response_data['response_text'] = response.content.decode(charset, errors='ignore')[:2048]
                except Exception:
                    pass

        # 其他类型：模板 HTML 或文本片段（限制长度）
        else:
            try:
                # 对于 HTML 模板响应，仅记录模板名称与上下文参数
                if content_type and 'text/html' in content_type:
                    template_name = getattr(response, 'template_name', None)
                    context_data = getattr(response, 'context_data', None)
                    response_data['template'] = template_name if isinstance(template_name, (str, list, tuple)) else (
                        str(template_name) if template_name is not None else None)
                    response_data['template_context'] = context_data
                # 其他类型，记录文本片段
                elif response.content:
                    charset = getattr(response, 'charset', 'utf-8') or 'utf-8'
                    snippet = response.content.decode(charset, errors='ignore')
                    response_data['response_text_snippet'] = snippet[:1024]
            except Exception:
                pass

        response_log = json.dumps(response_data, ensure_ascii=False, default=str)
        logger.debug(f'[{__uuid}]response: {response_log}, use_time: {round(time.time() - start, 4)} s')
        return response

    return wrapper


def debug_response_None(func):
    @wraps(func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        # return func(request, *args, **kwargs)
        return HttpResponse(status=200)

    return wrapper
