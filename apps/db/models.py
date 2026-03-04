from django.contrib.auth.models import User, Group
from django.db import models

from common.utils import get_uuid


class TimestampMixin(models.Model):
    """
    提供 created_at / updated_at 的抽象基类
    """

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        abstract = True


class HeartBeat(models.Model):
    """
    心跳测试模型
    """

    peer_id = models.CharField(max_length=255, verbose_name="客户端ID", unique=True)
    modified_at = models.DateTimeField(verbose_name="修改时间")
    uuid = models.CharField(max_length=255, verbose_name="设备UUID", unique=True)
    ver = models.CharField(max_length=255, default="", null=True, verbose_name="版本号")

    class Meta:
        verbose_name = "心跳测试"
        verbose_name_plural = verbose_name
        ordering = ["-modified_at"]
        db_table = "heartbeat"
        unique_together = [["uuid", "peer_id"]]


class PeerInfo(TimestampMixin):
    """
    客户端上报的客户端信息模型
    """

    peer_id = models.CharField(max_length=255, verbose_name="客户端ID", unique=True)
    cpu = models.TextField(verbose_name="CPU信息")
    device_name = models.CharField(max_length=255, verbose_name="主机名")
    memory = models.CharField(max_length=50, verbose_name="内存")
    os = models.TextField(verbose_name="操作系统")
    username = models.CharField(
        max_length=255, verbose_name="用户名", null=True, blank=True, default=""
    )
    uuid = models.CharField(max_length=255, unique=True, verbose_name="设备UUID")
    version = models.CharField(max_length=50, verbose_name="客户端版本")

    class Meta:
        verbose_name = "客户端上报的客户端信息"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]
        db_table = "peer_info"
        unique_together = [["uuid", "peer_id"]]

    def __str__(self):
        return f"{self.device_name}-({self.uuid})"


class Personal(TimestampMixin):
    """
    地址簿
    """

    guid = models.CharField(
        max_length=50, verbose_name="GUID", default=get_uuid, unique=True
    )
    personal_name = models.CharField(max_length=50, verbose_name="地址簿名称")
    creator = models.ForeignKey(
        User,
        to_field="id",
        on_delete=models.CASCADE,
        related_name="personal_create_user",
        db_column="create_user_id_id",
    )
    personal_type = models.CharField(
        verbose_name="地址簿类型",
        default="public",
        choices=[("public", "公开"), ("private", "私有")],
    )

    class Meta:
        verbose_name = "地址簿"
        verbose_name_plural = "地址簿"
        ordering = ["-created_at"]
        db_table = "personal"
        unique_together = [["personal_name", "creator"]]


class Tag(models.Model):
    """
    标签模型
    """

    tag = models.CharField(max_length=255, verbose_name="标签名称")
    color = models.CharField(max_length=50, verbose_name="标签颜色")
    guid = models.ForeignKey(
        Personal,
        to_field="guid",
        on_delete=models.CASCADE,
        related_name="tags",
        db_column="guid",
        db_index=True,
    )

    class Meta:
        verbose_name = "标签"
        db_table = "tag"
        unique_together = [["tag", "guid"]]

    def __str__(self):
        return f"{self._meta.db_table}--{self.tag, self.color, self.guid_id}"


class ClientTags(models.Model):
    """
    设备标签关联模型
    """

    user = models.ForeignKey(
        User,
        to_field="id",
        on_delete=models.CASCADE,
        verbose_name="用户名",
        related_name="user_tags",
        db_column="user_id_id",
    )
    peer_id = models.CharField(max_length=255, verbose_name="设备ID", db_index=True)
    tags = models.JSONField(verbose_name="标签ID列表", default=list)
    guid = models.ForeignKey(
        Personal,
        to_field="guid",
        on_delete=models.CASCADE,
        related_name="client_tags",
        db_column="guid",
        db_index=True,
    )

    class Meta:
        verbose_name = "设备标签关联"
        db_table = "client_tags"
        unique_together = [["peer_id", "guid"]]

    def __str__(self):
        return f"{self._meta.db_table}--{self.user_id, self.peer_id, self.tags, self.guid_id}"


class Token(TimestampMixin):
    """
    令牌模型
    """

    CLIENT_TYPE_WEB = "web"
    CLIENT_TYPE_CLIENT = "client"
    CLIENT_TYPE_API = "api"
    CLIENT_TYPE_CHOICES = [
        (CLIENT_TYPE_WEB, "web"),
        (CLIENT_TYPE_CLIENT, "client"),
        (CLIENT_TYPE_API, "api"),
    ]

    user = models.ForeignKey(
        User,
        to_field="id",
        on_delete=models.CASCADE,
        verbose_name="用户名",
        db_column="user_id_id",
    )
    uuid = models.CharField(max_length=255, verbose_name="设备UUID", db_index=True)
    token = models.CharField(max_length=255, verbose_name="令牌", db_index=True)
    client_type = models.CharField(
        max_length=255,
        verbose_name="客户端类型",
        choices=CLIENT_TYPE_CHOICES,
        default=CLIENT_TYPE_CLIENT,
    )
    last_used_at = models.DateTimeField(auto_now=True, verbose_name="最后使用时间")

    class Meta:
        verbose_name = "令牌"
        verbose_name_plural = "令牌"
        ordering = ["-created_at"]
        db_table = "token"
        unique_together = [["user", "uuid"]]

    def __str__(self):
        return f"{self.user} ({self.uuid}-{self.token})"


class LoginClient(models.Model):
    """
    登录客户端模型
    """

    CLIENT_TYPE_WEB = "web"
    CLIENT_TYPE_CLIENT = "client"
    CLIENT_TYPE_CHOICES = [
        (CLIENT_TYPE_WEB, "web"),
        (CLIENT_TYPE_CLIENT, "client"),
    ]

    PLATFORM_WINDOWS = "windows"
    PLATFORM_MACOS = "macos"
    PLATFORM_LINUX = "linux"
    PLATFORM_ANDROID = "android"
    PLATFORM_IOS = "ios"
    PLATFORM_WEB = "web"
    PLATFORM_CHOICES = [
        (PLATFORM_WINDOWS, "Windows"),
        (PLATFORM_MACOS, "MacOS"),
        (PLATFORM_LINUX, "Linux"),
        (PLATFORM_ANDROID, "Android"),
        (PLATFORM_IOS, "iOS"),
        (PLATFORM_WEB, "Web"),
    ]

    user = models.ForeignKey(
        User,
        to_field="id",
        on_delete=models.CASCADE,
        verbose_name="用户名",
        db_column="user_id_id",
    )
    peer_id = models.CharField(max_length=255, verbose_name="客户端ID")
    uuid = models.CharField(max_length=255, verbose_name="设备UUID", db_index=True)
    client_type = models.CharField(
        max_length=255,
        verbose_name="客户端类型",
        choices=CLIENT_TYPE_CHOICES,
        default=CLIENT_TYPE_CLIENT,
    )
    platform = models.CharField(
        max_length=255, verbose_name="平台", choices=PLATFORM_CHOICES, null=True
    )
    client_name = models.CharField(
        max_length=255, verbose_name="客户端名称", default="", blank=True
    )
    login_status = models.BooleanField(default=True, verbose_name="登录状态")

    class Meta:
        verbose_name = "登录客户端"
        verbose_name_plural = "登录客户端"
        ordering = ["-user"]
        db_table = "login_client"


class Log(models.Model):
    """
    日志模型
    """

    user = models.ForeignKey(
        User,
        to_field="id",
        on_delete=models.CASCADE,
        verbose_name="用户名",
        null=True,
        default=None,
        db_column="user_id_id",
    )
    uuid = models.ForeignKey(
        PeerInfo, to_field="uuid", on_delete=models.CASCADE, verbose_name="设备UUID"
    )
    log_level = models.CharField(
        max_length=50,
        verbose_name="日志类型",
        choices=[("info", "信息"), ("warning", "警告"), ("error", "错误")],
    )
    operation_type = models.CharField(
        max_length=50,
        verbose_name="操作类型",
        choices=[
            ("add", "添加"),
            ("delete", "删除"),
            ("update", "更新"),
            ("query", "查询"),
            ("other", "其他"),
        ],
    )
    operation_object = models.CharField(
        max_length=50,
        verbose_name="操作对象",
        choices=[
            ("tag", "标签"),
            ("client", "设备"),
            ("user", "用户"),
            ("token", "令牌"),
            ("login_client", "登录客户端"),
            ("login_log", "登录日志"),
            ("log", "日志"),
            ("tag_to_client", "标签与设备关系"),
            ("user_to_tag", "用户与标签关系"),
            ("system_info", "系统信息"),
            ("heart_beat", "心跳包"),
            ("config", "配置"),
            ("file", "文件"),
            ("file_to_client", "文件与设备关系"),
            ("file_to_tag", "文件与标签关系"),
            ("file_to_user", "文件与用户关系"),
            ("file_to_file", "文件与文件关系"),
        ],
    )
    operation_result = models.CharField(
        max_length=50,
        verbose_name="操作结果",
        choices=[("success", "成功"), ("fail", "失败")],
    )
    operation_detail = models.TextField(verbose_name="操作详情", null=True, default="")
    operation_time = models.DateTimeField(auto_now_add=True, verbose_name="操作时间")

    class Meta:
        verbose_name = "日志"
        verbose_name_plural = "日志"
        ordering = ["-operation_time"]
        db_table = "log"


class AuditConnLog(models.Model):
    """
    审计日志模型
    """

    action = models.CharField(max_length=50, verbose_name="操作类型")
    conn_id = models.IntegerField(verbose_name="连接ID")
    initiating_ip = models.CharField(max_length=50, verbose_name="发起IP")
    session_id = models.CharField(max_length=50, verbose_name="会话ID", null=True)
    controller_uuid = models.CharField(
        max_length=255, verbose_name="控制端UUID", null=True
    )
    controlled_uuid = models.CharField(max_length=255, verbose_name="被控端UUID")
    type = models.IntegerField(
        verbose_name="类型",
        default=0,
        choices=[
            (0, "connect"),
            (1, "file_transfer"),
            (2, "tcp_tunnel"),
            (3, "camera"),
        ],
    )
    user_id = models.CharField(max_length=50, verbose_name="发起连接的用户", null=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "审计日志"
        verbose_name_plural = "审计日志"
        ordering = ["-created_at"]
        db_table = "audit_log"

    def __str__(self):
        return f"{self.action} {self.conn_id} {self.initiating_ip} {self.session_id} {self.controller_uuid} {self.controlled_uuid} {self.type} {self.user_id} {self.created_at}"


AutidConnLog = AuditConnLog


class AuditFileLog(models.Model):
    """
    审计文件模型
    """

    conn_id = models.IntegerField(verbose_name="连接ID", null=True)
    source_id = models.CharField(max_length=255, verbose_name="控制端ID")
    target_id = models.CharField(max_length=255, verbose_name="被控端ID")
    target_uuid = models.CharField(max_length=255, verbose_name="被控端UUID")
    target_ip = models.CharField(max_length=255, verbose_name="被控端IP")
    operation_type = models.IntegerField(
        verbose_name="操作类型", default=1, choices=[(1, "upload"), (0, "download")]
    )
    is_file = models.BooleanField(verbose_name="是否文件")
    remote_path = models.CharField(verbose_name="远程路径", null=True)
    file_info = models.TextField(verbose_name="文件信息", null=True)
    user_id = models.CharField(max_length=50, verbose_name="操作用户", null=True)
    file_num = models.IntegerField(verbose_name="文件数量", null=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "审计文件"
        verbose_name_plural = "审计文件"
        ordering = ["-created_at"]
        db_table = "audit_file"


class UserProfile(models.Model):
    """
    用户配置模型
    """

    user = models.OneToOneField(
        User, to_field="id", on_delete=models.CASCADE, related_name="userprofile"
    )
    group = models.ForeignKey(
        Group, to_field="id", on_delete=models.CASCADE, related_name="userprofile_group"
    )

    class Meta:
        verbose_name = "用户配置"
        verbose_name_plural = "用户配置"
        db_table = "user_profile"

    def __str__(self):
        return f'{self.user.username} {self.group.name if self.group else "None"}'


# Backward-compatible alias for the old misspelled name
UserPrefile = UserProfile


class UserPersonal(models.Model):
    """
    用户与个人地址簿关系模型
    """

    user = models.ForeignKey(
        User, to_field="id", on_delete=models.CASCADE, related_name="user_personal"
    )
    personal = models.ForeignKey(
        Personal, to_field="id", on_delete=models.CASCADE, related_name="personal_user"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "用户与个人地址簿关系"
        verbose_name_plural = "用户与个人地址簿关系"
        ordering = ["-created_at"]
        db_table = "user_personal"


class PeerPersonal(models.Model):
    """
    设备与个人地址簿关系模型
    """

    peer = models.ForeignKey(
        PeerInfo, to_field="id", on_delete=models.CASCADE, related_name="peer_personal"
    )
    personal = models.ForeignKey(
        Personal,
        to_field="guid",
        on_delete=models.CASCADE,
        related_name="personal_peer",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "设备与个人地址簿关系模型"
        verbose_name_plural = "设备与个人地址簿关系模型"
        ordering = ["-created_at"]
        db_table = "peer_personal"


class ShareToUser(TimestampMixin):
    """
    地址簿分享给用户
    """

    personal = models.ForeignKey(
        Personal,
        to_field="guid",
        on_delete=models.CASCADE,
        related_name="shared_to_users",
        db_column="guid",
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_shares",
        db_column="to_share_id",
    )
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_shares",
        db_column="from_share_id",
    )

    class Meta:
        verbose_name = "分享地址簿给用户"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]
        db_table = "share_to_user"
        unique_together = [["personal", "to_user"]]


class ShareToGroup(TimestampMixin):
    """
    地址簿分享给用户组
    """

    personal = models.ForeignKey(
        Personal,
        to_field="guid",
        on_delete=models.CASCADE,
        related_name="shared_to_groups",
        db_column="guid",
    )
    to_group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="received_group_shares",
        db_column="to_share_id",
    )
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_group_shares",
        db_column="from_share_id",
    )

    class Meta:
        verbose_name = "分享地址簿给用户组"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]
        db_table = "share_to_group"
        unique_together = [["personal", "to_group"]]


# Keep backward-compatible SharePersonal as a reference
# The old SharePersonal table is replaced by ShareToUser and ShareToGroup
class SharePersonal(models.Model):
    """
    [已废弃] 分享地址簿记录 - 请使用 ShareToUser / ShareToGroup
    """

    guid = models.CharField(max_length=50, verbose_name="guid")
    to_share_id = models.CharField(
        max_length=50, verbose_name="被分享者的ID，被分享者可以是用户，也可以是用户组"
    )
    from_share_id = models.CharField(
        max_length=50, verbose_name="分享者的ID，分享者可以是用户，也可以是用户组"
    )
    to_share_type = models.IntegerField(
        verbose_name="被分享者的类型，1:用户，2:用户组",
        choices=[(1, "用户"), (2, "用户组")],
    )
    from_share_type = models.IntegerField(
        verbose_name="分享者的类型，1:用户，2:用户组",
        choices=[(1, "用户"), (2, "用户组")],
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "分享地址簿记录"
        verbose_name_plural = "分享地址簿记录"
        ordering = ["-created_at"]
        db_table = "share_personal"
        unique_together = [["guid", "to_share_id"]]
        managed = False


class Alias(models.Model):
    """
    别名模型
    """

    alias = models.CharField(max_length=50, verbose_name="别名")
    peer_id = models.ForeignKey(
        PeerInfo,
        to_field="peer_id",
        on_delete=models.CASCADE,
        related_name="alias_peer_id",
    )
    guid = models.ForeignKey(
        Personal, to_field="guid", on_delete=models.CASCADE, related_name="alias_guid"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "别名"
        verbose_name_plural = "别名"
        ordering = ["-created_at"]
        db_table = "alias"
        unique_together = [["peer_id", "guid"]]


class UserConfig(models.Model):
    """
    用户配置模型（支持多配置项）
    """

    user = models.ForeignKey(
        User,
        to_field="id",
        on_delete=models.CASCADE,
        related_name="user_configs",
        db_column="user_id_id",
    )
    config_name = models.CharField(max_length=50, verbose_name="配置名称")
    config_value = models.TextField(verbose_name="配置值")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "用户配置"
        verbose_name_plural = "用户配置"
        ordering = ["-created_at"]
        db_table = "user_config"
        unique_together = [["user", "config_name"]]
