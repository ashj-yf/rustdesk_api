/**
 * 用户组管理模块 (nav-3 groups tab)
 *
 * 用户组 CRUD、成员管理交互逻辑
 */

(function (window) {
    'use strict';

    const APP = window.APP || {};

    function u() {
        return APP.utils || {};
    }

    function esc(s) {
        return u().escapeHTML(s);
    }

    /**
     * 收集用户组搜索表单参数
     *
     * :param {HTMLFormElement} formEl: 搜索表单元素
     * :returns: 查询参数对象
     * :rtype: Object
     */
    function collectQueryOptions(formEl) {
        const {collectFormParams} = u();
        const params = collectFormParams(formEl, ['q', 'page_size']);
        params.tab = 'groups';
        return params;
    }

    /**
     * 打开用户组编辑弹窗（新建或编辑）
     *
     * :param {string|null} groupId: 用户组 ID，为空时表示新建
     * :param {string} name: 用户组名称
     */
    function openGroupEditor(groupId, name) {
        const titleEl = document.getElementById('nav3-group-edit-title');
        const idEl = document.getElementById('nav3-group-edit-id');
        const nameEl = document.getElementById('nav3-group-edit-name');

        if (titleEl) titleEl.textContent = groupId ? '编辑用户组' : '新建用户组';
        if (idEl) idEl.value = groupId || '';
        if (nameEl) nameEl.value = name || '';

        APP.modal.open('nav3-group-edit-root');
        if (nameEl) nameEl.focus();
    }

    /**
     * 提交用户组编辑表单
     *
     * :returns: Promise
     * :rtype: Promise
     */
    function submitGroupEditor() {
        const form = document.getElementById('nav3-group-edit-form');
        if (!form) return Promise.resolve();

        const groupId = (form.querySelector('#nav3-group-edit-id').value || '').trim();
        const name = (form.querySelector('#nav3-group-edit-name').value || '').trim();

        if (!name) {
            u().showToast('请输入用户组名称');
            return Promise.resolve();
        }

        let promise;
        if (groupId) {
            promise = u().postForm(APP.URLS.GROUP_UPDATE, {group_id: groupId, name: name})
                .then(function () {
                    u().showToast('更新成功', 'success');
                });
        } else {
            promise = u().postForm(APP.URLS.GROUP_CREATE, {name: name})
                .then(function () {
                    u().showToast('创建成功', 'success');
                });
        }

        return promise
            .then(function () {
                APP.modal.close('nav3-group-edit-root');
                APP.navigation.renderContent('nav-3', collectQueryOptions(
                    document.getElementById('nav3-group-search-form')
                ));
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    /**
     * 删除用户组
     *
     * :param {string} groupId: 用户组 ID
     * :param {string} groupName: 用户组名称（用于确认提示）
     * :returns: Promise
     * :rtype: Promise
     */
    function deleteGroup(groupId, groupName) {
        if (!confirm('确定要删除用户组"' + groupName + '"吗？组内成员将回落到默认组。')) {
            return Promise.resolve();
        }
        return u().postForm(APP.URLS.GROUP_DELETE, {group_id: groupId})
            .then(function () {
                u().showToast('删除成功', 'success');
                APP.navigation.renderContent('nav-3', collectQueryOptions(
                    document.getElementById('nav3-group-search-form')
                ));
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    /**
     * 打开成员管理弹窗并加载成员列表
     *
     * :param {string} groupId: 用户组 ID
     * :param {string} groupName: 用户组名称
     */
    function openGroupMembers(groupId, groupName) {
        document.getElementById('nav3-group-members-name').textContent = groupName;
        document.getElementById('nav3-group-members-id').value = groupId;
        const usernameInput = document.getElementById('nav3-group-members-username');
        if (usernameInput) usernameInput.value = '';

        APP.modal.open('nav3-group-members-root');
        _loadMembers(groupId);
    }

    /**
     * 加载用户组成员列表
     *
     * :param {string} groupId: 用户组 ID
     */
    function _loadMembers(groupId) {
        const listEl = document.getElementById('nav3-group-members-list');
        if (!listEl) return;
        listEl.innerHTML = '<p style="color:#8a939e;text-align:center;">加载中...</p>';

        u().fetchJSON(APP.URLS.GROUP_MEMBERS + '?group_id=' + encodeURIComponent(groupId))
            .then(function (data) {
                const members = data.data || [];
                if (!members.length) {
                    listEl.innerHTML = '<p style="color:#8a939e;text-align:center;">暂无成员</p>';
                    return;
                }
                listEl.innerHTML = '<table class="nav2-table nav3-group-members-table">' +
                    '<thead><tr><th>用户名</th><th>姓名</th><th>操作</th></tr></thead>' +
                    '<tbody>' + members.map(function (m) {
                        return '<tr>' +
                            '<td>' + esc(m.username) + '</td>' +
                            '<td>' + esc(m.full_name) + '</td>' +
                            '<td><button type="button" class="nav2-link nav2-link--danger nav3-group-remove-member-btn" ' +
                            'data-user-id="' + m.id + '" data-username="' + esc(m.username) + '">移除</button></td>' +
                            '</tr>';
                    }).join('') + '</tbody></table>';
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    /**
     * 添加成员到用户组
     *
     * :param {string} groupId: 用户组 ID
     * :param {string} username: 用户名
     * :returns: Promise
     * :rtype: Promise
     */
    function addMember(groupId, username) {
        if (!username) {
            u().showToast('请输入用户名');
            return Promise.resolve();
        }
        return u().postForm(APP.URLS.GROUP_ADD_MEMBER, {group_id: groupId, username: username})
            .then(function () {
                u().showToast('添加成功', 'success');
                const usernameInput = document.getElementById('nav3-group-members-username');
                if (usernameInput) usernameInput.value = '';
                _loadMembers(groupId);
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    /**
     * 从用户组中移除成员
     *
     * :param {string} groupId: 用户组 ID
     * :param {string} userId: 用户 ID
     * :param {string} username: 用户名（用于确认提示）
     * :returns: Promise
     * :rtype: Promise
     */
    function removeMember(groupId, userId, username) {
        if (!confirm('确定要将用户"' + username + '"从该组移除吗？')) {
            return Promise.resolve();
        }
        return u().postForm(APP.URLS.GROUP_REMOVE_MEMBER, {group_id: groupId, user_id: userId})
            .then(function () {
                u().showToast('移除成功', 'success');
                _loadMembers(groupId);
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    APP.group = {
        collectQueryOptions: collectQueryOptions,
        openGroupEditor: openGroupEditor,
        submitGroupEditor: submitGroupEditor,
        deleteGroup: deleteGroup,
        openGroupMembers: openGroupMembers,
        addMember: addMember,
        removeMember: removeMember
    };

    window.APP = APP;

})(window);
