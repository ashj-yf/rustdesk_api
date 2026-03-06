from django.urls import path

from apps.web import view_auth, view_home, view_user, view_personal

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
]
