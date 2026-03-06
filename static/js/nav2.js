/**
 * 设备管理页面模块 (nav-2)
 *
 * 处理设备列表、详情、编辑、删除、启用/禁用、标签过滤、
 * 右键菜单、批量操作、状态刷新等功能
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

    function getConstants() {
        return {
            STORAGE_KEY: APP.STORAGE_KEY || 'homeActiveNavKey',
            URLS: APP.URLS || {},
            ICONS: APP.ICONS || {}
        };
    }

    // ──────── 状态轮询 ────────
    let TIMER_ID = null;
    let RUNNING = false;
    let INFLIGHT_CONTROLLER = null;
    let FAILURES = 0;
    const BASE_INTERVAL = 10000;
    const MAX_INTERVAL = 60000;

    function collectPeerIdsFromDOM() {
        const rows = document.querySelectorAll('.nav2-table tbody tr[data-peer-id]');
        const ids = [];
        rows.forEach(function (tr) {
            const pid = tr.getAttribute('data-peer-id') || '';
            if (pid) ids.push(pid);
        });
        return ids;
    }

    function applyStatuses(statusMap) {
        if (!statusMap) return;
        Object.keys(statusMap).forEach(function (pid) {
            const el = document.querySelector('.nav2-status[data-status-for="' + pid + '"]');
            if (!el) return;
            const isOnline = !!(statusMap[pid] && statusMap[pid].is_online);
            el.classList.toggle('online', isOnline);
            el.classList.toggle('offline', !isOnline);
            el.textContent = isOnline ? '在线' : '离线';
        });
    }

    function refreshStatusesOnce() {
        const {URLS} = getConstants();
        const ids = collectPeerIdsFromDOM();
        if (!ids.length) return Promise.resolve();
        try {
            if (INFLIGHT_CONTROLLER) INFLIGHT_CONTROLLER.abort();
        } catch (_) {
        }
        INFLIGHT_CONTROLLER = new AbortController();
        return fetch(URLS.DEVICE_STATUSES, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-Session-No-Renew': '1',
                'X-CSRFToken': APP.utils.getCookie('csrftoken')
            },
            body: JSON.stringify({ids: ids.join(',')}),
            signal: INFLIGHT_CONTROLLER.signal
        }).then(function (resp) {
            if (!resp.ok) throw new Error('请求失败');
            return resp.json();
        }).then(function (data) {
            if (!data || data.ok !== true) return;
            applyStatuses(data.data || {});
        }).catch(function () {
        }).finally(function () {
            INFLIGHT_CONTROLLER = null;
        });
    }

    function computeDelay() {
        const backoff = BASE_INTERVAL * Math.pow(2, Math.max(0, Math.min(6, FAILURES)));
        return Math.min(backoff, MAX_INTERVAL);
    }

    function tick() {
        if (!RUNNING) return;
        if (document.hidden) {
            TIMER_ID = null;
            return;
        }
        refreshStatusesOnce().then(function () {
            FAILURES = 0;
        }).catch(function () {
            FAILURES += 1;
        }).finally(function () {
            if (!RUNNING) return;
            TIMER_ID = setTimeout(tick, computeDelay());
        });
    }

    function toggleAutoRefresh(enable) {
        RUNNING = !!enable;
        if (TIMER_ID) {
            clearTimeout(TIMER_ID);
            TIMER_ID = null;
        }
        try {
            if (INFLIGHT_CONTROLLER) INFLIGHT_CONTROLLER.abort();
        } catch (_) {
        }
        INFLIGHT_CONTROLLER = null;
        FAILURES = 0;
        if (RUNNING) tick();
    }

    // ──────── 表单参数收集 ────────
    function collectQueryOptions(formEl) {
        const {collectFormParams} = getUtils();
        return collectFormParams(formEl, ['q', 'os', 'status', 'enabled', 'sort', 'tag', 'page_size']);
    }

    // ──────── 重命名 ────────
    function prefillRenameForm(peerId, currentAlias) {
        const peerInput = document.getElementById('nav2-rename-peer');
        const aliasInput = document.getElementById('nav2-rename-alias');
        if (peerInput) peerInput.value = peerId || '';
        if (aliasInput) {
            aliasInput.value = currentAlias || '';
            aliasInput.focus();
            aliasInput.select();
        }
    }

    // ──────── 设备详情 ────────
    function renderDetailHTML(detail) {
        const {ICONS} = getConstants();
        const {escapeHTML} = getUtils();
        const esc = escapeHTML;
        const tags = Array.isArray(detail.tags) ? detail.tags.join(', ') : (detail.tags || '');
        const enabledText = detail.is_enabled ? '已启用' : '已禁用';
        const enabledClass = detail.is_enabled ? 'nav2-enabled-badge--on' : 'nav2-enabled-badge--off';
        return (
            '<dl style="margin:0;">' +
            _detailRow('设备ID', esc(detail.peer_id || '-')) +
            _detailRow('用户名', esc(detail.username || '-')) +
            _detailRow('主机名', esc(detail.hostname || '-')) +
            _detailRowEditable('设备别名', 'alias', detail.peer_id, esc(detail.alias || '-'), detail.alias, ICONS) +
            _detailRowEditable('设备标签', 'tags', detail.peer_id, esc(tags || '-'), tags, ICONS) +
            _detailRow('平台', esc(detail.platform || '-')) +
            _detailRow('版本', esc(detail.version || '-')) +
            _detailRow('启用状态', '<span class="nav2-enabled-badge ' + enabledClass + '">' + enabledText + '</span>') +
            _detailRowEditable('备注', 'note', detail.peer_id, esc(detail.note || '-'), detail.note, ICONS) +
            '</dl>'
        );
    }

    function _detailRow(label, value) {
        return '<div style="display:flex;gap:8px;margin:6px 0;align-items:center;">' +
            '<dt style="min-width:88px;color:#6a737d;">' + label + '</dt>' +
            '<dd style="margin:0;flex:1;">' + value + '</dd></div>';
    }

    function _detailRowEditable(label, field, peerId, displayValue, rawValue, ICONS) {
        const {escapeHTML} = getUtils();
        const esc = escapeHTML;
        return '<div style="display:flex;gap:8px;margin:6px 0;align-items:center;">' +
            '<dt style="min-width:88px;color:#6a737d;">' + label + '</dt>' +
            '<dd id="nav2-detail-' + field + '" style="margin:0;flex:1;" data-original="' + esc(rawValue || '') + '">' +
            '<span class="nav2-detail-text">' + displayValue + '</span> ' +
            '<button type="button" class="nav2-link nav2-edit-btn" data-field="' + esc(field) + '" data-peer="' + esc(peerId || '') + '" aria-label="编辑' + label + '">' +
            '<img src="' + ICONS.EDIT + '" width="16" height="16" alt="" aria-hidden="true">' +
            '</button></dd></div>';
    }

    function fetchAndShowDetail(peerId) {
        const {URLS} = getConstants();
        const {open: openModal} = getModal();
        const bodyEl = document.getElementById('nav2-modal-body');
        if (bodyEl) bodyEl.innerHTML = '<div style="color:#6a737d;">加载中...</div>';
        openModal('nav2-modal-root');
        const params = new URLSearchParams({peer_id: peerId});
        fetch(URLS.DEVICE_DETAIL + '?' + params.toString(), {
            method: 'GET', credentials: 'same-origin',
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        }).then(function (resp) {
            if (!resp.ok) throw new Error('请求失败');
            return resp.json();
        }).then(function (data) {
            if (!data || data.ok !== true) throw new Error((data && (data.err_msg || data.error)) || '加载失败');
            if (bodyEl) bodyEl.innerHTML = renderDetailHTML(data.data || {});
        }).catch(function (err) {
            const {escapeHTML} = getUtils();
            if (bodyEl) bodyEl.innerHTML = '<div style="color:#b91c1c;">' + escapeHTML(err.message || '加载失败') + '</div>';
        });
    }

    // ──────── 内联编辑（别名/标签） ────────
    function startInlineEdit(containerEl, field, peerId) {
        const {ICONS} = getConstants();
        const {escapeHTML} = getUtils();
        const esc = escapeHTML;
        const placeholderMap = {alias: '请输入设备别名', tags: '用逗号分隔多个标签', note: '请输入备注'};
        const placeholder = placeholderMap[field] || '';
        const isInlineCell = containerEl.hasAttribute('data-inline-field');
        const original = containerEl.getAttribute('data-original')
            || (containerEl.querySelector('.nav2-detail-text') || {}).textContent || '';

        if (isInlineCell) {
            if (containerEl.querySelector('.nav2-inline-pop')) return;
            const pop = document.createElement('div');
            pop.className = 'nav2-inline-pop';
            pop.innerHTML =
                '<input type="text" class="nav2-input" value="' + esc(original) + '" ' +
                'data-field="' + esc(field) + '" data-peer="' + esc(peerId) + '" placeholder="' + esc(placeholder) + '"> ' +
                '<button type="button" class="nav2-link nav2-edit-confirm" data-field="' + esc(field) + '" data-peer="' + esc(peerId) + '" aria-label="确认">' +
                '<img src="' + ICONS.CONFIRM + '" width="16" height="16" alt="" aria-hidden="true"></button> ' +
                '<button type="button" class="nav2-link nav2-edit-cancel" data-field="' + esc(field) + '" data-peer="' + esc(peerId) + '" aria-label="取消">' +
                '<img src="' + ICONS.CANCEL + '" width="16" height="16" alt="" aria-hidden="true"></button>';
            containerEl.appendChild(pop);
            const input = pop.querySelector('input[type="text"]');
            if (input) {
                input.focus();
                input.select();
            }
            return;
        }

        containerEl.innerHTML =
            '<input type="text" class="nav2-input" style="min-width:200px;" value="' + esc(original) + '" ' +
            'data-field="' + esc(field) + '" data-peer="' + esc(peerId) + '" placeholder="' + esc(placeholder) + '"> ' +
            '<button type="button" class="nav2-link nav2-edit-confirm" data-field="' + esc(field) + '" data-peer="' + esc(peerId) + '" aria-label="确认">' +
            '<img src="' + ICONS.CONFIRM + '" width="16" height="16" alt="" aria-hidden="true"></button> ' +
            '<button type="button" class="nav2-link nav2-edit-cancel" data-field="' + esc(field) + '" data-peer="' + esc(peerId) + '" aria-label="取消">' +
            '<img src="' + ICONS.CANCEL + '" width="16" height="16" alt="" aria-hidden="true"></button>';
    }

    function submitInlineEdit(ddEl, field, peerId) {
        const {showToast, parseFetchError, getCookie} = getUtils();
        const {URLS, STORAGE_KEY} = getConstants();
        const {renderContent} = getNavigation();
        const input = ddEl.querySelector('input[type="text"][data-field="' + field + '"]');
        const value = input ? input.value.trim() : '';
        const csrf = getCookie('csrftoken');

        if (field === 'note') {
            const body = new URLSearchParams();
            body.set('peer_id', peerId);
            body.set('note', value);
            fetch(URLS.DEVICE_NOTE, {
                method: 'POST', credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                    'X-CSRFToken': csrf
                },
                body: body.toString()
            }).then(function (resp) {
                if (!resp.ok) return parseFetchError(resp);
                return resp.json();
            }).then(function (data) {
                if (!data || data.ok !== true) throw new Error((data && data.err_msg) || '保存失败');
                const inModal = !!ddEl.closest('#nav2-modal-root');
                if (inModal) fetchAndShowDetail(peerId);
                _reloadNav2();
            }).catch(function (err) {
                showToast(err.message || '保存失败', 'error');
            });
            return;
        }

        const body = new URLSearchParams();
        body.set('peer_id', peerId);
        if (field === 'alias') body.set('alias', value);
        else if (field === 'tags') body.set('tags', value);

        fetch(URLS.DEVICE_UPDATE, {
            method: 'POST', credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'X-CSRFToken': csrf
            },
            body: body.toString()
        }).then(function (resp) {
            if (!resp.ok) return parseFetchError(resp);
            return resp.json();
        }).then(function (data) {
            if (!data || data.ok !== true) throw new Error((data && data.err_msg) || '保存失败');
            const inModal = !!ddEl.closest('#nav2-modal-root');
            if (inModal) fetchAndShowDetail(peerId);
            _reloadNav2();
        }).catch(function (err) {
            showToast(err.message || '保存失败', 'error');
        });
    }

    function cancelInlineEdit(containerEl, field) {
        const {ICONS} = getConstants();
        const {escapeHTML} = getUtils();
        const esc = escapeHTML;
        const pop = containerEl.querySelector('.nav2-inline-pop');
        if (pop) {
            pop.remove();
            return;
        }
        const original = containerEl.getAttribute('data-original') || '';
        const peerAttr = containerEl.getAttribute('data-peer') || '';
        containerEl.innerHTML =
            '<span class="nav2-detail-text">' + esc(original || '-') + '</span> ' +
            '<button type="button" class="nav2-link nav2-edit-btn" data-field="' + esc(field) + '" data-peer="' + esc(peerAttr) + '" aria-label="编辑">' +
            '<img src="' + ICONS.EDIT + '" width="16" height="16" alt="" aria-hidden="true"></button>';
    }

    // ──────── 删除设备 ────────
    function showDeleteConfirm(peerIds) {
        if (!peerIds || !peerIds.length) return;
        const {open: openModal} = getModal();
        const idsInput = document.getElementById('nav2-delete-peer-ids');
        const msgEl = document.getElementById('nav2-delete-msg');
        if (idsInput) idsInput.value = peerIds.join(',');
        if (msgEl) {
            msgEl.textContent = peerIds.length === 1
                ? '确定要删除设备 ' + peerIds[0] + ' 吗？此操作不可恢复。'
                : '确定要删除选中的 ' + peerIds.length + ' 台设备吗？此操作不可恢复。';
        }
        openModal('nav2-delete-root');
    }

    function confirmDelete() {
        const {showToast, getCookie} = getUtils();
        const {URLS} = getConstants();
        const {close: closeModal} = getModal();
        const idsInput = document.getElementById('nav2-delete-peer-ids');
        const peerIds = (idsInput ? idsInput.value : '').trim();
        if (!peerIds) return;

        const body = new URLSearchParams();
        body.set('peer_ids', peerIds);
        fetch(URLS.DEVICE_DELETE, {
            method: 'POST', credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: body.toString()
        }).then(function (resp) {
            if (!resp.ok) throw new Error('请求失败');
            return resp.json();
        }).then(function (data) {
            if (!data || data.ok !== true) throw new Error((data && data.err_msg) || '删除失败');
            closeModal('nav2-delete-root');
            showToast('已删除 ' + (data.count || 0) + ' 台设备', 'success');
            _reloadNav2();
        }).catch(function (err) {
            showToast(err.message || '删除失败', 'error');
        });
    }

    // ──────── 启用/禁用 ────────
    function toggleDevices(peerIds, enabled) {
        if (!peerIds || !peerIds.length) return;
        const {showToast, getCookie} = getUtils();
        const {URLS} = getConstants();
        const body = new URLSearchParams();
        body.set('peer_ids', peerIds.join(','));
        body.set('enabled', enabled ? 'true' : 'false');
        fetch(URLS.DEVICE_TOGGLE, {
            method: 'POST', credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: body.toString()
        }).then(function (resp) {
            if (!resp.ok) throw new Error('请求失败');
            return resp.json();
        }).then(function (data) {
            if (!data || data.ok !== true) throw new Error((data && data.err_msg) || '操作失败');
            const action = enabled ? '启用' : '禁用';
            showToast('已' + action + ' ' + (data.count || 0) + ' 台设备', 'success');
            _reloadNav2();
        }).catch(function (err) {
            showToast(err.message || '操作失败', 'error');
        });
    }

    // ──────── 备注编辑弹窗 ────────
    function showNoteModal(peerId) {
        const {open: openModal} = getModal();
        const peerInput = document.getElementById('nav2-note-peer');
        const noteInput = document.getElementById('nav2-note-text');
        if (peerInput) peerInput.value = peerId;
        if (noteInput) {
            const row = document.querySelector('tr[data-peer-id="' + peerId + '"] .nav2-note-cell');
            const current = row ? row.textContent.trim() : '';
            noteInput.value = (current === '-') ? '' : current;
            noteInput.focus();
        }
        openModal('nav2-note-root');
    }

    function submitNote() {
        const {showToast, getCookie} = getUtils();
        const {URLS} = getConstants();
        const {close: closeModal} = getModal();
        const peerId = (document.getElementById('nav2-note-peer') || {}).value || '';
        const note = (document.getElementById('nav2-note-text') || {}).value || '';
        if (!peerId) return;

        const body = new URLSearchParams();
        body.set('peer_id', peerId);
        body.set('note', note.trim());
        fetch(URLS.DEVICE_NOTE, {
            method: 'POST', credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: body.toString()
        }).then(function (resp) {
            if (!resp.ok) throw new Error('请求失败');
            return resp.json();
        }).then(function (data) {
            if (!data || data.ok !== true) throw new Error((data && data.err_msg) || '保存失败');
            closeModal('nav2-note-root');
            showToast('备注已更新', 'success');
            _reloadNav2();
        }).catch(function (err) {
            showToast(err.message || '保存失败', 'error');
        });
    }

    // ──────── 批量选择 ────────
    function getSelectedPeerIds() {
        const boxes = document.querySelectorAll('.nav2-row-checkbox:checked');
        const ids = [];
        boxes.forEach(function (cb) {
            if (cb.value) ids.push(cb.value);
        });
        return ids;
    }

    function updateMultiBar() {
        const ids = getSelectedPeerIds();
        const bar = document.getElementById('nav2-multi-bar');
        const countEl = document.getElementById('nav2-multi-count');
        if (!bar) return;
        if (ids.length > 0) {
            bar.style.display = 'flex';
            if (countEl) countEl.textContent = ids.length;
        } else {
            bar.style.display = 'none';
        }
    }

    function clearSelection() {
        const allCheck = document.getElementById('nav2-select-all');
        if (allCheck) allCheck.checked = false;
        document.querySelectorAll('.nav2-row-checkbox').forEach(function (cb) {
            cb.checked = false;
        });
        updateMultiBar();
    }

    // ──────── 标签过滤 ────────
    function setTagFilter(tag) {
        const form = document.getElementById('nav2-search-form');
        if (!form) return;
        const tagInput = form.querySelector('input[name="tag"]');
        if (tagInput) tagInput.value = tag || '';
        form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
    }

    // ──────── 右键菜单 ────────
    let _ctxPeerId = '';

    function showContextMenu(peerId, x, y) {
        _ctxPeerId = peerId;
        const menu = document.getElementById('nav2-context-menu');
        if (!menu) return;

        const row = document.querySelector('tr[data-peer-id="' + peerId + '"]');
        const isEnabled = row ? row.getAttribute('data-enabled') === 'true' : true;
        const toggleBtn = document.getElementById('nav2-ctx-toggle');
        if (toggleBtn) toggleBtn.textContent = isEnabled ? '禁用' : '启用';

        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
        menu.classList.add('nav2-context-menu--show');

        const viewW = window.innerWidth;
        const viewH = window.innerHeight;
        const rect = menu.getBoundingClientRect();
        if (rect.right > viewW) menu.style.left = Math.max(0, x - rect.width) + 'px';
        if (rect.bottom > viewH) menu.style.top = Math.max(0, y - rect.height) + 'px';
    }

    function hideContextMenu() {
        const menu = document.getElementById('nav2-context-menu');
        if (menu) menu.classList.remove('nav2-context-menu--show');
        _ctxPeerId = '';
    }

    function handleContextAction(action) {
        const peerId = _ctxPeerId;
        hideContextMenu();
        if (!peerId) return;

        if (action === 'detail') {
            fetchAndShowDetail(peerId);
        } else if (action === 'rename') {
            const row = document.querySelector('tr[data-peer-id="' + peerId + '"] .nav2-alias-cell');
            const currentAlias = row ? row.textContent.trim() : '';
            prefillRenameForm(peerId, currentAlias === '-' ? '' : currentAlias);
            getModal().open('nav2-rename-root');
        } else if (action === 'edit_tags') {
            fetchAndShowDetail(peerId);
        } else if (action === 'edit_note') {
            showNoteModal(peerId);
        } else if (action === 'toggle') {
            const row = document.querySelector('tr[data-peer-id="' + peerId + '"]');
            const isEnabled = row ? row.getAttribute('data-enabled') === 'true' : true;
            toggleDevices([peerId], !isEnabled);
        } else if (action === 'add_to_book') {
            if (typeof APP.events !== 'undefined' && APP.events.openAddToBook) {
                APP.events.openAddToBook(peerId);
            }
        } else if (action === 'delete') {
            showDeleteConfirm([peerId]);
        }
    }

    // ──────── 辅助 ────────
    function _reloadNav2() {
        const {renderContent} = getNavigation();
        const {STORAGE_KEY} = getConstants();
        const extra = collectQueryOptions(document.getElementById('nav2-search-form'));
        renderContent('nav-2', extra);
        try {
            localStorage.setItem(STORAGE_KEY, 'nav-2');
        } catch (_) {
        }
    }

    // 导出
    APP.nav2 = {
        toggleAutoRefresh: toggleAutoRefresh,
        collectQueryOptions: collectQueryOptions,
        prefillRenameForm: prefillRenameForm,
        fetchAndShowDetail: fetchAndShowDetail,
        startInlineEdit: startInlineEdit,
        submitInlineEdit: submitInlineEdit,
        cancelInlineEdit: cancelInlineEdit,
        showDeleteConfirm: showDeleteConfirm,
        confirmDelete: confirmDelete,
        toggleDevices: toggleDevices,
        showNoteModal: showNoteModal,
        submitNote: submitNote,
        getSelectedPeerIds: getSelectedPeerIds,
        updateMultiBar: updateMultiBar,
        clearSelection: clearSelection,
        setTagFilter: setTagFilter,
        showContextMenu: showContextMenu,
        hideContextMenu: hideContextMenu,
        handleContextAction: handleContextAction
    };

    window.APP = APP;

})(window);
