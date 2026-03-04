import json
import logging
import time
from datetime import timedelta
from typing import TypeVar

from django.contrib.auth.models import User, Group
from django.db import models
from django.db import transaction, OperationalError
from django.db.models import Q
from django.http import HttpRequest

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
    ShareToUser,
    ShareToGroup,
    UserConfig,
)
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
        user_qs = self.get_user_info(username)
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
            self.db.objects.create(
                user=user_qs,
                uuid=uuid,
                peer_id=peer_id,
                login_status=False,
                client_type=login_qs.client_type,
                platform=login_qs.platform,
                client_name=login_qs.client_name,
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

        if qs := self.db.objects.filter(user_id=user_qs.id, uuid=uuid, client_type=client_type).first():
            qs.token = token
            qs.created_at = get_local_time()
            qs.last_used_at = get_local_time()
            qs.save()
            logger.info(f"更新令牌: user: {username} uuid: {uuid} token: {token}")
        else:
            self.db.objects.create(
                user=user_qs,
                uuid=uuid,
                token=token,
                client_type=client_type,
                created_at=get_local_time(),
                last_used_at=get_local_time(),
            )
            logger.info(f"创建令牌: user: {username} uuid: {uuid} token: {token}")
        return token

    def check_token(self, token, timeout=3600):
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

    def renew_token_if_alive(self, uuid, timeout=3600, min_interval=300):
        """
        仅当 token 有效且距上次续期超过 min_interval 秒时才写入。
        """
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
