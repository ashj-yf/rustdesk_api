import json
import logging
import time
from datetime import timedelta
from typing import TypeVar

from django.contrib.auth.models import User, Group
from django.db import models
from django.db import transaction, OperationalError
from django.db.models import Q, Exists, OuterRef, F, Subquery
from django.http import HttpRequest
from django.utils import timezone

from apps.db.models import (
    HeartBeat,
    PeerInfo,
    Token,
    LoginClient,
    Tag,
    Log,
    AuditConnLog,
    AuditFileLog,
    UserProfile,
    Personal,
    Alias,
    ClientTags,
    PeerPersonal,
    ShareToUser,
    ShareToGroup,
    UserConfig,
    DeviceGroup,
    DevicePermission,
    Role,
    UserRole,
    DeviceGroupPeer,
    GroupRole,
)
from common.env import PublicConfig
from common.error import UserNotFoundError
from common.utils import get_local_time, get_randem_md5

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=models.Model)


class BaseService:
    """
    数据服务基类

    :param db: 需要操作的模型类
    """

    db: models.Model = None

    @staticmethod
    def get_user_info(username):
        if isinstance(username, str):
            username = UserService().get_user_by_name(username)
        return username

    @staticmethod
    def get_peer_by_uuid(uuid):
        if isinstance(uuid, str):
            uuid = PeerInfoService().get_peer_info_by_uuid(uuid)
        return uuid

    @staticmethod
    def get_peer_by_peer_id(peer_id):
        if isinstance(peer_id, str):
            peer_id = PeerInfoService().get_peer_info_by_peer_id(peer_id)
        return peer_id


class UserService(BaseService):
    db = User

    def get(self, email) -> User | None:
        try:
            return self.db.objects.get(email=email)
        except self.db.DoesNotExist:
            return None

    def get_users(self, *users, is_active=True):
        _filter = {
            'username__in': [*users],
            'is_active': is_active
        }
        if is_active is None:
            _filter.pop('is_active')
        return self.db.objects.filter(**_filter).all()

    def create_user(
            self,
            username,
            password,
            email="",
            is_superuser=False,
            is_staff=False,
            is_active=True,
            group: str | Group = None,
    ) -> User:
        user = self.db.objects.create_user(
            username=username,
            email=email,
            is_superuser=is_superuser,
            is_staff=is_staff,
            is_active=is_active,
        )
        user.set_password(password)
        user.save()
        logger.info(f"创建用户: {user}")

        group_service = GroupService()
        group_service.add_user_to_group(user, group_name=group)

        PersonalService().create_self_personal(user)

        RoleService().assign_role_to_user(user, RoleService().get_default_role())

        return user

    def set_user_config(self, username, config_key, config_value):
        qs = self.db.objects.filter(username=username).first()
        UserConfig.objects.update_or_create(
            user=qs,
            config_name=config_key,
            defaults={'config_value': config_value}
        )

    def get_user_config(self, username, config_key=None):
        qs = self.db.objects.filter(username=username).first()
        if not qs:
            return None
        return UserConfig.objects.filter(user=qs, config_name=config_key)

    def get_user_all_config(self, username):
        qs = self.db.objects.filter(username=username).first()
        if not qs:
            return None
        return UserConfig.objects.filter(user=qs).all()

    def get_user_by_email(self, email) -> User:
        return self.db.objects.filter(email=email).first()

    def get_user_by_name(self, username) -> User:
        if isinstance(username, User):
            return username
        return self.db.objects.filter(username=username).first()

    def set_password(self, password, email=None, username=None):
        if username is not None:
            user = self.get_user_by_name(username)
        elif email is not None:
            user = self.get_user_by_email(email)
        else:
            raise ValueError("Either username or email must be provided.")
        if not user:
            raise UserNotFoundError(email or username)
        user.set_password(password)
        user.save()
        logger.info(f"设置用户密码: {user}")
        return user

    def delete_user(self, *usernames):
        self.db.objects.filter(username__in=[*usernames]).update(is_active=False)
        logger.info(f"删除用户: {usernames}")

    def __get_list(self, **kwargs):
        page = int(kwargs.pop("page", 1))
        page_size = int(kwargs.pop("page_size", 10))

        filters = kwargs.pop("filters", {})
        is_active = kwargs.pop("is_active", True)
        if is_active is not None:
            filters.update(is_active=is_active)
        queryset = self.db.objects.filter(**filters)

        if ordering := kwargs.pop("ordering", []):
            queryset = queryset.order_by(*ordering)

        total = queryset.count()
        results = queryset[(page - 1) * page_size: page * page_size]

        return {
            "results": results,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }

    def get_list_by_status(self, is_active, page=1, page_size=10):
        return self.__get_list(is_active=is_active, page=page, page_size=page_size)

    def get_user_by_id(self, user_id) -> User:
        return self.db.objects.filter(id=user_id).first()

    def username_exists(self, username) -> bool:
        return self.db.objects.filter(username=username).exists()

    def email_exists(self, email) -> bool:
        return self.db.objects.filter(email=email).exists()

    def update_user(self, username, **kwargs) -> User | None:
        user = self.get_user_by_name(username)
        if not user:
            return None
        for field, value in kwargs.items():
            setattr(user, field, value)
        user.save(update_fields=list(kwargs.keys()))
        logger.info(f"更新用户信息: {username} - {list(kwargs.keys())}")
        return user

    def get_active_user_by_name(self, username) -> User | None:
        return self.db.objects.filter(username=username, is_active=True).first()

    def delete_user_soft(self, username) -> bool:
        user = self.get_active_user_by_name(username)
        if not user:
            return False
        timestamp = int(time.time())
        update_fields = ['username', 'is_active']
        user.is_active = False
        user.username = f'{user.username}_deleted_{timestamp}'
        if user.email:
            user.email = f'{user.email}_deleted_{timestamp}'
            update_fields.append('email')
        user.save(update_fields=update_fields)
        logger.info(f"软删除用户: {username}")
        return True

    def count_active_users(self) -> int:
        return self.db.objects.filter(is_active=True).count()

    def get_active_users_qs(self, q='', ordering=('-date_joined',)):
        qs = self.db.objects.filter(is_active=True)
        if q:
            qs = qs.filter(
                Q(username__icontains=q) |
                Q(email__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q)
            )
        return qs.order_by(*ordering)


class GroupService(BaseService):
    db = Group

    def __init__(self):
        self.default_group_name = "Default"

    def get_group_by_name(self, name) -> Group:
        if isinstance(name, str):
            return self.db.objects.filter(name=name).first()
        return name

    def get_group_by_id(self, id) -> Group:
        if isinstance(id, str):
            return self.db.objects.filter(id=id).first()
        return id

    def create_group(self, name, permissions=None) -> Group:
        if permissions is None:
            permissions = []
        group = self.db.objects.create(name=name)
        group.permissions.add(*permissions)
        logger.info(f"创建用户组: {group}")
        return group

    def default_group(self):
        group = self.get_group_by_name(self.default_group_name)
        if not group:
            group = self.create_group(name=self.default_group_name)
        return group

    def get_groups_qs(self, q: str = ''):
        """
        获取用户组查询集（支持按名称搜索），供分页使用

        :param q: 搜索关键词，按名称模糊匹配
        :type q: str
        :return: 用户组 QuerySet
        :rtype: QuerySet
        """
        qs = self.db.objects.all()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs.order_by('id')

    def update_group(self, group_id: int, name: str) -> Group | None:
        """
        更新用户组名称

        :param group_id: 用户组 ID
        :type group_id: int
        :param name: 新名称
        :type name: str
        :return: 更新后的用户组对象，不存在返回 None
        :rtype: Group | None
        """
        group = self.db.objects.filter(id=group_id).first()
        if not group:
            return None
        group.name = name
        group.save(update_fields=['name'])
        logger.info(f"更新用户组: id={group_id}, name={name}")
        return group

    def delete_group(self, group_id: int) -> bool:
        """
        删除用户组（Default 组不可删），组内成员自动回落到 Default 组

        :param group_id: 用户组 ID
        :type group_id: int
        :return: 是否删除成功
        :rtype: bool
        """
        group = self.db.objects.filter(id=group_id).first()
        if not group or group.name == self.default_group_name:
            return False
        default = self.default_group()
        with transaction.atomic():
            UserProfile.objects.filter(group=group).update(group=default)
            group.delete()
        logger.info(f"删除用户组: id={group_id}, name={group.name}")
        return True

    def get_group_members(self, group_id: int):
        """
        获取指定组的活跃成员列表

        :param group_id: 用户组 ID
        :type group_id: int
        :return: 用户 QuerySet
        :rtype: QuerySet
        """
        user_ids = UserProfile.objects.filter(
            group_id=group_id
        ).values_list('user_id', flat=True)
        return User.objects.filter(id__in=user_ids, is_active=True).order_by('username')

    def remove_user_from_group(self, user_id: int, group_id: int) -> bool:
        """
        将用户从指定组移出（回落到 Default 组）

        :param user_id: 用户 ID
        :type user_id: int
        :param group_id: 用户组 ID
        :type group_id: int
        :return: 是否操作成功
        :rtype: bool
        """
        profile = UserProfile.objects.filter(user_id=user_id, group_id=group_id).first()
        if not profile:
            return False
        default = self.default_group()
        profile.group = default
        profile.save(update_fields=['group'])
        return True

    def count_group_members(self, group_id: int) -> int:
        """
        统计指定组的活跃成员数

        :param group_id: 用户组 ID
        :type group_id: int
        :return: 成员数量
        :rtype: int
        """
        user_ids = UserProfile.objects.filter(
            group_id=group_id
        ).values_list('user_id', flat=True)
        return User.objects.filter(id__in=user_ids, is_active=True).count()

    def add_user_to_group(self, *username: User | str, group_name: Group | str = None):
        """
        为用户设置所在组（高效批量）。

        通过一次性查询现有 `UserProfile`，区分需要更新与新建的记录，分别使用
        `bulk_update` 与 `bulk_create`，显著减少 SQL 次数，确保"用户仅一个组"。

        :param username: 用户对象或用户名字符串，可变参数，支持批量
        :param group_name: 目标组对象或组名字符串；为空则加入默认组
        :returns: None
        """
        group_name = group_name or self.default_group_name
        group = self.get_group_by_name(group_name)
        if not group:
            group = self.default_group()

        user_service = UserService()
        user_objs: list[User] = []
        for item in username:
            if isinstance(item, User):
                user_objs.append(item)
            elif isinstance(item, str):
                if u := user_service.get_user_by_name(item):
                    user_objs.append(u)
            else:
                continue

        if not user_objs:
            return

        user_ids = [u.id for u in user_objs]

        with transaction.atomic():
            existing_profiles = UserProfile.objects.filter(user_id__in=user_ids)
            user_id_to_profile = {p.user_id: p for p in existing_profiles}

            to_update: list[UserProfile] = []
            to_create: list[UserProfile] = []

            for u in user_objs:
                if u.id in user_id_to_profile:
                    profile = user_id_to_profile[u.id]
                    if profile.group_id != group.id:
                        profile.group = group
                        to_update.append(profile)
                else:
                    to_create.append(UserProfile(user=u, group=group))

            if to_update:
                UserProfile.objects.bulk_update(to_update, ["group"])
            if to_create:
                UserProfile.objects.bulk_create(to_create)


class PeerInfoService(BaseService):
    db = PeerInfo

    def get_peer_info_by_uuid(self, uuid):
        return self.db.objects.filter(uuid=uuid).first()

    def get_peer_info_by_peer_id(self, peer_id):
        return self.db.objects.filter(peer_id=peer_id).first()

    def update(self, uuid: str, **kwargs):
        kwargs["uuid"] = uuid
        peer_id = kwargs.get("peer_id")

        if not self.db.objects.filter(Q(uuid=uuid) | Q(peer_id=peer_id)).update(**kwargs):
            self.db.objects.create(**kwargs)

        logger.info(f"更新设备信息: {kwargs}")

    def get_list(self):
        return self.db.objects.all()

    def get_peers(self, *peers):
        return self.db.objects.filter(peer_id__in=peers).all()

    def count_all(self) -> int:
        return self.db.objects.count()

    def get_all_ordered_qs(self, ordering=('-created_at',)):
        return self.db.objects.order_by(*ordering)

    def get_device_list_qs(self, user, q='', os_param='', status='',
                           enabled='', sort='', tags=None):
        """
        获取设备列表查询集（带标注和筛选）

        :param user: 当前用户
        :param q: 搜索关键词（匹配设备ID/设备名/别名）
        :param os_param: 操作系统筛选
        :param status: 在线状态筛选（online/offline）
        :param enabled: 启用状态筛选（enabled/disabled）
        :param sort: 排序字段（peer_id/device_name/username/status/-created_at）
        :param tags: 标签筛选列表
        :return: 标注后的查询集
        :rtype: QuerySet
        """
        online_threshold = timezone.now() - timedelta(minutes=5)
        recent_hb = HeartBeat.objects.filter(
            Q(peer_id=OuterRef('peer_id')) | Q(uuid=OuterRef('uuid')),
            modified_at__gte=online_threshold
        ).values('pk')[:1]

        base_qs = self.db.objects.all().annotate(
            is_online=Exists(recent_hb),
            owner_username=F('username'),
            alias=Subquery(
                Alias.objects.filter(
                    peer_id=OuterRef('peer_id')
                ).values('alias')[:1]
            ),
            tags_text=Subquery(
                ClientTags.objects.filter(
                    peer_id=OuterRef('peer_id'),
                    user=user
                ).values('tags')[:1]
            )
        )

        sort_map = {
            'peer_id': 'peer_id',
            'device_name': 'device_name',
            'username': 'username',
            'status': '-is_online',
            '-created_at': '-created_at',
        }
        ordering = sort_map.get(sort, '-created_at')
        base_qs = base_qs.order_by(ordering)

        if q:
            base_qs = base_qs.filter(
                Q(peer_id__icontains=q) | Q(device_name__icontains=q) |
                Q(alias__icontains=q)
            )
        if os_param:
            base_qs = base_qs.filter(os__icontains=os_param)
        if status in ('online', 'offline'):
            base_qs = base_qs.filter(is_online=(status == 'online'))
        if enabled in ('enabled', 'disabled'):
            base_qs = base_qs.filter(is_enabled=(enabled == 'enabled'))
        if tags:
            tag_peers = ClientTags.objects.filter(
                user=user, tags__contains=tags
            ).values_list('peer_id', flat=True)
            base_qs = base_qs.filter(peer_id__in=tag_peers)

        return base_qs

    def delete_peers(self, peer_ids: list[str]) -> int:
        """
        批量删除设备及其关联数据

        :param peer_ids: 设备ID列表
        :type peer_ids: list[str]
        :return: 删除的设备数量
        :rtype: int
        """
        if not peer_ids:
            return 0
        with transaction.atomic():
            HeartBeat.objects.filter(peer_id__in=peer_ids).delete()
            Alias.objects.filter(peer_id__peer_id__in=peer_ids).delete()
            ClientTags.objects.filter(peer_id__in=peer_ids).delete()
            PeerPersonal.objects.filter(peer__peer_id__in=peer_ids).delete()
            count, _ = self.db.objects.filter(peer_id__in=peer_ids).delete()
        logger.info(f"批量删除设备: {peer_ids}, 共删除 {count} 台")
        return count

    def toggle_peers(self, peer_ids: list[str], enabled: bool) -> int:
        """
        批量启用/禁用设备

        :param peer_ids: 设备ID列表
        :param enabled: 是否启用
        :return: 更新的设备数量
        :rtype: int
        """
        if not peer_ids:
            return 0
        count = self.db.objects.filter(peer_id__in=peer_ids).update(is_enabled=enabled)
        action = '启用' if enabled else '禁用'
        logger.info(f"批量{action}设备: {peer_ids}, 共{count}台")
        return count

    def update_note(self, peer_id: str, note: str) -> bool:
        """
        更新设备备注

        :param peer_id: 设备ID
        :param note: 备注内容
        :return: 是否更新成功
        :rtype: bool
        """
        count = self.db.objects.filter(peer_id=peer_id).update(note=note)
        return count > 0

    def get_all_tags_for_user(self, user) -> list[str]:
        """
        获取当前用户可见的所有标签（去重、扁平化）

        :param user: 当前用户
        :return: 标签名称列表
        :rtype: list[str]
        """
        tag_rows = ClientTags.objects.filter(user=user).values_list('tags', flat=True)
        all_tags = set()
        for raw in tag_rows:
            if isinstance(raw, str):
                for t in raw.split(','):
                    t = t.strip()
                    if t:
                        all_tags.add(t)
            elif isinstance(raw, list):
                for t in raw:
                    t = str(t).strip()
                    if t:
                        all_tags.add(t)
        return sorted(all_tags)


class HeartBeatService(BaseService):
    db = HeartBeat

    MAX_RETRIES = 3
    RETRY_BACKOFF = 0.15

    def update(self, uuid, **kwargs):
        kwargs["modified_at"] = get_local_time()
        kwargs["uuid"] = uuid
        peer_id = kwargs.get("peer_id")

        last_exc = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                with transaction.atomic():
                    if not self.db.objects.filter(Q(uuid=uuid) | Q(peer_id=peer_id)).update(**kwargs):
                        self.db.objects.create(**kwargs)
                return
            except OperationalError as e:
                last_exc = e
                if "locked" not in str(e).lower():
                    raise
                wait = self.RETRY_BACKOFF * (2 ** (attempt - 1))
                logger.warning(f"心跳写入被锁，第{attempt}次重试 (等待{wait:.2f}s): uuid={uuid}")
                time.sleep(wait)

        logger.error(f"心跳写入最终失败 ({self.MAX_RETRIES}次重试): uuid={uuid}, error={last_exc}")
        raise last_exc

    def is_alive(self, uuid, timeout=60):
        client = self.db.objects.filter(uuid=uuid).first()
        if client and get_local_time() - client.modified_at < timeout:
            return True
        return False

    def is_online(self, peer_id, uuid=None, timeout_minutes=5) -> bool:
        threshold = timezone.now() - timedelta(minutes=timeout_minutes)
        q_filter = Q(peer_id=peer_id)
        if uuid:
            q_filter |= Q(uuid=uuid)
        return self.db.objects.filter(q_filter, modified_at__gte=threshold).exists()

    def get_online_peer_ids(self, peer_ids, timeout_seconds=60) -> set:
        if not peer_ids:
            return set()
        threshold = timezone.now() - timedelta(seconds=timeout_seconds)
        online_qs = self.db.objects.filter(
            peer_id__in=peer_ids,
            modified_at__gte=threshold
        ).values_list('peer_id', flat=True).distinct()
        return set(online_qs)


class LoginClientService(BaseService):
    """
    登录客户端服务类
    """

    db = LoginClient

    @property
    def platform(self):
        return {
            'windows': LoginClient.PLATFORM_WINDOWS,
            'macos': LoginClient.PLATFORM_MACOS,
            'linux': LoginClient.PLATFORM_LINUX,
            'android': LoginClient.PLATFORM_ANDROID,
            'ios': LoginClient.PLATFORM_IOS,
            'web': LoginClient.PLATFORM_WEB,
            'api': LoginClient.PLATFORM_WEB,
        }

    @staticmethod
    def client_type(client_type: str):
        return LoginClient.CLIENT_TYPE_WEB if client_type.lower() == 'web' else LoginClient.CLIENT_TYPE_CLIENT

    def update_login_status(self, username, uuid, platform, client_name, client_type='api', peer_id=None):
        user_qs = self.get_user_info(username)
        platform_val = self.platform.get(platform, platform) if platform else None
        client_type_val = self.client_type(client_type)
        if not self.db.objects.filter(user_id=user_qs.id, uuid=uuid).update(
                user=user_qs,
                uuid=uuid,
                peer_id=peer_id,
                login_status=True,
                client_type=client_type_val,
                platform=platform_val,
                client_name=client_name,
        ):
            self.db.objects.create(
                user=user_qs,
                uuid=uuid,
                peer_id=peer_id,
                login_status=True,
                client_type=client_type_val,
                platform=platform_val,
                client_name=client_name,
            )

        logger.info(f"更新登录状态: {username} - {uuid}")

    def update_logout_status(self, username, uuid, peer_id=None):
        """
        更新登出状态

        :param username: 用户名或用户对象
        :param uuid: 设备UUID
        :param peer_id: 设备ID（可选）
        """
        user_qs = self.get_user_info(username)

        if not user_qs:
            # 用户不存在，尝试直接通过 uuid 更新登出状态
            logger.warning(f"用户不存在，尝试直接更新登出状态: {username} - {uuid}")
            update_count = self.db.objects.filter(uuid=uuid).update(login_status=False)
            if update_count > 0:
                logger.info(f"通过 uuid 更新登出状态成功: {uuid}")
            else:
                logger.warning(f"未找到登录记录: {uuid}")
            return
            
        if not self.db.objects.filter(user_id=user_qs.id, uuid=uuid).update(
                user=user_qs,
                uuid=uuid,
                peer_id=peer_id,
                login_status=False,
        ):
            login_qs = self.db.objects.filter(
                user=user_qs,
                uuid=uuid,
                login_status=True
            ).first()
            if login_qs:
                self.db.objects.create(
                    user=user_qs,
                    uuid=uuid,
                    peer_id=peer_id,
                    login_status=False,
                    client_type=login_qs.client_type,
                    platform=login_qs.platform,
                    client_name=login_qs.client_name,
                )
            else:
                self.db.objects.create(
                    user=user_qs,
                    uuid=uuid,
                    peer_id=peer_id,
                    login_status=False,
                    client_type=self.db.CLIENT_TYPE_CLIENT,
                    platform=None,
                    client_name='',
                )

        logger.info(f"更新登出状态: {username} - {uuid}")

    def get_login_client_list(self, username):
        return self.db.objects.filter(user_id=self.get_user_info(username).id).all()


class TokenService(BaseService):
    """
    令牌服务类
    """

    db = Token

    def __init__(self, request: HttpRequest | None = None):
        self.request = request

    def create_token(self, username, uuid, client_type=Token.CLIENT_TYPE_API):
        """
        创建令牌

        :param username: 用户名
        :param uuid: 设备UUID
        :param client_type: 客户端类型字符串
        :return: 令牌
        """
        assert client_type in [Token.CLIENT_TYPE_WEB, Token.CLIENT_TYPE_CLIENT, Token.CLIENT_TYPE_API]
        user_qs = self.get_user_info(username)
        token = f"{get_randem_md5()}_{username}"

        qs, created = self.db.objects.update_or_create(
            user=user_qs,
            uuid=uuid,
            defaults={
                'token': token,
                'client_type': client_type,
                'created_at': get_local_time(),
                'last_used_at': get_local_time(),
            },
        )
        logger.info(f"{'创建' if created else '更新'}令牌: user: {username} uuid: {uuid} token: {token}")
        return token

    def check_token(self, token, timeout=None):
        if timeout is None:
            timeout = PublicConfig.TOKEN_TIMEOUT
        if _token := self.db.objects.filter(token=token).first():
            return _token.last_used_at > get_local_time() - timedelta(seconds=timeout)
        self.db.objects.filter(token=token).delete()
        return False

    def update_token(self, token):
        if _token := self.db.objects.filter(token=token).first():
            _token.last_used_at = get_local_time()
            _token.save()
            return True
        return False

    def update_token_by_uuid(self, uuid):
        if _token := self.db.objects.filter(uuid=uuid).first():
            _token.last_used_at = get_local_time()
            _token.save()
            logger.info(f"通过uuid更新令牌: {uuid} - {_token.token}")
            return True
        return False

    def renew_token_if_alive(self, uuid, timeout=None, min_interval=300):
        """
        仅当 token 有效且距上次续期超过 min_interval 秒时才写入。
        """
        if timeout is None:
            timeout = PublicConfig.TOKEN_TIMEOUT
        token_obj = self.db.objects.filter(uuid=uuid).first()
        if not token_obj:
            return False
        now = get_local_time()
        if token_obj.last_used_at < now - timedelta(seconds=timeout):
            return False
        if token_obj.last_used_at > now - timedelta(seconds=min_interval):
            return False
        token_obj.last_used_at = now
        token_obj.save(update_fields=['last_used_at'])
        logger.info(f"心跳续期令牌: uuid={uuid}")
        return True

    def delete_token(self, token):
        res = self.db.objects.filter(token=token).delete()
        logger.info(f"删除令牌: {token}")
        return res

    def delete_token_by_uuid(self, uuid):
        res = self.db.objects.filter(uuid=uuid).delete()
        logger.info(f"通过uuid删除令牌: {uuid}")
        return res

    def delete_token_by_user(self, username: User | str):
        user = self.get_user_info(username)
        res = self.db.objects.filter(user_id=user.id).delete()
        logger.info(f"通过用户名删除令牌: {username}")
        return res

    @property
    def authorization(self) -> str | None:
        if self.request:
            return self.request.headers.get("Authorization")[7:]
        return None

    @property
    def user_info(self) -> User | None:
        if self.request:
            auth = self.authorization
            username = auth.split("_")[-1]
            return UserService().get_user_by_name(username)
        return None

    @property
    def client_type(self):
        if self.request:
            auth = self.authorization
            username = auth.split("_")[-2]
            return UserService().get_user_by_name(username)
        return None

    @property
    def request_body(self) -> dict | list:
        if self.request:
            if body := self.request.body:
                return json.loads(body)
        return {}

    @property
    def request_query(self):
        if self.request:
            if params := self.request.GET:
                return params.dict()
        return {}

    def get_cur_uuid_by_token(self, token) -> str | None:
        if peer := self.db.objects.filter(token=token).first():
            return peer.uuid
        return None


class TagService:
    """
    标签服务类
    """

    db_tag = Tag
    db_client = PeerInfo
    db_client_tags = ClientTags

    def __init__(self, guid, user: User | str):
        self.guid = guid
        self.user = UserService().get_user_info(user)

    def get_tags_by_name(self, *tag_name):
        res = self.db_tag.objects.filter(tag__in=tag_name, guid_id=self.guid).all()
        logger.debug(f"获取用户标签: {self.guid} - {tag_name} - {res}")
        return res

    def get_tags_by_id(self, *tag_id):
        return self.db_tag.objects.filter(id__in=tag_id, guid_id=self.guid).all()

    def create_tag(self, tag, color):
        res = self.db_tag.objects.create(tag=tag, color=color, guid_id=self.guid)
        logger.info(f"创建标签: {self.guid} - {tag} - {color}")
        return res

    def delete_tag(self, *tag):
        """
        删除指定标签，并在关系表中移除这些标签（单次批量更新）。
        """
        tags_to_delete = {str(t) for t in tag if t is not None}
        if not tags_to_delete:
            return

        changed_instances = []
        for inst in self.db_client_tags.objects.filter(guid_id=self.guid).all():
            current_tags = self._parse_tags(inst.tags)
            if not current_tags:
                continue
            new_tags = [t for t in current_tags if t not in tags_to_delete]
            if new_tags != current_tags:
                inst.tags = new_tags
                changed_instances.append(inst)

        if changed_instances:
            self.db_client_tags.objects.bulk_update(changed_instances, ["tags"])

        self.db_tag.objects.filter(tag__in=tags_to_delete, guid_id=self.guid).delete()
        logger.info(f"删除标签: {self.guid} - {tags_to_delete}")

    def update_tag(self, tag, color=None, new_tag=None):
        data = {}
        if color:
            data["color"] = color
        if new_tag:
            data["tag"] = new_tag
        res = self.db_tag.objects.filter(tag=tag, guid_id=self.guid).update(**data)
        logger.info(f"更新标签: {self.guid} - {data}")
        return res

    def get_all_tags(self):
        return self.db_tag.objects.filter(guid_id=self.guid).all()

    def set_user_tag_by_peer_id(self, peer_id, tags):
        """
        为指定设备设置标签（覆盖式）。
        """
        tag_list = []
        for tag in self.get_tags_by_name(*list(tags)):
            tag_list.append(tag.id)

        if qs := self.user.user_tags.filter(peer_id=peer_id, guid_id=self.guid).first():
            qs.tags = tag_list if tag_list else []
            return qs.save()

        kwargs = {
            "peer_id": peer_id,
            "tags": tag_list,
            "guid_id": self.guid,
        }
        res = self.user.user_tags.create(**kwargs)
        logger.info(f"设置标签: {self.guid} - {peer_id} - {tag_list if tag_list else []}")
        return res

    def del_tag_by_peer_id(self, *peer_id):
        res = self.user.user_tags.filter(peer_id__in=peer_id, guid_id=self.guid).delete()
        logger.info(f"删除标签: {self.guid} - {peer_id}")
        return res

    def get_tags_by_peer_id(self, peer_id) -> list[str]:
        row = self.user.user_tags.filter(peer_id=peer_id, guid_id=self.guid).values("tags").first()
        if not row:
            return []
        return self._parse_tags(row.get("tags"))

    def get_tags_map(self, peer_ids: list[str]) -> dict[str, list[str]]:
        """
        批量获取多个设备的标签映射，避免 N+1 查询。
        """
        if not peer_ids:
            return {}
        rows = self.db_client_tags.objects.filter(guid_id=self.guid, peer_id__in=peer_ids).values("peer_id", "tags")
        logger.debug(f"批量获取标签: {self.guid} peers: {peer_ids} result: {rows}")
        result: dict[str, list[str]] = {}
        for row in rows:
            tags = self._parse_tags(row.get("tags") or [])
            tags_qs = self.get_tags_by_id(*tags)
            logger.debug(f"标签: {self.guid} peers: {row['peer_id']} tags: {tags} result: {tags_qs}")
            if not tags_qs:
                continue
            result[row["peer_id"]] = [str(tag.tag) for tag in tags_qs]
        logger.debug(f"批量获取标签结果: guid: {self.guid} peers: {peer_ids} result: {result}")
        return result

    @staticmethod
    def _parse_tags(raw) -> list[str]:
        """
        解析存储在数据库中的标签字段。
        兼容 JSONField 原生 list 和旧的字符串存储格式。
        """
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw]
        s = str(raw).strip()
        if not s:
            return []
        try:
            val = json.loads(s)
            if isinstance(val, list):
                return [str(x) for x in val]
        except Exception:
            pass
        import ast
        try:
            val = ast.literal_eval(s)
            if isinstance(val, list):
                return [str(x) for x in val]
        except Exception:
            pass
        return []


class LogService(BaseService):
    """
    日志服务类
    """

    db = Log

    def create_log(self, username, uuid, log_type, log_level="info", log_message=""):
        log = self.db.objects.create(
            user_id=self.get_user_info(username).id,
            uuid=uuid,
            log_level=log_level,
            operation_type=log_type,
            operation_object="log",
            operation_result="success",
            operation_detail=log_message,
            operation_time=get_local_time(),
        )
        logger.info(
            f'创建日志: 用户="{username}", UUID="{uuid}", 类型="{log_type}", 级别="{log_level}", 消息="{log_message}"'
        )
        return log


class AuditConnService(BaseService):
    """
    审计连接服务类
    """

    db = AuditConnLog

    def get(self, conn_id, action="new") -> AuditConnLog:
        return self.db.objects.filter(conn_id=conn_id, action=action).first()

    def log(
            self,
            conn_id,
            action,
            controlled_uuid,
            source_ip,
            session_id,
            controller_peer_id=None,
            type_=0,
            username=None
    ):
        if username:
            user_id = self.get_user_info(username).id
        else:
            user_id = ''
        if action:
            if action == "new":
                self.db.objects.create(
                    conn_id=conn_id,
                    action=action,
                    controlled_uuid=controlled_uuid,
                    initiating_ip=source_ip,
                    session_id=session_id,
                )
            else:
                connect_log = self.db.objects.filter(
                    conn_id=conn_id,
                    action="new",
                ).first()
                self.db.objects.create(
                    conn_id=conn_id,
                    action=action,
                    controlled_uuid=controlled_uuid,
                    controller_uuid=connect_log.controller_uuid,
                    initiating_ip=connect_log.initiating_ip,
                    session_id=session_id,
                    user_id=connect_log.user_id,
                    type=connect_log.type,
                )
        else:
            self.db.objects.filter(conn_id=conn_id).update(
                session_id=session_id,
                controller_uuid=self.get_peer_by_peer_id(controller_peer_id).uuid,
                user_id=user_id,
                type=type_,
            )
        logger.info(
            f'审计连接: conn_id="{conn_id}", action="{action}", controlled_uuid="{controlled_uuid}", source_ip="{source_ip}", session_id="{session_id}"'
        )


class AuditFileLogService(BaseService):
    """
    审计文件服务类
    """
    db = AuditFileLog

    @property
    def conn_service(self):
        return AuditConnService()

    @property
    def conn_id(self):
        qs = self.conn_service.db.objects.first()
        if qs.type == 1:
            return qs.conn_id
        return None

    def log(
            self,
            source_id,
            target_id,
            target_uuid,
            target_ip,
            operation_type,
            is_file,
            remote_path,
            file_info,
            user_id,
            file_num,
    ):
        res = self.db.objects.create(
            conn_id=self.conn_id,
            source_id=source_id,
            target_id=target_id,
            target_uuid=target_uuid,
            target_ip=target_ip,
            operation_type=operation_type,
            is_file=is_file,
            remote_path=remote_path,
            file_info=file_info,
            user_id=user_id,
            file_num=file_num,
        )
        logger.info(
            f'审计文件: source_id="{source_id}", target_id="{target_id}", target_uuid="{target_uuid}", operation_type="{operation_type}", is_file="{is_file}", remote_path="{remote_path}", user_id="{user_id}", file_num="{file_num}"'
        )
        return res


class PersonalService(BaseService):
    db = Personal

    def create_personal(self, personal_name, create_user, personal_type="public"):
        qs = self.get_user_info(create_user)
        personal = self.db.objects.create(
            personal_name=personal_name,
            creator=qs,
            personal_type=personal_type,
        )
        personal.personal_user.create(user=create_user)
        logger.info(
            f'创建地址簿: name: {personal_name}, create_user: {create_user}, type: {personal_type}, guid: {personal.guid}'
        )
        return personal

    def create_self_personal(self, username):
        qs = self.get_user_info(username)
        personal = self.create_personal(
            personal_name=f'{username}_personal',
            create_user=qs,
            personal_type="private"
        )
        return personal

    def get_personal(self, guid):
        return self.db.objects.filter(guid=guid).first()

    def get_all_personal(self):
        return self.db.objects.all()

    def get_peers_by_personal(self, guid):
        personal = self.get_personal(guid=guid)
        if personal:
            return personal.personal_peer.all()
        return []

    def delete_personal(self, guid):
        personal = self.get_personal(guid=guid)
        if personal and personal.personal_type != "private":
            logger.info(f'删除地址簿: {personal.personal_name} - {personal.personal_name}')
            return personal.delete()
        logger.info(f'无地址簿信息: {guid}')
        return None

    def add_personal_to_user(self, guid, username):
        user_qs = self.get_user_info(username)
        res = self.get_personal(guid=guid).personal_user.create(user_id=user_qs)
        logger.info(f'分享地址簿给用户: {guid} - {username}')
        return res

    def del_personal_to_user(self, guid, username):
        user_qs = self.get_user_info(username)
        res = (
            self.get_personal(guid=guid)
            .personal_user.filter(user_id=user_qs)
            .delete()
        )
        logger.info(f'取消分享地址簿: guid={guid}, username={username}')
        return res

    def get_personal_by_user(self, guid, user) -> Personal | None:
        return self.db.objects.filter(guid=guid, creator=user).first()

    def personal_name_exists(self, user, name, exclude_guid=None) -> bool:
        qs = self.db.objects.filter(creator=user, personal_name=name)
        if exclude_guid:
            qs = qs.exclude(guid=exclude_guid)
        return qs.exists()

    def rename_personal(self, guid, new_name) -> None:
        self.db.objects.filter(guid=guid).update(personal_name=new_name)
        logger.info(f'重命名地址簿: guid={guid}, new_name={new_name}')

    def get_personals_by_creator(self, user, q='', personal_type=None, ordering=('-created_at',)):
        qs = self.db.objects.filter(creator=user)
        if q:
            qs = qs.filter(guid__icontains=q)
        if personal_type in ('public', 'private'):
            qs = qs.filter(personal_type=personal_type)
        return qs.order_by(*ordering)

    def get_or_create_default_personal(self, user) -> Personal:
        personal, _ = self.db.objects.get_or_create(
            creator=user,
            personal_type='private',
            personal_name='默认地址簿',
            defaults={}
        )
        return personal

    def get_private_personal_guid(self, user) -> str:
        return user.user_personal.get(personal__personal_type='private').personal.guid

    def get_user_created_personals(self, user):
        return user.user_personal.all()

    def add_peer_to_personal(self, guid, peer_id):
        peer = PeerInfoService().get_peer_info_by_peer_id(peer_id)
        return self.get_personal(guid=guid).personal_peer.create(peer=peer)

    def del_peer_to_personal(self, guid, peer_id: list | str, user):
        if isinstance(peer_id, str):
            peer_id = [peer_id]
        peers = PeerInfoService().get_peers(*peer_id)

        alias_service = AliasService()
        alias_service.delete_alias(*peers, guid=guid)

        tag_service = TagService(guid=guid, user=user)
        tag_service.del_tag_by_peer_id(*peer_id)
        res = self.get_personal(guid=guid).personal_peer.filter(peer__in=peers).delete()
        logger.info(f'从地址簿移除设备: guid={guid}, peer_ids={peer_id}')
        return res


class AliasService(BaseService):
    db = Alias

    def set_alias(self, peer_id, alias, guid):
        kwargs = {
            "peer_id_id": peer_id,
            "guid_id": guid,
            "alias": alias,
        }
        updated = self.db.objects.filter(peer_id_id=peer_id, guid_id=guid).update(**kwargs)
        if not updated:
            self.db.objects.create(**kwargs)
        logger.info(f'设置别名: peer_id="{peer_id}", alias="{alias}", guid="{guid}"')

    def get_alias(self, guid):
        return self.db.objects.filter(guid=guid).all()

    def get_alias_map(self, guid: str, peer_ids: list[str]) -> dict[str, str]:
        if not peer_ids:
            return {}
        rows = self.db.objects.filter(guid=guid, peer_id__in=peer_ids).values("peer_id", "alias")
        return {row["peer_id"]: row["alias"] for row in rows}

    def delete_alias(self, *peer_ids, guid):
        return self.db.objects.filter(guid=guid, peer_id__in=peer_ids).delete()

    def count_by_personal(self, personal) -> int:
        return self.db.objects.filter(guid=personal).count()

    def get_alias_by_peer_and_personal(self, peer, personal) -> Alias | None:
        return self.db.objects.filter(peer_id=peer, guid=personal).first()

    def get_peer_alias_text(self, peer, user) -> str:
        default_personal = PersonalService().get_or_create_default_personal(user)
        alias_qs = self.db.objects.filter(peer_id=peer)
        prefer = alias_qs.filter(guid=default_personal).values_list('alias', flat=True).first()
        if prefer is not None:
            return prefer
        fallback = alias_qs.values_list('alias', flat=True).first()
        return fallback or ''

    def update_or_create_alias(self, peer, personal, alias_text) -> None:
        self.db.objects.update_or_create(
            peer_id=peer,
            guid=personal,
            defaults={'alias': alias_text}
        )

    def delete_alias_by_peer_and_personal(self, peer, personal) -> None:
        self.db.objects.filter(peer_id=peer, guid=personal).delete()


class ClientTagsService(BaseService):
    """
    设备标签关联服务类（面向 Web 视图的轻量标签操作）
    """
    db = ClientTags

    def get_tags_text_by_peer_in_personal(self, peer_id, guid) -> str:
        obj = self.db.objects.filter(peer_id=peer_id, guid_id=guid).first()
        return obj.tags if obj else ''

    def set_tags_for_peer_in_personal(self, user, peer_id, guid, tags_text) -> None:
        self.db.objects.filter(peer_id=peer_id, guid_id=guid).delete()
        if tags_text:
            self.db.objects.create(
                user=user,
                peer_id=peer_id,
                tags=tags_text,
                guid_id=guid
            )

    def get_user_peer_tags(self, user, peer_id) -> list:
        return list(
            self.db.objects.filter(user=user, peer_id=peer_id).values_list('tags', flat=True)
        )

    def update_or_create_client_tag(self, user, peer_id, personal, tags) -> None:
        self.db.objects.update_or_create(
            user=user,
            peer_id=peer_id,
            guid=personal,
            defaults={'tags': tags}
        )

    def delete_client_tag(self, user, peer_id, personal) -> None:
        self.db.objects.filter(user=user, peer_id=peer_id, guid=personal).delete()


class SharePersonalService(BaseService):
    """
    地址簿分享服务类 - 使用新的 ShareToUser / ShareToGroup 表
    """

    def __init__(self, count_user: User):
        self.user = count_user

    def share_to_user(self, guid, username):
        user = PersonalService().get_user_info(username)
        return ShareToUser.objects.create(
            personal_id=guid,
            to_user=user,
            from_user=self.user,
        )

    def share_to_group(self, guid, group_name):
        group = GroupService().get_group_by_name(group_name)
        return ShareToGroup.objects.create(
            personal_id=guid,
            to_group=group,
            from_user=self.user,
        )

    def get_user_personals(self):
        group_id = self.user.userprofile.group_id

        user_share_guids = ShareToUser.objects.filter(
            to_user=self.user
        ).values_list("personal_id", flat=True)

        group_share_guids = ShareToGroup.objects.filter(
            to_group_id=group_id
        ).values_list("personal_id", flat=True)

        all_guids = set(user_share_guids) | set(group_share_guids)

        return PersonalService.db.objects.filter(guid__in=all_guids).all()


class DeviceGroupService(BaseService):
    """
    设备组服务

    提供设备组的查询操作。
    """
    db = DeviceGroup

    def get_accessible_groups(self, user: User) -> list[DeviceGroup]:
        """
        获取用户可访问的设备组（基于全局权限）

        Super admin 或拥有 VIEW 权限时返回所有设备组，否则返回空列表。

        :param user: 用户对象
        :return: 设备组列表
        """
        if user.is_superuser or PermissionService().has_perm(user, DevicePermission.VIEW):
            return list(self.db.objects.all())
        return []

    def get_list(self, page: int = 1, page_size: int = 100) -> dict:
        """
        分页查询设备组

        :param page: 页码
        :param page_size: 每页条数
        :return: 包含 total 和 data 的字典
        """
        qs = self.db.objects.all()
        total = qs.count()
        start = (page - 1) * page_size
        data = list(qs[start:start + page_size])
        return {'total': total, 'data': data}


class UserConfigService(BaseService):
    """
    用户配置服务类
    """
    def __init__(self, user: User | str):
        self.user = self.get_user_info(user)

    def get_config(self):
        return UserConfig.objects.filter(user=self.user).all()

    def set_language(self, language):
        UserConfig.objects.update_or_create(
            user=self.user,
            config_name='language',
            defaults={
                "config_value": language
            }
        )

    def get_language(self):
        if qs := UserConfig.objects.filter(user=self.user, config_name='language').first():
            return qs.config_value
        return None

    def get_legacy_ab(self) -> str | None:
        """
        获取 Legacy 地址簿数据

        :return: JSON 字符串或 None
        """
        qs = UserConfig.objects.filter(user=self.user, config_name='legacy_ab').first()
        return qs.config_value if qs else None

    def set_legacy_ab(self, data: str) -> None:
        """
        存储 Legacy 地址簿数据

        :param data: 地址簿 JSON 字符串
        """
        UserConfig.objects.update_or_create(
            user=self.user,
            config_name='legacy_ab',
            defaults={"config_value": data}
        )


# ---------------------------------------------------------------------------
# 权限系统服务
# ---------------------------------------------------------------------------


class RoleService(BaseService):
    """
    角色管理服务

    提供角色的 CRUD、用户与角色的绑定/解绑操作。
    """

    db = Role

    def create_role(self, name: str, note: str = "", permission: int = 0) -> Role:
        """
        创建角色

        :param name: 角色名称
        :param note: 备注
        :param permission: 全局权限位（DevicePermission bitflag 并集）
        :return: 新角色对象
        :rtype: Role
        """
        role = self.db.objects.create(name=name, note=note, permission=permission)
        logger.info(f"创建角色: {name}")
        return role

    def update_role(self, role_id: int, **kwargs) -> Role | None:
        """
        更新角色信息

        :param role_id: 角色 ID
        :return: 更新后的角色对象，不存在返回 None
        :rtype: Role | None
        """
        role = self.db.objects.filter(id=role_id).first()
        if not role:
            return None
        if role.is_default and "name" in kwargs:
            kwargs.pop("name")
        for field, value in kwargs.items():
            setattr(role, field, value)
        role.save()
        logger.info(f"更新角色: id={role_id}, fields={list(kwargs.keys())}")
        return role

    def delete_role(self, role_id: int) -> bool:
        """
        删除角色（default 角色不可删除）

        :param role_id: 角色 ID
        :return: 是否删除成功
        :rtype: bool
        """
        role = self.db.objects.filter(id=role_id).first()
        if not role or role.is_default:
            return False
        role.delete()
        logger.info(f"删除角色: {role.name}")
        return True

    def get_default_role(self) -> Role:
        """
        获取默认角色，不存在则创建

        :return: 默认角色对象
        :rtype: Role
        """
        role, _ = self.db.objects.get_or_create(
            name="default",
            defaults={"note": "默认角色", "is_default": True},
        )
        return role

    def list_roles(self):
        """
        获取所有角色列表

        :return: 角色查询集
        :rtype: QuerySet[Role]
        """
        return self.db.objects.all()

    def get_role_by_id(self, role_id: int) -> Role | None:
        """
        根据 ID 获取角色

        :param role_id: 角色 ID
        :return: 角色对象或 None
        :rtype: Role | None
        """
        return self.db.objects.filter(id=role_id).first()

    def assign_role_to_user(self, user: User | str, role: Role | int) -> None:
        """
        为用户分配角色

        :param user: 用户对象或用户名
        :param role: 角色对象或角色 ID
        """
        user = self.get_user_info(user)
        if isinstance(role, int):
            role = self.get_role_by_id(role)
        if user and role:
            UserRole.objects.get_or_create(user=user, role=role)
            logger.info(f"为用户 {user.username} 分配角色 {role.name}")

    def remove_role_from_user(self, user: User | str, role: Role | int) -> None:
        """
        移除用户的角色

        :param user: 用户对象或用户名
        :param role: 角色对象或角色 ID
        """
        user = self.get_user_info(user)
        if isinstance(role, int):
            role = self.get_role_by_id(role)
        if user and role:
            UserRole.objects.filter(user=user, role=role).delete()
            logger.info(f"移除用户 {user.username} 的角色 {role.name}")

    def get_user_roles(self, user: User | str) -> list[Role]:
        """
        获取用户的所有角色

        :param user: 用户对象或用户名
        :return: 角色列表
        :rtype: list[Role]
        """
        user = self.get_user_info(user)
        if not user:
            return []
        return list(
            self.db.objects.filter(role_users__user=user)
        )

    def get_role_users(self, role: Role | int):
        """
        获取拥有指定角色的所有用户

        :param role: 角色对象或角色 ID
        :return: 用户查询集
        :rtype: QuerySet[User]
        """
        role_id = role.id if isinstance(role, Role) else role
        return User.objects.filter(user_roles__role_id=role_id)

    def assign_role_to_group(self, group: Group | int, role_id: int) -> None:
        """
        为用户组分配角色

        :param group: 用户组对象或用户组 ID
        :param role_id: 角色 ID
        """
        group_id = group.id if isinstance(group, Group) else group
        GroupRole.objects.get_or_create(group_id=group_id, role_id=role_id)
        logger.info(f"为用户组 {group_id} 分配角色 {role_id}")

    def remove_role_from_group(self, group: Group | int, role_id: int) -> None:
        """
        移除用户组的角色

        :param group: 用户组对象或用户组 ID
        :param role_id: 角色 ID
        """
        group_id = group.id if isinstance(group, Group) else group
        GroupRole.objects.filter(group_id=group_id, role_id=role_id).delete()
        logger.info(f"移除用户组 {group_id} 的角色 {role_id}")

    def get_group_roles(self, group: Group | int) -> list[Role]:
        """
        获取用户组的所有角色

        :param group: 用户组对象或用户组 ID
        :return: 角色列表
        :rtype: list[Role]
        """
        group_id = group.id if isinstance(group, Group) else group
        return list(
            self.db.objects.filter(role_groups__group_id=group_id)
        )


class DeviceGroupPeerService(BaseService):
    """
    设备-设备组关联服务

    管理设备与设备组的多对多关系。当前 Service 层限制一个设备只能属于一个组。
    """

    db = DeviceGroupPeer

    def add_peer_to_group(self, peer: PeerInfo | int, group: DeviceGroup | int) -> DeviceGroupPeer | None:
        """
        将设备加入设备组（当前限制一对多：设备已有组则拒绝）

        :param peer: 设备对象或设备 ID
        :param group: 设备组对象或设备组 ID
        :return: 创建的关联对象，已有组则返回 None
        :rtype: DeviceGroupPeer | None
        """
        peer_id = peer.id if isinstance(peer, PeerInfo) else peer
        group_id = group.id if isinstance(group, DeviceGroup) else group

        if self.db.objects.filter(peer_id=peer_id).exists():
            logger.warning(f"设备 {peer_id} 已属于某个设备组，不可重复加入")
            return None

        obj = self.db.objects.create(peer_id=peer_id, device_group_id=group_id)
        logger.info(f"设备 {peer_id} 加入设备组 {group_id}")
        return obj

    def remove_peer_from_group(self, peer: PeerInfo | int, group: DeviceGroup | int) -> bool:
        """
        将设备从设备组移除

        :param peer: 设备对象或设备 ID
        :param group: 设备组对象或设备组 ID
        :return: 是否移除成功
        :rtype: bool
        """
        peer_id = peer.id if isinstance(peer, PeerInfo) else peer
        group_id = group.id if isinstance(group, DeviceGroup) else group
        count, _ = self.db.objects.filter(peer_id=peer_id, device_group_id=group_id).delete()
        return count > 0

    def get_groups_for_peer(self, peer: PeerInfo | int) -> list[DeviceGroup]:
        """
        获取设备所属的所有设备组

        :param peer: 设备对象或设备 ID
        :return: 设备组列表
        :rtype: list[DeviceGroup]
        """
        peer_id = peer.id if isinstance(peer, PeerInfo) else peer
        return list(
            DeviceGroup.objects.filter(group_peers__peer_id=peer_id)
        )

    def get_peers_in_group(self, group: DeviceGroup | int):
        """
        获取设备组内所有设备

        :param group: 设备组对象或设备组 ID
        :return: 设备查询集
        :rtype: QuerySet[PeerInfo]
        """
        group_id = group.id if isinstance(group, DeviceGroup) else group
        return PeerInfo.objects.filter(peer_groups__device_group_id=group_id)

    def get_group_ids_for_peer(self, peer: PeerInfo | int) -> set[int]:
        """
        获取设备所属设备组的 ID 集合

        :param peer: 设备对象或设备 ID
        :return: 设备组 ID 集合
        :rtype: set[int]
        """
        peer_id = peer.id if isinstance(peer, PeerInfo) else peer
        return set(
            self.db.objects.filter(peer_id=peer_id).values_list("device_group_id", flat=True)
        )


class PermissionService(BaseService):
    """
    全局权限服务

    用户最终权限 = 直接角色权限并集 | 所属用户组角色权限并集。
    superuser 拥有所有权限。
    """

    def get_user_effective_perm(self, user: User) -> int:
        """
        计算用户的全局有效权限值

        :param user: 用户对象
        :return: 权限位值
        :rtype: int
        """
        if user.is_superuser:
            return DevicePermission.FULL
        perm = 0
        for role_perm in UserRole.objects.filter(user=user).values_list('role__permission', flat=True):
            perm |= role_perm
        try:
            group_id = user.userprofile.group_id
        except (UserProfile.DoesNotExist, AttributeError):
            group_id = None
        if group_id:
            for role_perm in GroupRole.objects.filter(group_id=group_id).values_list('role__permission', flat=True):
                perm |= role_perm
        return perm

    def has_perm(self, user: User, perm_flag: int) -> bool:
        """
        判断用户是否拥有指定全局权限

        :param user: 用户对象
        :param perm_flag: 权限位（如 DevicePermission.VIEW）
        :return: 是否拥有权限
        :rtype: bool
        """
        return (self.get_user_effective_perm(user) & perm_flag) == perm_flag
