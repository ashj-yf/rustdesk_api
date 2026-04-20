"""
Data migration: 初始化权限系统数据

1. 将现有 PeerInfo.device_group FK 数据同步到 DeviceGroupPeer 中间表
2. 创建 default 角色
3. 为所有现有活跃用户绑定 default 角色
"""

from django.db import migrations


def forwards(apps, schema_editor):
    PeerInfo = apps.get_model("db", "PeerInfo")
    DeviceGroupPeer = apps.get_model("db", "DeviceGroupPeer")
    Role = apps.get_model("db", "Role")
    UserRole = apps.get_model("db", "UserRole")
    User = apps.get_model("auth", "User")

    # 1) 同步 PeerInfo.device_group -> DeviceGroupPeer
    peers_with_group = PeerInfo.objects.filter(
        device_group__isnull=False
    ).values_list("id", "device_group_id")

    existing = set(
        DeviceGroupPeer.objects.values_list("peer_id", "device_group_id")
    )
    to_create = [
        DeviceGroupPeer(peer_id=peer_id, device_group_id=group_id)
        for peer_id, group_id in peers_with_group
        if (peer_id, group_id) not in existing
    ]
    if to_create:
        DeviceGroupPeer.objects.bulk_create(to_create, ignore_conflicts=True)

    # 2) 创建 default 角色，默认拥有完整权限
    default_role, _ = Role.objects.get_or_create(
        name="default",
        defaults={"note": "默认角色", "is_default": True, "permission": 15},
    )

    # 3) 为所有活跃用户绑定 default 角色
    active_user_ids = User.objects.filter(is_active=True).values_list("id", flat=True)
    existing_bindings = set(
        UserRole.objects.filter(role=default_role).values_list("user_id", flat=True)
    )
    user_roles = [
        UserRole(user_id=uid, role=default_role)
        for uid in active_user_ids
        if uid not in existing_bindings
    ]
    if user_roles:
        UserRole.objects.bulk_create(user_roles, ignore_conflicts=True)


def backwards(apps, schema_editor):
    Role = apps.get_model("db", "Role")
    UserRole = apps.get_model("db", "UserRole")
    DeviceGroupPeer = apps.get_model("db", "DeviceGroupPeer")

    UserRole.objects.all().delete()
    Role.objects.filter(name="default", is_default=True).delete()
    DeviceGroupPeer.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0006_permission_system_models"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
