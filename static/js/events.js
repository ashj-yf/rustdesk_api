/**
 * 事件处理中心
 *
 * 集中管理所有页面事件委托和事件监听
 */

(function (window) {
    'use strict';

    const APP = window.APP || {};

    function getUtils() {
        return APP.utils || {};
    }

    function getModal() {
        return APP.modal || {};
    }

    function getNavigation() {
        return APP.navigation || {};
    }

    function getNav2() {
        return APP.nav2 || {};
    }

    function getNav3() {
        return APP.nav3 || {};
    }

    function getNav4() {
        return APP.nav4 || {};
    }

    function getPerm() {
        return APP.perm || {};
    }

    function getGroup() {
        return APP.group || {};
    }

    function getConstants() {
        return {
            STORAGE_KEY: APP.STORAGE_KEY || 'homeActiveNavKey',
            URLS: APP.URLS || {}
        };
    }

    /**
     * 重新加载指定导航页内容并记住导航状态
     *
     * :param {string} navKey: 导航标识
     * :param {Object} extra: 额外查询参数
     */
    function reloadNav(navKey, extra) {
        const {renderContent} = getNavigation();
        const {STORAGE_KEY} = getConstants();
        renderContent(navKey, extra);
        try {
            localStorage.setItem(STORAGE_KEY, navKey);
        } catch (_) { /* localStorage 不可用时静默处理 */
        }
    }

    function init() {
        const contentEl = document.getElementById('content');
        if (!contentEl) return;

        // ========== 通用事件 ==========

        contentEl.addEventListener('click', function (e) {
            const {close: closeModal} = getModal();
            const closeBtn = e.target.closest('[data-close]');
            if (!closeBtn) return;
            const token = closeBtn.getAttribute('data-close') || '';
            if (!token) return;
            e.preventDefault();
            const rootId = token.endsWith('-root') ? token : `${token}-root`;
            closeModal(rootId);
        }, false);

        contentEl.addEventListener('click', function (e) {
            const backdrop = e.target.closest('.modal-backdrop');
            if (!backdrop) return;
            if (e.target === backdrop) {
                backdrop.style.display = 'none';
                backdrop.setAttribute('aria-hidden', 'true');
            }
        }, false);

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                const {closeAll: closeAllModals} = getModal();
                closeAllModals();
            }
        }, false);

        // ========== nav-1 事件 ==========

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav1-page-btn');
            if (!btn) return;
            e.preventDefault();
            const page = btn.dataset.page;
            const key = btn.dataset.key || 'nav-1';
            if (page) reloadNav(key, {page});
        }, false);

        // ========== nav-2 事件 ==========

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav2-page-btn');
            if (!btn) return;
            e.preventDefault();
            const page = btn.dataset.page;
            const key = btn.dataset.key || 'nav-2';
            if (page) {
                const {collectQueryOptions} = getNav2();
                const extra = collectQueryOptions(document.getElementById('nav2-search-form'));
                extra.page = page;
                reloadNav(key, extra);
            }
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav2-reset-btn');
            if (!btn) return;
            e.preventDefault();
            reloadNav('nav-2');
        }, false);

        contentEl.addEventListener('change', function (e) {
            const {updateMultiBar} = getNav2();
            const target = e.target;
            if (target && target.id === 'nav2-select-all') {
                const check = !!target.checked;
                document.querySelectorAll('.nav2-row-checkbox').forEach(function (cb) {
                    cb.checked = check;
                });
                updateMultiBar();
            }
            if (target && target.classList.contains('nav2-row-checkbox')) {
                updateMultiBar();
            }
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav2-row-action[data-action="more"]');
            if (!btn) return;
            e.preventDefault();
            e.stopPropagation();
            const peerId = btn.dataset.id || '';
            if (!peerId) return;
            const rect = btn.getBoundingClientRect();
            const {showContextMenu} = getNav2();
            showContextMenu(peerId, rect.left, rect.bottom + 4);
        }, false);

        contentEl.addEventListener('contextmenu', function (e) {
            const row = e.target.closest('.nav2-table tbody tr[data-peer-id]');
            if (!row) return;
            e.preventDefault();
            const peerId = row.getAttribute('data-peer-id') || '';
            if (!peerId) return;
            const {showContextMenu} = getNav2();
            showContextMenu(peerId, e.clientX, e.clientY);
        }, false);

        document.addEventListener('click', function (e) {
            const item = e.target.closest('.nav2-context-item');
            if (item) {
                e.preventDefault();
                const action = item.getAttribute('data-ctx') || '';
                const {handleContextAction} = getNav2();
                handleContextAction(action);
                return;
            }
            const {hideContextMenu} = getNav2();
            hideContextMenu();
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('[data-batch]');
            if (!btn) return;
            e.preventDefault();
            const action = btn.getAttribute('data-batch') || '';
            const {getSelectedPeerIds, showDeleteConfirm, toggleDevices, clearSelection} = getNav2();
            const ids = getSelectedPeerIds();
            if (!ids.length) {
                getUtils().showToast('请先选择设备', 'error');
                return;
            }
            if (action === 'delete') {
                showDeleteConfirm(ids);
            } else if (action === 'enable') {
                toggleDevices(ids, true);
            } else if (action === 'disable') {
                toggleDevices(ids, false);
            } else if (action === 'add_to_book') {
                if (ids.length === 1) {
                    const {showAddDeviceModal} = getNav4();
                    if (showAddDeviceModal) showAddDeviceModal(ids[0]);
                } else {
                    getUtils().showToast('批量添加地址簿暂只支持逐个添加', 'info');
                }
            }
        }, false);

        contentEl.addEventListener('click', function (e) {
            if (!e.target.closest('#nav2-multi-close')) return;
            e.preventDefault();
            const {clearSelection} = getNav2();
            clearSelection();
        }, false);

        contentEl.addEventListener('click', function (e) {
            const item = e.target.closest('.nav2-tag-item');
            if (!item) return;
            e.preventDefault();
            const tag = item.getAttribute('data-tag-value') || '';
            const {setTagFilter} = getNav2();
            setTagFilter(tag);
        }, false);

        contentEl.addEventListener('click', function (e) {
            if (!e.target.closest('#nav2-delete-confirm-btn')) return;
            e.preventDefault();
            const {confirmDelete} = getNav2();
            confirmDelete();
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {startInlineEdit} = getNav2();
            const editBtn = e.target.closest('.nav2-edit-btn');
            if (!editBtn) return;
            e.preventDefault();
            const field = editBtn.getAttribute('data-field');
            const peer = editBtn.getAttribute('data-peer');
            let container = editBtn.closest('[data-inline-field="' + field + '"]') || document.getElementById('nav2-detail-' + field);
            if (!container) return;
            if (!container.hasAttribute('data-original')) {
                const text = (container.querySelector('.nav2-detail-text')?.textContent || '').trim();
                container.setAttribute('data-original', text);
            }
            if (!container.getAttribute('data-peer') && peer) {
                container.setAttribute('data-peer', peer);
            }
            startInlineEdit(container, field, peer);
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {submitInlineEdit} = getNav2();
            const okBtn = e.target.closest('.nav2-edit-confirm');
            if (!okBtn) return;
            e.preventDefault();
            const field = okBtn.getAttribute('data-field');
            const peer = okBtn.getAttribute('data-peer');
            const container = okBtn.closest('[data-inline-field]') || document.getElementById('nav2-detail-' + field);
            if (!container) return;
            submitInlineEdit(container, field, peer);
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {cancelInlineEdit} = getNav2();
            const cancelBtn = e.target.closest('.nav2-edit-cancel');
            if (!cancelBtn) return;
            e.preventDefault();
            const field = cancelBtn.getAttribute('data-field');
            const container = cancelBtn.closest('[data-inline-field]') || document.getElementById('nav2-detail-' + field);
            if (!container) return;
            cancelInlineEdit(container, field);
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {startInlineEdit} = getNav2();
            const textEl = e.target.closest('[data-inline-field="alias"] .nav2-detail-text');
            if (!textEl) return;
            const container = textEl.closest('[data-inline-field="alias"]');
            if (!container) return;
            if (container.querySelector('input[type="text"][data-field="alias"]')) return;
            const peer = container.getAttribute('data-peer') || '';
            if (!container.hasAttribute('data-original')) {
                container.setAttribute('data-original', (textEl.textContent || '').trim());
            }
            startInlineEdit(container, 'alias', peer);
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const {showToast, postForm} = getUtils();
            const {close: closeModal} = getModal();
            const {collectQueryOptions} = getNav2();
            const {URLS} = getConstants();
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav2-rename-form') return;
            e.preventDefault();
            const fd = new FormData(formEl);
            const peerId = (fd.get('peer_id') || '').trim();
            const alias = (fd.get('alias') || '').trim();
            if (!peerId || !alias) {
                showToast('请输入有效的别名', 'error');
                return;
            }
            postForm(URLS.RENAME_ALIAS, {peer_id: peerId, alias: alias}).then(() => {
                closeModal('nav2-rename-root');
                const extra = collectQueryOptions(document.getElementById('nav2-search-form'));
                reloadNav('nav-2', extra);
            }).catch(err => {
                showToast(err.message || '重命名失败，请稍后重试', 'error');
            });
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav2-note-form') return;
            e.preventDefault();
            const {submitNote} = getNav2();
            submitNote();
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav2-search-form') return;
            e.preventDefault();
            const {collectQueryOptions} = getNav2();
            reloadNav('nav-2', collectQueryOptions(formEl));
        }, false);

        // ========== nav-3 事件 ==========

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-page-btn');
            if (!btn) return;
            e.preventDefault();
            const page = btn.dataset.page;
            const key = btn.dataset.key || 'nav-3';
            if (page) {
                const {collectQueryOptions} = getNav3();
                const extra = collectQueryOptions(document.getElementById('nav3-search-form'));
                extra.page = page;
                reloadNav(key, extra);
            }
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-reset-btn');
            if (!btn) return;
            e.preventDefault();
            reloadNav('nav-3');
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav3-search-form') return;
            e.preventDefault();
            const {collectQueryOptions} = getNav3();
            reloadNav('nav-3', collectQueryOptions(formEl));
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {showToast, postForm} = getUtils();
            const {open: openModal} = getModal();
            const {URLS} = getConstants();
            const btn = e.target.closest('.nav3-row-action');
            if (!btn) return;
            e.preventDefault();
            const action = btn.getAttribute('data-action') || '';
            const username = btn.getAttribute('data-username') || '';
            if (!action || !username) return;
            if (action === 'edit') {
                const uEl = document.getElementById('nav3-edit-username');
                const fEl = document.getElementById('nav3-edit-fullname');
                const eEl = document.getElementById('nav3-edit-email');
                const sEl = document.getElementById('nav3-edit-is-staff');
                if (uEl) uEl.value = username;
                if (fEl) fEl.value = btn.getAttribute('data-fullname') || '';
                if (eEl) eEl.value = btn.getAttribute('data-email') || '';
                if (sEl) {
                    sEl.checked = btn.getAttribute('data-is_staff') === '1';
                    sEl.disabled = (username === document.body.dataset.currentUser);
                }
                openModal('nav3-edit-root');
            } else if (action === 'reset_pwd') {
                const uEl = document.getElementById('nav3-reset-username');
                const p1 = document.getElementById('nav3-reset-pass1');
                const p2 = document.getElementById('nav3-reset-pass2');
                if (uEl) uEl.value = username;
                if (p1) p1.value = '';
                if (p2) p2.value = '';
                openModal('nav3-reset-root');
            } else if (action === 'roles') {
                const {openAssignRole} = getPerm();
                if (openAssignRole) openAssignRole(username);
            } else if (action === 'delete') {
                if (!confirm(`确定要删除用户"${username}"吗？删除后该用户将无法登录。`)) return;
                postForm(URLS.USER_DELETE, {username: username}).then(() => {
                    showToast('删除成功', 'success');
                    const {collectQueryOptions} = getNav3();
                    reloadNav('nav-3', collectQueryOptions(document.getElementById('nav3-search-form')));
                }).catch(err => {
                    showToast(err.message || '删除失败，请稍后重试', 'error');
                });
            }
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const {showToast, postForm} = getUtils();
            const {close: closeModal} = getModal();
            const {URLS} = getConstants();
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav3-edit-form') return;
            e.preventDefault();
            const fd = new FormData(formEl);
            const username = (fd.get('username') || '').trim();
            if (!username) {
                showToast('用户名无效', 'error');
                return;
            }
            postForm(URLS.USER_UPDATE, {
                username: username,
                full_name: (fd.get('full_name') || '').trim(),
                email: (fd.get('email') || '').trim(),
                is_staff: formEl.querySelector('#nav3-edit-is-staff')?.checked ? '1' : '0'
            }).then(() => {
                closeModal('nav3-edit-root');
                const {collectQueryOptions} = getNav3();
                reloadNav('nav-3', collectQueryOptions(document.getElementById('nav3-search-form')));
            }).catch(err => {
                showToast(err.message || '保存失败，请稍后重试', 'error');
            });
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const {showToast, postForm} = getUtils();
            const {close: closeModal} = getModal();
            const {URLS} = getConstants();
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav3-reset-form') return;
            e.preventDefault();
            const fd = new FormData(formEl);
            const username = (fd.get('username') || '').trim();
            const p1 = (fd.get('password1') || '').trim();
            const p2 = (fd.get('password2') || '').trim();
            if (!username || !p1 || !p2) {
                showToast('请输入完整信息', 'error');
                return;
            }
            if (p1 !== p2) {
                showToast('两次密码不一致', 'error');
                return;
            }
            postForm(URLS.USER_RESET_PWD, {username, password1: p1, password2: p2}).then(() => {
                closeModal('nav3-reset-root');
                const {collectQueryOptions} = getNav3();
                reloadNav('nav-3', collectQueryOptions(document.getElementById('nav3-search-form')));
            }).catch(err => {
                showToast(err.message || '重置失败，请稍后重试', 'error');
            });
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {open: openModal} = getModal();
            const btn = e.target.closest('.nav3-create-btn');
            if (!btn) return;
            e.preventDefault();
            const form = document.getElementById('nav3-create-form');
            if (form) form.reset();
            openModal('nav3-create-root');
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const {showToast, postForm} = getUtils();
            const {close: closeModal} = getModal();
            const {URLS} = getConstants();
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav3-create-form') return;
            e.preventDefault();
            const fd = new FormData(formEl);
            const username = (fd.get('username') || '').trim();
            const p1 = (fd.get('password1') || '').trim();
            const p2 = (fd.get('password2') || '').trim();
            if (!username || !p1 || !p2) {
                showToast('用户名和密码不能为空', 'error');
                return;
            }
            if (p1 !== p2) {
                showToast('两次密码不一致', 'error');
                return;
            }
            if (p1.length < 6) {
                showToast('密码长度至少为6位', 'error');
                return;
            }
            const params = {
                username,
                password1: p1,
                password2: p2,
                is_staff: formEl.querySelector('#nav3-create-is-staff')?.checked ? '1' : '0'
            };
            const fullName = (fd.get('full_name') || '').trim();
            const email = (fd.get('email') || '').trim();
            if (fullName) params.full_name = fullName;
            if (email) params.email = email;
            postForm(URLS.USER_CREATE, params).then(() => {
                showToast('用户创建成功', 'success');
                closeModal('nav3-create-root');
                const {collectQueryOptions} = getNav3();
                reloadNav('nav-3', collectQueryOptions(document.getElementById('nav3-search-form')));
            }).catch(err => {
                showToast(err.message || '创建失败，请稍后重试', 'error');
            });
        }, false);

        // ========== nav-3 角色管理事件 ==========

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-role-manage-btn');
            if (!btn) return;
            e.preventDefault();
            const {openRoleManager} = getPerm();
            if (openRoleManager) openRoleManager();
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-role-add-btn');
            if (!btn) return;
            e.preventDefault();
            const {openRoleEditor} = getPerm();
            if (openRoleEditor) openRoleEditor(null, '', '', 0);
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-role-edit-btn');
            if (!btn) return;
            e.preventDefault();
            const {openRoleEditor} = getPerm();
            if (openRoleEditor) openRoleEditor(btn.dataset.id, btn.dataset.name, btn.dataset.note, btn.dataset.permission);
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav3-role-edit-form') return;
            e.preventDefault();
            const {submitRoleEditor} = getPerm();
            if (submitRoleEditor) submitRoleEditor();
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-role-delete-btn');
            if (!btn) return;
            e.preventDefault();
            const {deleteRole} = getPerm();
            if (deleteRole) deleteRole(btn.dataset.id);
        }, false);

        contentEl.addEventListener('change', function (e) {
            const cb = e.target.closest('.nav3-assign-role-cb');
            if (!cb) return;
            const username = (document.getElementById('nav3-assign-role-username')?.value || '').trim();
            if (!username) return;
            const roleId = cb.getAttribute('data-role-id');
            const {toggleUserRole} = getPerm();
            if (toggleUserRole) toggleUserRole(username, roleId, cb.checked);
        }, false);

        // ========== nav-3 用户组角色分配事件 ==========

        contentEl.addEventListener('change', function (e) {
            const cb = e.target.closest('.nav3-assign-group-role-cb');
            if (!cb) return;
            const groupId = (document.getElementById('nav3-assign-group-role-id')?.value || '').trim();
            if (!groupId) return;
            const roleId = cb.getAttribute('data-role-id');
            const {toggleGroupRole} = getPerm();
            if (toggleGroupRole) toggleGroupRole(groupId, roleId, cb.checked);
        }, false);

        // ========== nav-3 标签切换事件 ==========

        contentEl.addEventListener('click', function (e) {
            const tab = e.target.closest('.nav3-tab');
            if (!tab) return;
            e.preventDefault();
            const tabKey = tab.getAttribute('data-tab');
            if (!tabKey) return;
            const params = tabKey === 'groups' ? {tab: 'groups'} : {};
            reloadNav('nav-3', params);
        }, false);

        // ========== nav-3 用户组管理事件 ==========

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-group-create-btn');
            if (!btn) return;
            e.preventDefault();
            const {openGroupEditor} = getGroup();
            if (openGroupEditor) openGroupEditor(null, '');
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav3-group-edit-form') return;
            e.preventDefault();
            const {submitGroupEditor} = getGroup();
            if (submitGroupEditor) submitGroupEditor();
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav3-group-search-form') return;
            e.preventDefault();
            const {collectQueryOptions} = getGroup();
            reloadNav('nav-3', collectQueryOptions(formEl));
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-group-reset-btn');
            if (!btn) return;
            e.preventDefault();
            reloadNav('nav-3', {tab: 'groups'});
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-group-page-btn');
            if (!btn) return;
            e.preventDefault();
            const page = btn.dataset.page;
            if (page) {
                const {collectQueryOptions} = getGroup();
                const extra = collectQueryOptions(document.getElementById('nav3-group-search-form'));
                extra.page = page;
                reloadNav('nav-3', extra);
            }
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-group-row-action');
            if (!btn) return;
            e.preventDefault();
            const action = btn.getAttribute('data-action') || '';
            const groupId = btn.getAttribute('data-group-id') || '';
            const groupName = btn.getAttribute('data-group-name') || '';
            if (!action || !groupId) return;

            if (action === 'edit') {
                const {openGroupEditor} = getGroup();
                if (openGroupEditor) openGroupEditor(groupId, groupName);
            } else if (action === 'members') {
                const {openGroupMembers} = getGroup();
                if (openGroupMembers) openGroupMembers(groupId, groupName);
            } else if (action === 'roles') {
                const {openAssignGroupRole} = getPerm();
                if (openAssignGroupRole) openAssignGroupRole(groupId, groupName);
            } else if (action === 'delete') {
                const {deleteGroup} = getGroup();
                if (deleteGroup) deleteGroup(groupId, groupName);
            }
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-group-add-member-btn');
            if (!btn) return;
            e.preventDefault();
            const groupId = (document.getElementById('nav3-group-members-id')?.value || '').trim();
            const usernameInput = document.getElementById('nav3-group-members-username');
            const username = (usernameInput?.value || '').trim();
            if (!groupId) return;
            const {addMember} = getGroup();
            if (addMember) addMember(groupId, username);
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav3-group-remove-member-btn');
            if (!btn) return;
            e.preventDefault();
            const groupId = (document.getElementById('nav3-group-members-id')?.value || '').trim();
            const userId = btn.getAttribute('data-user-id') || '';
            const username = btn.getAttribute('data-username') || '';
            if (!groupId || !userId) return;
            const {removeMember} = getGroup();
            if (removeMember) removeMember(groupId, userId, username);
        }, false);

        // ========== nav-4 事件 ==========

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav4-page-btn');
            if (!btn) return;
            e.preventDefault();
            const page = btn.dataset.page;
            const key = btn.dataset.key || 'nav-4';
            if (page) {
                const {collectQueryOptions} = getNav4();
                const extra = collectQueryOptions(document.getElementById('nav4-search-form'));
                extra.page = page;
                reloadNav(key, extra);
            }
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav4-reset-btn');
            if (!btn) return;
            e.preventDefault();
            reloadNav('nav-4');
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav4-search-form') return;
            e.preventDefault();
            const {collectQueryOptions} = getNav4();
            reloadNav('nav-4', collectQueryOptions(formEl));
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {open: openModal} = getModal();
            const btn = e.target.closest('.nav4-create-btn');
            if (!btn) return;
            e.preventDefault();
            const nameEl = document.getElementById('nav4-create-name');
            const typeEl = document.getElementById('nav4-create-type');
            if (nameEl) nameEl.value = '';
            if (typeEl) typeEl.value = 'private';
            openModal('nav4-create-root');
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const {showToast, postForm} = getUtils();
            const {close: closeModal} = getModal();
            const {URLS} = getConstants();
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav4-create-form') return;
            e.preventDefault();
            const fd = new FormData(formEl);
            const personalName = (fd.get('personal_name') || '').trim();
            const personalType = (fd.get('personal_type') || '').trim();
            if (!personalName) {
                showToast('请输入地址簿名称', 'error');
                return;
            }
            postForm(URLS.PERSONAL_CREATE, {personal_name: personalName, personal_type: personalType}).then(() => {
                closeModal('nav4-create-root');
                const {collectQueryOptions} = getNav4();
                reloadNav('nav-4', collectQueryOptions(document.getElementById('nav4-search-form')));
                showToast('创建成功', 'success');
            }).catch(err => {
                showToast(err.message || '创建失败，请稍后重试', 'error');
            });
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {showToast, postForm} = getUtils();
            const {open: openModal} = getModal();
            const {URLS} = getConstants();
            const btn = e.target.closest('.nav4-row-action');
            if (!btn) return;
            e.preventDefault();
            const action = btn.getAttribute('data-action') || '';
            const guid = btn.getAttribute('data-guid') || '';
            const name = btn.getAttribute('data-name') || '';
            if (!action || !guid) return;

            if (action === 'view') {
                const {fetchAndShowDetail: fetchAndShowDetail4} = getNav4();
                fetchAndShowDetail4(guid);
            } else if (action === 'rename') {
                const guidEl = document.getElementById('nav4-rename-guid');
                const nameEl = document.getElementById('nav4-rename-name');
                if (guidEl) guidEl.value = guid;
                if (nameEl) {
                    nameEl.value = name;
                    nameEl.focus();
                    nameEl.select();
                }
                openModal('nav4-rename-root');
            } else if (action === 'delete') {
                if (!confirm(`确定要删除地址簿"${name}"吗？删除后将无法恢复。`)) return;
                postForm(URLS.PERSONAL_DELETE, {guid}).then(() => {
                    const {collectQueryOptions} = getNav4();
                    reloadNav('nav-4', collectQueryOptions(document.getElementById('nav4-search-form')));
                    showToast('删除成功', 'success');
                }).catch(err => {
                    showToast(err.message || '删除失败，请稍后重试', 'error');
                });
            }
        }, false);

        contentEl.addEventListener('submit', function (e) {
            const {showToast, postForm} = getUtils();
            const {close: closeModal} = getModal();
            const {URLS} = getConstants();
            const formEl = e.target;
            if (!formEl || formEl.id !== 'nav4-rename-form') return;
            e.preventDefault();
            const fd = new FormData(formEl);
            const guid = (fd.get('guid') || '').trim();
            const newName = (fd.get('new_name') || '').trim();
            if (!guid || !newName) {
                showToast('请输入新名称', 'error');
                return;
            }
            postForm(URLS.PERSONAL_RENAME, {guid, new_name: newName}).then(() => {
                closeModal('nav4-rename-root');
                const {collectQueryOptions} = getNav4();
                reloadNav('nav-4', collectQueryOptions(document.getElementById('nav4-search-form')));
                showToast('重命名成功', 'success');
            }).catch(err => {
                showToast(err.message || '重命名失败，请稍后重试', 'error');
            });
        }, false);

        contentEl.addEventListener('click', function (e) {
            const {showToast, postForm} = getUtils();
            const {URLS} = getConstants();
            const btn = e.target.closest('.nav4-remove-device-btn');
            if (!btn) return;
            e.preventDefault();
            const guid = btn.getAttribute('data-guid') || '';
            const peerId = btn.getAttribute('data-peer-id') || '';
            if (!guid || !peerId) return;
            if (!confirm('确定要从地址簿中移除该设备吗？')) return;
            postForm(URLS.PERSONAL_REMOVE_DEVICE, {guid, peer_id: peerId}).then(() => {
                const {fetchAndShowDetail: fetchAndShowDetail4} = getNav4();
                fetchAndShowDetail4(guid);
                showToast('移除成功', 'success');
            }).catch(err => {
                showToast(err.message || '移除失败，请稍后重试', 'error');
            });
        }, false);

        contentEl.addEventListener('click', function (e) {
            const btn = e.target.closest('.nav4-edit-btn');
            if (!btn) return;
            e.preventDefault();
            const field = btn.getAttribute('data-field');
            const guid = btn.getAttribute('data-guid');
            const peerId = btn.getAttribute('data-peer-id');
            const cell = btn.closest('.nav4-editable-cell');
            if (!cell || !field || !guid || !peerId) return;
            if (cell.querySelector('input[type="text"]')) return;
            const {startInlineEdit: startInlineEdit4} = getNav4();
            startInlineEdit4(cell, field, guid, peerId);
        }, false);

        const addToBookForm = document.getElementById('nav2-add-to-book-form');
        if (addToBookForm) {
            addToBookForm.addEventListener('submit', function (e) {
                const {showToast, postForm} = getUtils();
                const {close: closeModal} = getModal();
                const {URLS} = getConstants();
                e.preventDefault();
                const peerId = document.getElementById('nav2-add-to-book-peer-id').value.trim();
                const guid = document.getElementById('nav2-add-to-book-guid').value.trim();
                const alias = document.getElementById('nav2-add-to-book-alias').value.trim();
                if (!guid) {
                    showToast('请选择地址簿', 'error');
                    return;
                }
                const params = {guid, peer_id: peerId};
                if (alias) params.alias = alias;
                postForm(URLS.PERSONAL_ADD_DEVICE, params).then(() => {
                    showToast('添加成功', 'success');
                    closeModal('nav2-add-to-book-root');
                }).catch(err => {
                    showToast(err.message || '添加失败，请稍后重试', 'error');
                });
            });
        }

        // ========== 导航内容加载完成事件 ==========

        document.addEventListener('contentLoaded', function (e) {
            const key = e.detail?.key || '';
            const {toggleAutoRefresh} = getNav2();
            toggleAutoRefresh(key === 'nav-2');
        }, false);

        window.addEventListener('beforeunload', function () {
            const {toggleAutoRefresh} = getNav2();
            toggleAutoRefresh(false);
        }, false);
    }

    function openAddToBook(peerId) {
        const {showAddDeviceModal} = getNav4();
        if (showAddDeviceModal) showAddDeviceModal(peerId);
    }

    APP.events = {
        init: init,
        openAddToBook: openAddToBook
    };

    window.APP = APP;

})(window);
