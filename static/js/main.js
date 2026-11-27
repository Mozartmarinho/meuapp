// Layout responsivo e utilitários do São Geraldo Service
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('appSidebar') || document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const toggle = document.getElementById('menuToggle');
    const COLLAPSE_KEY = document.body.dataset.sidebarCollapse || '';
    const collapseEnabled = !!COLLAPSE_KEY;
    const mqMobile = window.matchMedia('(max-width: 768px)');

    function isMobile() {
        return mqMobile.matches;
    }

    function updateToggleAria() {
        if (!toggle) return;
        if (isMobile()) {
            const open = !!(sidebar && sidebar.classList.contains('active'));
            toggle.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            return;
        }
        if (!collapseEnabled) return;
        const collapsed = document.body.classList.contains('sidebar-collapsed');
        toggle.setAttribute('aria-label', collapsed ? 'Expandir menu' : 'Recuar menu');
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }

    function setCollapsed(collapsed) {
        document.body.classList.toggle('sidebar-collapsed', !!collapsed);
        try {
            localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
        } catch (err) { /* ignore */ }
        updateToggleAria();
    }

    if (collapseEnabled) {
        try {
            if (localStorage.getItem(COLLAPSE_KEY) === '1') setCollapsed(true);
            else setCollapsed(false);
        } catch (err) {
            setCollapsed(false);
        }
    } else {
        updateToggleAria();
    }

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('active');
        if (overlay) overlay.classList.remove('show');
        document.body.style.overflow = '';
        updateToggleAria();
    }

    function openSidebar() {
        if (!sidebar) return;
        sidebar.classList.add('active');
        if (overlay) overlay.classList.add('show');
        document.body.style.overflow = 'hidden';
        updateToggleAria();
    }

    if (toggle && sidebar) {
        toggle.addEventListener('click', function(e) {
            e.stopPropagation();
            if (isMobile()) {
                if (sidebar.classList.contains('active')) closeSidebar();
                else openSidebar();
            } else if (collapseEnabled) {
                setCollapsed(!document.body.classList.contains('sidebar-collapsed'));
            }
        });
    }

    if (overlay) {
        overlay.addEventListener('click', closeSidebar);
    }

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeSidebar();
    });

    // Fecha menu ao navegar em mobile
    if (sidebar) {
        sidebar.querySelectorAll('a[href]:not([href^="javascript"])').forEach(function(link) {
            link.addEventListener('click', function() {
                if (isMobile()) closeSidebar();
            });
        });
    }

    window.addEventListener('resize', function() {
        if (!isMobile()) closeSidebar();
        updateToggleAria();
    });
});

document.querySelectorAll('input[type="number"]').forEach(input => {
    input.addEventListener('input', function() {
        if (this.value.includes('.')) {
            const parts = this.value.split('.');
            if (parts[1].length > 2) {
                this.value = parseFloat(this.value).toFixed(2);
            }
        }
    });
});

function showAlert(message, type = 'info') {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    alert.style.position = 'fixed';
    alert.style.top = '20px';
    alert.style.right = '20px';
    alert.style.zIndex = '9999';
    document.body.appendChild(alert);
    setTimeout(() => {
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 300);
    }, 3000);
}

function confirmarAcao(mensagem = 'Tem certeza que deseja realizar esta ação?') {
    return confirm(mensagem);
}

function formatarData(data) {
    if (!data) return '-';
    const d = new Date(data);
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR');
}

function formatarMoeda(valor) {
    if (!valor) return 'R$ 0,00';
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor);
}

(function forcarCaixaAltaCadastro() {
    var tiposIgnorados = {
        password: 1, email: 1, url: 1, search: 1, hidden: 1, file: 1,
        date: 1, time: 1, 'datetime-local': 1, month: 1, week: 1,
        number: 1, color: 1, range: 1, checkbox: 1, radio: 1,
        button: 1, submit: 1, reset: 1, tel: 1
    };

    function deveMaiuscula(el) {
        if (!el || el.readOnly || el.disabled) return false;
        var tag = el.tagName;
        if (tag !== 'INPUT' && tag !== 'TEXTAREA') return false;
        if (el.dataset && (el.dataset.keepCase === '1' || el.dataset.caixa === 'normal')) return false;
        if (el.classList && (el.classList.contains('sg-combo-input') || el.classList.contains('no-uppercase'))) return false;
        if (tag === 'INPUT') {
            var type = (el.getAttribute('type') || 'text').toLowerCase();
            if (tiposIgnorados[type]) return false;
        }
        var nome = ((el.name || '') + ' ' + (el.id || '')).toLowerCase();
        if (/senha|password|email|e-mail|token/.test(nome)) return false;
        return true;
    }

    function aplicar(el) {
        if (!deveMaiuscula(el)) return;
        var upper = el.value.toLocaleUpperCase('pt-BR');
        if (upper === el.value) return;
        var start = el.selectionStart;
        var end = el.selectionEnd;
        el.value = upper;
        if (typeof start === 'number' && el.setSelectionRange) {
            try { el.setSelectionRange(start, end); } catch (err) { /* ignore */ }
        }
    }

    document.addEventListener('input', function (e) {
        if (e.isComposing) return;
        aplicar(e.target);
    }, true);
    document.addEventListener('compositionend', function (e) {
        aplicar(e.target);
    }, true);
})();

document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(e) {
        if (this.dataset.submitting) {
            e.preventDefault();
            return;
        }
        this.dataset.submitting = 'true';
        setTimeout(() => {
            delete this.dataset.submitting;
        }, 5000);
    });
});
