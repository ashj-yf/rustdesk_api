/**
 * 权限管理模块
 *
 * 角色管理 CRUD（携带全局权限）、用户角色分配、用户组角色分配
 * 权限位定义由后端注入到 APP.PERM_FLAGS，本模块不硬编码任何权限值
 */

(function (window) {
    'use strict';

    const APP = window.APP || {};

    function u() {
        return APP.utils || {};
    }

    function flags() {
        return APP.PERM_FLAGS || [];
    }

    /**
     * 从表单复选框状态合并为权限整数
     *
     * :param {HTMLElement} container: 包含 .perm-flag-cb 复选框的容器元素
     * :returns: 权限整数
     * :rtype: number
     */
    function permFromCheckboxes(container) {
        let v = 0;
        container.querySelectorAll('.perm-flag-cb').forEach(function (cb) {
            if (cb.checked) v |= parseInt(cb.getAttribute('data-flag'), 10);
        });
        return v;
    }

    /**
     * 生成权限复选框 HTML（用于角色创建/编辑表单）
     */
    function _renderPermCheckboxes(namePrefix) {
        return flags().map(function (f) {
            return '<label class="nav3-perm-cb-label">' +
                '<input type="checkbox" class="perm-flag-cb" name="' + namePrefix + '_' + f.key + '" ' +
                'data-flag="' + f.value + '" value="1"> ' + esc(f.label) + '</label>';
        }).join('');
    }

    /**
     * 根据权限整数返回已有权限标签字符串
     */
    function _permLabels(permission) {
        var labels = [];
        flags().forEach(function (f) {
            if (permission & f.value) labels.push(f.label);
        });
        return labels.length ? labels.join(', ') : '-';
    }

    /**
     * 在指定容器中将复选框状态设为匹配权限整数
     */
    function _setPermCheckboxes(container, permission) {
        container.querySelectorAll('.perm-flag-cb').forEach(function (cb) {
            var flag = parseInt(cb.getAttribute('data-flag'), 10);
            cb.checked = !!(permission & flag);
        });
    }

    function esc(s) {
        return u().escapeHTML(s);
    }

    // =================== 角色管理 ===================

    function openRoleManager() {
        APP.modal.open('nav3-roles-root');
        _loadRoles();
    }

    function _loadRoles() {
        var tbody = document.getElementById('nav3-roles-tbody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#8a939e;">加载中...</td></tr>';

        u().fetchJSON(APP.URLS.ROLE_LIST)
            .then(function (data) {
                var rows = (data.data || []).map(function (r) {
                    var canDel = !r.is_default;
                    return '<tr data-role-id="' + r.id + '">' +
                        '<td>' + esc(r.name) + '</td>' +
                        '<td>' + esc(r.note || '-') + '</td>' +
                        '<td>' + esc(_permLabels(r.permission)) + '</td>' +
                        '<td>' + r.user_count + '</td>' +
                        '<td>' + (r.is_default ? '是' : '否') + '</td>' +
                        '<td><div class="nav2-row-actions">' +
                        '<button type="button" class="nav2-link nav3-role-edit-btn" data-id="' + r.id +
                        '" data-name="' + esc(r.name) + '" data-note="' + esc(r.note || '') +
                        '" data-permission="' + r.permission + '">编辑</button>' +
                        (canDel ? '<button type="button" class="nav2-link nav2-link--danger nav3-role-delete-btn" data-id="' + r.id + '">删除</button>' : '') +
                        '</div></td></tr>';
                });
                tbody.innerHTML = rows.length ? rows.join('') : '<tr><td colspan="6" style="text-align:center;color:#8a939e;">暂无角色</td></tr>';
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    // =================== 角色编辑弹窗 ===================

    /**
     * 打开角色编辑弹窗
     *
     * :param {string|null} roleId: 角色 ID，为空时表示新建
     * :param {string} name: 角色名称
     * :param {string} note: 备注
     * :param {number|string} permission: 权限整数
     */
    function openRoleEditor(roleId, name, note, permission) {
        var titleEl = document.getElementById('nav3-role-edit-title');
        var idEl = document.getElementById('nav3-role-edit-id');
        var nameEl = document.getElementById('nav3-role-edit-name');
        var noteEl = document.getElementById('nav3-role-edit-note');
        var cbContainer = document.getElementById('nav3-role-edit-perm-cbs');

        if (titleEl) titleEl.textContent = roleId ? '编辑角色' : '添加角色';
        if (idEl) idEl.value = roleId || '';
        if (nameEl) nameEl.value = name || '';
        if (noteEl) noteEl.value = note || '';

        if (cbContainer && !cbContainer.hasChildNodes()) {
            cbContainer.innerHTML = _renderPermCheckboxes('role');
        }
        if (cbContainer) _setPermCheckboxes(cbContainer, parseInt(permission, 10) || 0);

        APP.modal.open('nav3-role-edit-root');
        if (nameEl) nameEl.focus();
    }

    function submitRoleEditor() {
        var form = document.getElementById('nav3-role-edit-form');
        if (!form) return Promise.resolve();

        var roleId = (form.querySelector('#nav3-role-edit-id').value || '').trim();
        var name = (form.querySelector('#nav3-role-edit-name').value || '').trim();
        var note = (form.querySelector('#nav3-role-edit-note').value || '').trim();
        var cbContainer = document.getElementById('nav3-role-edit-perm-cbs');
        var permInt = cbContainer ? permFromCheckboxes(cbContainer) : 0;

        if (!name) {
            u().showToast('请输入角色名称');
            return Promise.resolve();
        }

        var promise;
        if (roleId) {
            promise = u().postForm(APP.URLS.ROLE_UPDATE, {role_id: roleId, name: name, note: note, permission: permInt})
                .then(function () {
                    u().showToast('更新成功', 'success');
                });
        } else {
            promise = u().postForm(APP.URLS.ROLE_CREATE, {name: name, note: note, permission: permInt})
                .then(function () {
                    u().showToast('创建成功', 'success');
                });
        }

        return promise
            .then(function () {
                APP.modal.close('nav3-role-edit-root');
                _loadRoles();
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    function deleteRole(roleId) {
        if (!confirm('确定要删除该角色吗？')) return Promise.resolve();
        return u().postForm(APP.URLS.ROLE_DELETE, {role_id: roleId})
            .then(function () {
                u().showToast('删除成功', 'success');
                _loadRoles();
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    // =================== 用户角色分配 ===================

    /**
     * 渲染角色列表条目 HTML（含权限标签）
     */
    function _renderRoleItem(r, cbClass) {
        return '<label class="nav3-assign-role-item">' +
            '<input type="checkbox" class="' + cbClass + '" data-role-id="' + r.id + '"' +
            (r.assigned ? ' checked' : '') + '>' +
            '<span class="nav3-assign-role-info">' +
            '<span class="nav3-assign-role-name">' + esc(r.name) + '</span>' +
            '<span class="nav3-role-perm-label">' + esc(_permLabels(r.permission)) + '</span>' +
            '</span></label>';
    }

    function openAssignRole(username) {
        document.getElementById('nav3-assign-role-user').textContent = username;
        document.getElementById('nav3-assign-role-username').value = username;
        APP.modal.open('nav3-assign-role-root');

        var listEl = document.getElementById('nav3-assign-role-list');
        listEl.innerHTML = '<p style="color:#8a939e;">加载中...</p>';

        u().fetchJSON(APP.URLS.USER_ROLES + '?username=' + encodeURIComponent(username))
            .then(function (data) {
                var roles = data.data.roles || [];
                if (!roles.length) {
                    listEl.innerHTML = '<p style="color:#8a939e;">暂无角色</p>';
                    return;
                }
                listEl.innerHTML = roles.map(function (r) {
                    return _renderRoleItem(r, 'nav3-assign-role-cb');
                }).join('');
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    function toggleUserRole(username, roleId, assign) {
        var url = assign ? APP.URLS.ROLE_ASSIGN : APP.URLS.ROLE_REMOVE;
        u().postForm(url, {username: username, role_id: roleId})
            .then(function () {
                u().showToast(assign ? '已分配' : '已移除', 'success');
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    // =================== 用户组角色分配 ===================

    function openAssignGroupRole(groupId, groupName) {
        document.getElementById('nav3-assign-group-role-name').textContent = groupName;
        document.getElementById('nav3-assign-group-role-id').value = groupId;
        APP.modal.open('nav3-assign-group-role-root');

        var listEl = document.getElementById('nav3-assign-group-role-list');
        listEl.innerHTML = '<p style="color:#8a939e;">加载中...</p>';

        u().fetchJSON(APP.URLS.GROUP_ROLES + '?group_id=' + encodeURIComponent(groupId))
            .then(function (data) {
                var roles = data.data.roles || [];
                if (!roles.length) {
                    listEl.innerHTML = '<p style="color:#8a939e;">暂无角色</p>';
                    return;
                }
                listEl.innerHTML = roles.map(function (r) {
                    return _renderRoleItem(r, 'nav3-assign-group-role-cb');
                }).join('');
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    function toggleGroupRole(groupId, roleId, assign) {
        var url = assign ? APP.URLS.GROUP_ROLE_ASSIGN : APP.URLS.GROUP_ROLE_REMOVE;
        u().postForm(url, {group_id: groupId, role_id: roleId})
            .then(function () {
                u().showToast(assign ? '已分配' : '已移除', 'success');
            })
            .catch(function (err) {
                u().showToast(err.message);
            });
    }

    APP.perm = {
        openRoleManager: openRoleManager,
        openRoleEditor: openRoleEditor,
        submitRoleEditor: submitRoleEditor,
        deleteRole: deleteRole,
        openAssignRole: openAssignRole,
        toggleUserRole: toggleUserRole,
        openAssignGroupRole: openAssignGroupRole,
        toggleGroupRole: toggleGroupRole
    };

    window.APP = APP;

})(window);
