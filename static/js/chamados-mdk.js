(function () {
    function toast(msg) {
        var t = document.getElementById('mdk-toast');
        if (!t) {
            t = document.createElement('div');
            t.id = 'mdk-toast';
            t.className = 'mdk-toast';
            document.body.appendChild(t);
        }
        t.textContent = msg;
        t.classList.add('show');
        clearTimeout(toast._tm);
        toast._tm = setTimeout(function () { t.classList.remove('show'); }, 2200);
    }
    window.mdkToast = toast;

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-mdk-drop-btn]');
        document.querySelectorAll('[data-mdk-drop-menu]').forEach(function (menu) {
            var wrap = menu.closest('[data-mdk-drop]');
            if (btn && wrap && wrap.contains(btn) && menu.contains(btn) === false) {
                var open = menu.hasAttribute('hidden');
                document.querySelectorAll('[data-mdk-drop-menu]').forEach(function (m) { m.setAttribute('hidden', ''); });
                if (open) menu.removeAttribute('hidden');
                var trigger = wrap.querySelector('[data-mdk-drop-btn]');
                if (trigger) trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
            } else if (!wrap || !wrap.contains(e.target)) {
                menu.setAttribute('hidden', '');
                var t2 = wrap && wrap.querySelector('[data-mdk-drop-btn]');
                if (t2) t2.setAttribute('aria-expanded', 'false');
            }
        });
        var stub = e.target.closest('[data-mdk-soon]');
        if (stub) {
            e.preventDefault();
            toast('Em breve');
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        document.querySelectorAll('[data-mdk-drop-menu]').forEach(function (menu) {
            menu.setAttribute('hidden', '');
        });
    });
})();
