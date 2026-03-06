from django.urls import path

from apps.web import view_auth, view_home, view_user, view_personal, view_permission, view_group

urlpatterns = [
    path('', view_auth.index),
    path('login', view_auth.login, name='web_login'),
    path('logout', view_auth.logout, name='web_logout'),
    path('home', view_home.home, name='web_home'),
    path('nav-content', view_home.nav_content, name='web_nav_content'),
    path('device/rename-alias', view_home.rename_alias, name='web_rename_alias'),
    path('device/detail', view_home.device_detail, name='web_device_detail'),
    path('device/update', view_home.update_device, name='web_device_update'),
    path('device/statuses', view_home.device_statuses, name='web_device_statuses'),
    path('device/delete', view_home.delete_device, name='web_device_delete'),
    path('device/toggle', view_home.toggle_device, name='web_device_toggle'),
    path('device/update-note', view_home.update_note, name='web_device_note'),
    path('device/tags', view_home.device_tags, name='web_device_tags'),
    path('user/update', view_user.update_user, name='web_user_update'),
    path('user/reset-password', view_user.reset_user_password, name='web_user_reset_password'),
    path('user/delete', view_user.delete_user, name='web_user_delete'),
    path('user/create', view_user.create_user, name='web_user_create'),
    # 地址簿相关路由
    path('personal/list', view_personal.get_personal_list, name='web_personal_list'),
    path('personal/create', view_personal.create_personal, name='web_personal_create'),
    path('personal/delete', view_personal.delete_personal, name='web_personal_delete'),
    path('personal/rename', view_personal.rename_personal, name='web_personal_rename'),
    path('personal/detail', view_personal.personal_detail, name='web_personal_detail'),
    path('personal/add-device', view_personal.add_device_to_personal, name='web_personal_add_device'),
    path('personal/remove-device', view_personal.remove_device_from_personal, name='web_personal_remove_device'),
    path('personal/update-alias', view_personal.update_device_alias_in_personal, name='web_personal_update_alias'),
    path('personal/update-tags', view_personal.update_device_tags_in_personal, name='web_personal_update_tags'),
    # 角色管理
    path('role/list', view_permission.role_list, name='web_role_list'),
    path('role/create', view_permission.role_create, name='web_role_create'),
    path('role/update', view_permission.role_update, name='web_role_update'),
    path('role/delete', view_permission.role_delete, name='web_role_delete'),
    # 用户-角色
    path('role/user-roles', view_permission.user_roles, name='web_user_roles'),
    path('role/assign', view_permission.user_role_assign, name='web_role_assign'),
    path('role/remove', view_permission.user_role_remove, name='web_role_remove'),
    # 用户组管理
    path('group/list', view_group.group_list, name='web_group_list'),
    path('group/create', view_group.group_create, name='web_group_create'),
    path('group/update', view_group.group_update, name='web_group_update'),
    path('group/delete', view_group.group_delete, name='web_group_delete'),
    path('group/members', view_group.group_members, name='web_group_members'),
    path('group/add-member', view_group.group_add_member, name='web_group_add_member'),
    path('group/remove-member', view_group.group_remove_member, name='web_group_remove_member'),
    # 用户组-角色
    path('group-role/list', view_permission.group_roles, name='web_group_roles'),
    path('group-role/assign', view_permission.group_role_assign, name='web_group_role_assign'),
    path('group-role/remove', view_permission.group_role_remove, name='web_group_role_remove'),
]
