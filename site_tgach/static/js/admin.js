const AdminManager = {
    init() {
        const select = document.getElementById('admin-board-select');
        const listContainer = document.getElementById('admin-ban-list');
        this.initShadowBanForm();
        this.initAlertForm();
        this.initRoleForm();
        this.initBannerForm();
        this.initTrollForm();
        this.initSystemSettings();
        if (!select || !listContainer) return;
        select.addEventListener('change', () => this.loadUsers(select.value));
        listContainer.addEventListener('click', async (e) => {
            if (e.target.classList.contains('lift-ban-btn')) {
                e.preventDefault();
                const { id, type } = e.target.dataset;
                await this.liftBan(id, type, select.value);
            }
        });
        this.loadUsers(select.value);
    },
    initAlertForm() {
        const form = document.getElementById('admin-alert-form');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const data = {
                user_id: parseInt(formData.get('user_id')),
                content: formData.get('content'),
                image_url: formData.get('image_url') || null,
                btn_text: formData.get('btn_text') || null,
                btn_link: formData.get('btn_link') || null,
                target_board: formData.get('target_board')
            };
            try {
                const res = await fetch('/api/admin/send_alert', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (res.ok) {
                    showToast(t('msg_alert_sent'));
                    form.reset();
                } else {
                    const err = await res.json();
                    showToast(`${t('error_prefix')}${err.detail}`);
                }
            } catch (err) { showToast(t('network_error')); }
        });
    },
    initBannerForm() {
        const bannerForm = document.getElementById('admin-banner-form');
        if (bannerForm) {
            bannerForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const fd = new FormData(bannerForm);
                const data = {
                    board_id: fd.get('board_id'),
                    image_url: fd.get('image_url'),
                    link_url: fd.get('link_url')
                };
                try {
                    const res = await fetch('/api/admin/set_banner', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    });
                    if (res.ok) {
                        showToast(t('msg_banner_updated'));
                    } else {
                        showToast(t('msg_save_error'));
                    }
                } catch(e) {
                    showToast(t('network_error'));
                }
            });
        }
    },
    initRoleForm() {
        const form = document.getElementById('admin-role-form');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const data = {
                user_id: parseInt(formData.get('user_id')),
                role: formData.get('role')
            };
            if (!confirm(t('admin_role_confirm').replace('{0}', data.role.toUpperCase()).replace('{1}', data.user_id))) return;
            try {
                const res = await fetch('/api/admin/set_role', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (res.ok) {
                    showToast(t('msg_role_set').replace('{0}', data.role));
                    form.reset();
                } else {
                    const err = await res.json();
                    showToast(`${t('error_prefix')}${err.detail}`);
                }
            } catch (err) { showToast(t('network_error')); }
        });
    },
    initShadowBanForm() {
        const sbForm = document.getElementById('shadow-ban-form');
        if (sbForm) {
            const newForm = sbForm.cloneNode(true);
            sbForm.parentNode.replaceChild(newForm, sbForm);
            newForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(newForm);
                const data = {
                    post_num: parseInt(formData.get('post_num')),
                    duration: parseInt(formData.get('duration'))
                };
                try {
                    const res = await fetch('/api/admin/shadow_ban', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    });
                    if (res.ok) {
                        showToast(t('msg_shadow_cast'));
                        document.getElementById('shadow-ban-modal').style.display = 'none';
                        newForm.reset();
                        const select = document.getElementById('admin-board-select');
                        if (select) this.loadUsers(select.value);
                    } else {
                        const err = await res.json();
                        showToast(`${t('error_prefix')}${err.detail}`);
                    }
                } catch (err) {
                    showToast(t('network_error'));
                }
            });
        }
    },
    initSystemSettings() {
        const saveWhitelistBtn = document.getElementById('save-whitelist-btn');
        if (saveWhitelistBtn) {
            saveWhitelistBtn.onclick = async () => {
                const input = document.getElementById('admin-whitelist-ips');
                const val = input ? input.value : "";
                try {
                    const res = await fetch('/api/admin/set_setting', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ key: 'ip_whitelist', value: val })
                    });
                    if (res.ok) {
                        showToast("Белый список IP обновлен");
                    } else {
                        showToast("Ошибка сохранения");
                    }
                } catch (e) { showToast(t('network_error')); }
            };
        }
    },

    async loadSystemSettings() {
        const whitelistInput = document.getElementById('admin-whitelist-ips');
        if (!whitelistInput) return;

        try {
            const res = await fetch('/api/admin/get_setting?key=ip_whitelist');
            const data = await res.json();
            if (data.value !== undefined) {
                whitelistInput.value = data.value;
            }
        } catch (e) { console.error("Failed to load whitelist", e); }
    },
    async loadUsers(boardId) {
        const container = document.getElementById('admin-ban-list');
        if (!container) return;
        container.innerHTML = `<div style="padding:20px; text-align:center;">${t('admin_loading')}</div>`;
        try {
            const res = await fetch(`/api/admin/users/${boardId}`);
            if (!res.ok) throw new Error('Failed to load');
            const data = await res.json();
            this.render(data, container);
        } catch (e) {
            container.innerHTML = `<div style="color:var(--error-color); padding:10px;">${t('admin_load_err').replace('{0}', e.message)}</div>`;
        }
    },
    async loadAlertsHistory() {
        const container = document.getElementById('admin-alerts-list');
        if (!container) return;
        try {
            const res = await fetch('/api/admin/alerts_history');
            if (!res.ok) throw new Error('Failed');
            const alerts = await res.json();
            if (alerts.length === 0) {
                container.innerHTML = `<p style="padding:10px;">${t('admin_hist_empty')}</p>`;
                return;
            }
            let html = '<table style="width:100%; border-collapse:collapse; font-size:0.9em;">';
            html += '<tr style="background:var(--bg-hover); text-align:left;"><th style="padding:8px;">ID Юзера</th><th style="padding:8px;">Текст</th><th style="padding:8px;">Статус</th><th style="padding:8px;">Дата</th></tr>';
            alerts.forEach(a => {
                const isRead = a.is_read ? '<span style="color:green;">✅ Прочитано</span>' : '<span style="color:orange;">✉️ Не прочитано</span>';
                const date = new Date(a.created_at * 1000).toLocaleString();
                let cleanContent = a.content.replace(/<[^>]*>/g, ''); 
                if (cleanContent.length > 50) cleanContent = cleanContent.substring(0, 50) + '...';
                const safeTitle = a.content.replace(/"/g, '&quot;');
                const safeDisplay = cleanContent.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

                html += `
                    <tr style="border-bottom:1px solid var(--border-input);">
                        <td style="padding:8px;"><b>${a.user_id}</b></td>
                        <td style="padding:8px;" title="${safeTitle}">${safeDisplay}</td>
                        <td style="padding:8px;">${isRead}</td>
                        <td style="padding:8px; font-size:0.85em; color:var(--text-secondary);">${date}</td>
                    </tr>
                `;
            });
            html += '</table>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = `<p style="padding:10px; color:red;">${t('admin_load_err').replace('{0}', '')}</p>`;
        }
    },
    async checkFeedbackCount() {
        try {
            const res = await fetch('/api/admin/feedback/count');
            const data = await res.json();
            const badge = document.getElementById('inbox-badge');
            if (badge) {
                if (data.count > 0) {
                    badge.textContent = data.count;
                    badge.style.display = 'inline-block';
                } else {
                    badge.style.display = 'none';
                }
            }
        } catch(e) {}
    },

    async loadFeedback() {
        const container = document.getElementById('feedback-list');
        if (!container) return;
        container.innerHTML = `<p style="padding:20px; text-align:center;">${t('admin_loading')}</p>`;
        try {
            const res = await fetch('/api/admin/feedback');
            if (!res.ok) throw new Error('Error');
            const list = await res.json();
            if (list.length === 0) {
                container.innerHTML = `<div style="padding:20px; text-align:center; color:gray;">${t('admin_inbox_empty')}</div>`;
                return;
            }
            const icons = {
                'suggestion': '💡', 'bug': '🐛', 'coop': '🤝',
                'other': '✉️', 'pin_request': '📌', 'borda': '♾️'
            };
            const esc = (txt) => (txt || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
            
            container.innerHTML = list.map(item => {
                const icon = icons[item.category] || '❓';
                const date = new Date(item.created_at * 1000).toLocaleString();
                const safeContact = esc(item.contact);
                const safeMessage = window.formatTextGlobal(item.message);
                const unreadClass = item.is_read ? '' : 'unread';
                
                const contactDisplay = safeContact ? `<code style="background:#333; color:#fff; padding:2px 4px; border-radius:3px;">${safeContact}</code>` : '<span style="opacity:0.5">Анон</span>';
                if (!item.is_read) {
                    fetch('/api/admin/feedback/read', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ id: item.id })
                    }).then(() => this.checkFeedbackCount());
                }

                return `
                <div class="feedback-card ${unreadClass}" style="background:var(--bg-input); border:1px solid var(--border-input); border-radius:6px; padding:15px; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:10px; border-bottom:1px solid var(--border-separator); padding-bottom:5px;">
                        <div>${icon} <b>${esc(item.category).toUpperCase()}</b> от ${contactDisplay}</div>
                        <div style="font-size:0.85em; color:var(--text-secondary);">${date}</div>
                    </div>
                    <div style="white-space:pre-wrap; font-family:sans-serif; line-height:1.5;">${safeMessage}</div>
                    <div style="margin-top:10px; font-size:0.8em; color:gray;">User ID: ${item.user_id}</div>
                </div>`;
            }).join('');
        } catch (e) {
            container.innerHTML = `<p style="color:red; text-align:center;">${t('admin_load_err').replace('{0}', '')}</p>`;
        }
    },
    render(data, container) {
        let html = '';
       const renderList = (items, type, title) => {
            html += `<div class="admin-section"><h3>${title} <span style="font-size:0.8em; opacity:0.7">(${items.length})</span></h3>`;
            if (items.length === 0) {
                html += `<p style="color:var(--text-secondary); font-style:italic;">${t('admin_list_empty')}</p>`;
            } else {
                html += '<ul class="admin-user-list">';
                items.forEach(u => {
                    const dateInfo = u.expires_at && typeof window.formatTimestamp === 'function'
                        ? `<span class="ban-date">до ${window.formatTimestamp(u.expires_at)}</span>`
                        : '';
                    html += `
                        <li class="admin-user-item">
                            <div class="user-info">
                                <span class="user-id">ID: <b>${u.user_id}</b></span>
                                ${dateInfo}
                            </div>
                            <button class="btn btn-secondary btn-small lift-ban-btn"
                                    data-id="${u.user_id}"
                                    data-type="${type}">
                                ${t('admin_btn_lift')}
                            </button>
                        </li>`;
                });
                html += '</ul>';
            }
            html += '</div>';
        };
        renderList(data.banned || [], 'ban', t('admin_bans_title'));
        renderList(data.shadow || [], 'shadow', t('admin_shadow_title'));
        container.innerHTML = html;
    },
    async liftBan(userId, type, boardId) {
        const banName = type === 'ban' ? t('admin_bans_title') : t('admin_shadow_title');
        if (!confirm(t('admin_lift_confirm').replace('{0}', banName).replace('{1}', userId))) return;
        try {
            const res = await fetch('/api/admin/lift_ban', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ user_id: parseInt(userId), board_id: boardId, ban_type: type })
            });
            if (res.ok) {
                showToast(t('msg_ban_lifted'));
                this.loadUsers(boardId);
            } else {
                const err = await res.json();
                showToast(`${t('error_prefix')}${err.detail}`);
            }
        } catch (e) {
            showToast(t('network_error'));
        }
    },
    initTrollForm() {
        const form = document.getElementById('admin-troll-form');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd = new FormData(form);
            const data = {
                ip: fd.get('ip'),
                mode: fd.get('mode'),
                duration: parseInt(fd.get('duration'))
            };
            try {
                const res = await fetch('/api/admin/troll_ip', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (res.ok) {
                    showToast("🔥 Ловушка активирована!");
                    form.querySelector('input[name="ip"]').value = "";
                    this.loadTrollList();
                } else {
                    const err = await res.json();
                    alert("Ошибка: " + err.detail);
                }
            } catch (err) { showToast(t('network_error')); }
        });
    },
    async loadTrollList() {
        const container = document.getElementById('troll-active-list');
        if (!container) return;
        try {
            const res = await fetch('/api/admin/troll_list');
            const traps = await res.json();
            if (traps.length === 0) {
                container.innerHTML = '<p style="color:gray;">Активных ловушек нет.</p>';
                return;
            }
            container.innerHTML = traps.map(t => `
                <div style="background:var(--bg-input); padding:10px; border-radius:4px; margin-bottom:5px; display:flex; justify-content:space-between; align-items:center; border-left: 4px solid #e74c3c;">
                    <div>
                        <b>${t.ip}</b> <span style="color:#aaa; font-size:0.85em; margin-left:10px;">[Mode: ${t.mode.toUpperCase()}]</span>
                        <br><small style="color:var(--text-secondary)">Осталось: ${Math.round(t.remaining / 60)} мин.</small>
                    </div>
                    <button class="btn btn-secondary btn-small" onclick="AdminManager.clearFirewall('${t.ip}')" style="color:orange; border-color:orange;">Выпустить</button>
                </div>
            `).join('');
        } catch (e) { container.innerHTML = '<p style="color:red;">Ошибка загрузки списка.</p>'; }
    },
    async clearFirewall(ip) {
        if (!confirm(`Выпустить IP ${ip} из ловушки?`)) return;
        try {
            const res = await fetch('/api/admin/firewall_clear', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ ip: ip })
            });
            if (res.ok) {
                showToast("Освобожден.");
                this.loadTrollList();
            }
        } catch (e) { showToast(t('network_error')); }
    }
};

if (document.getElementById('admin-dashboard-container')) {
    safeInit('AdminDashboard', () => AdminManager.init());
}