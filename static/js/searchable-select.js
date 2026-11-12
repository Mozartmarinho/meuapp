/* Dropdown de filtro: digitar filtra as opções já existentes. Não altera valores. */
(function () {
    var openApi = null;

    function fold(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }

    function zoneText(node) {
        var id = (node.id || '').toLowerCase();
        var cls = typeof node.className === 'string' ? node.className.toLowerCase() : '';
        return id + ' ' + cls;
    }

    function inFilterZone(select) {
        var node = select.parentElement;
        while (node && node !== document.body) {
            var blob = zoneText(node);
            if (blob.indexOf('filtro') !== -1 || blob.indexOf('filter') !== -1) return true;
            if (node.tagName === 'FORM' && blob.indexOf('toolbar') !== -1) return true;
            if (node.classList && (
                node.classList.contains('mdk-tickets-toolbar') ||
                node.classList.contains('mdk-adv') ||
                node.classList.contains('mdk-chips')
            )) return true;
            node = node.parentElement;
        }
        return false;
    }

    function isFilterSelect(select) {
        if (!select || select.tagName !== 'SELECT') return false;
        if (select.dataset.sgCombo) return false;
        if (select.dataset.sgNoSearch != null) return false;
        if (select.multiple || select.size > 1) return false;
        if (select.closest('.sg-combo, .modal, .modal-dialog, .modal-body, .portal-card, .tec-modal')) return false;
        var ident = ((select.id || '') + ' ' + (select.getAttribute('name') || '')).toLowerCase();
        if (ident.indexOf('filtro') !== -1) return true;
        return inFilterZone(select);
    }

    function optionLabel(option) {
        return (option && (option.textContent || option.label) || '').replace(/\s+/g, ' ').trim();
    }

    function enhance(select) {
        if (!isFilterSelect(select)) return;
        select.dataset.sgCombo = '1';

        var rect = select.getBoundingClientRect();
        var parent = select.parentElement;
        var parentRect = parent ? parent.getBoundingClientRect() : rect;
        var cs = window.getComputedStyle(select);
        var full = parentRect.width > 40 && rect.width >= parentRect.width - 12;

        var wrap = document.createElement('span');
        wrap.className = 'sg-combo';
        parent.insertBefore(wrap, select);
        wrap.appendChild(select);

        if (rect.width < 24 || rect.height < 12 || full || select.classList.contains('form-control')) {
            wrap.style.display = 'block';
            wrap.style.width = '100%';
            wrap.style.maxWidth = '100%';
            wrap.style.flex = '1 1 auto';
            wrap.style.minWidth = '0';
        } else {
            wrap.style.display = 'inline-block';
            wrap.style.width = Math.max(140, Math.round(rect.width)) + 'px';
            wrap.style.maxWidth = '100%';
            wrap.style.verticalAlign = 'middle';
        }
        wrap.style.minHeight = Math.max(rect.height || 0, 30) + 'px';

        select.classList.add('sg-combo-native');
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'sg-combo-input';
        input.autocomplete = 'off';
        input.spellcheck = false;
        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-expanded', 'false');
        if (select.id) input.id = select.id + '-busca';
        input.style.fontSize = cs.fontSize;
        input.style.fontFamily = cs.fontFamily;
        input.style.fontWeight = cs.fontWeight;
        input.style.padding = cs.padding;
        input.style.paddingRight = '1.75rem';
        input.style.borderRadius = cs.borderRadius;
        input.style.color = cs.color;
        input.style.backgroundColor = cs.backgroundColor;

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'sg-combo-btn';
        button.tabIndex = -1;
        button.setAttribute('aria-label', 'Abrir lista');

        var list = document.createElement('div');
        list.className = 'sg-combo-list';
        list.hidden = true;
        list.setAttribute('role', 'listbox');
        document.body.appendChild(list);

        wrap.appendChild(input);
        wrap.appendChild(button);

        var active = -1;
        var items = [];
        var moved = false;

        function currentLabel() {
            var option = select.options[select.selectedIndex];
            return option ? optionLabel(option) : '';
        }

        function syncDisabled() {
            input.disabled = !!select.disabled;
            wrap.classList.toggle('is-disabled', !!select.disabled);
        }

        function closeList() {
            list.hidden = true;
            list.innerHTML = '';
            input.setAttribute('aria-expanded', 'false');
            wrap.classList.remove('is-open');
            if (openApi && openApi.input === input) openApi = null;
            items = [];
            active = -1;
        }

        function placeList() {
            var box = input.getBoundingClientRect();
            var width = Math.max(box.width, 180);
            var spaceBelow = window.innerHeight - box.bottom;
            var spaceAbove = box.top;
            var openUp = spaceBelow < 180 && spaceAbove > spaceBelow;
            list.style.width = width + 'px';
            list.style.left = Math.max(8, Math.min(box.left, window.innerWidth - width - 8)) + 'px';
            if (openUp) {
                var maxH = Math.max(120, Math.min(260, spaceAbove - 12));
                list.style.maxHeight = maxH + 'px';
                list.style.top = Math.max(8, box.top - maxH - 4) + 'px';
            } else {
                list.style.maxHeight = Math.max(120, Math.min(260, spaceBelow - 12)) + 'px';
                list.style.top = (box.bottom + 4) + 'px';
            }
        }

        function paintActive() {
            var nodes = list.querySelectorAll('.sg-combo-opt');
            nodes.forEach(function (node, index) {
                node.classList.toggle('is-active', index === active);
            });
            var current = nodes[active];
            if (current && current.scrollIntoView) {
                current.scrollIntoView({ block: 'nearest' });
            }
        }

        function render(query) {
            var q = fold(query);
            var all = Array.prototype.slice.call(select.options);
            var matched = all.filter(function (option) {
                if (!q) return true;
                if (!option.value && fold(optionLabel(option)).indexOf(q) === -1) return false;
                var text = fold(optionLabel(option));
                return text.indexOf(q) !== -1 || fold(option.value).indexOf(q) !== -1;
            });
            if (q) {
                matched.sort(function (a, b) {
                    var as = fold(optionLabel(a)).indexOf(q) === 0 ? 0 : 1;
                    var bs = fold(optionLabel(b)).indexOf(q) === 0 ? 0 : 1;
                    return as - bs;
                });
            }
            var hiddenCount = 0;
            if (matched.length > 250) {
                hiddenCount = matched.length - 250;
                matched = matched.slice(0, 250);
            }
            list.innerHTML = '';
            items = matched;
            var current = -1;
            matched.forEach(function (option, index) {
                if (option.index === select.selectedIndex) current = index;
            });
            active = current >= 0 ? current : (q ? 0 : -1);
            if (!matched.length) {
                var empty = document.createElement('div');
                empty.className = 'sg-combo-empty';
                empty.textContent = 'Nenhum item';
                list.appendChild(empty);
                return;
            }
            matched.forEach(function (option, index) {
                var row = document.createElement('button');
                row.type = 'button';
                row.className = 'sg-combo-opt';
                if (option.index === select.selectedIndex) row.classList.add('is-current');
                if (option.disabled) row.disabled = true;
                row.textContent = optionLabel(option) || '—';
                row.setAttribute('role', 'option');
                row.addEventListener('mousedown', function (event) {
                    event.preventDefault();
                });
                row.addEventListener('mouseenter', function () {
                    active = index;
                    paintActive();
                });
                row.addEventListener('click', function () {
                    choose(option);
                });
                list.appendChild(row);
            });
            if (hiddenCount) {
                var more = document.createElement('div');
                more.className = 'sg-combo-more';
                more.textContent = 'Continue digitando para reduzir a lista';
                list.appendChild(more);
            }
            paintActive();
        }

        function openList(query) {
            if (input.disabled) return;
            if (openApi && openApi.input !== input) openApi.close();
            render(query);
            list.hidden = false;
            input.setAttribute('aria-expanded', 'true');
            wrap.classList.add('is-open');
            placeList();
            openApi = api;
        }

        function choose(option) {
            if (!option || option.disabled) return;
            var previous = select.selectedIndex;
            select.selectedIndex = option.index;
            input.value = optionLabel(option);
            closeList();
            if (select.selectedIndex !== previous) {
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        function move(step) {
            if (!items.length) return;
            var next = active;
            var guard = 0;
            do {
                if (next < 0) next = step > 0 ? 0 : items.length - 1;
                else next = (next + step + items.length) % items.length;
                guard += 1;
            } while (items[next] && items[next].disabled && guard <= items.length);
            if (items[next] && !items[next].disabled) active = next;
            paintActive();
        }

        function restoreLabel() {
            input.value = currentLabel();
        }

        var api = {
            input: input,
            close: closeList,
            place: placeList
        };

        input.addEventListener('focus', function () {
            if (input.disabled) return;
            moved = false;
            openList('');
            input.select();
        });

        input.addEventListener('input', function () {
            moved = fold(input.value) !== fold(currentLabel());
            openList(moved ? input.value : '');
        });

        input.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowDown') {
                event.preventDefault();
                moved = true;
                if (list.hidden) openList(fold(input.value) === fold(currentLabel()) ? '' : input.value);
                move(1);
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                moved = true;
                if (list.hidden) openList('');
                move(-1);
            } else if (event.key === 'Enter') {
                if (!list.hidden && (moved || fold(input.value) !== fold(currentLabel()))) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (active >= 0 && items[active]) choose(items[active]);
                }
            } else if (event.key === 'Escape') {
                event.preventDefault();
                closeList();
                restoreLabel();
            } else if (event.key === 'Tab') {
                closeList();
                restoreLabel();
            }
        });

        input.addEventListener('blur', function () {
            window.setTimeout(function () {
                if (document.activeElement === input) return;
                closeList();
                restoreLabel();
            }, 80);
        });

        button.addEventListener('mousedown', function (event) {
            event.preventDefault();
        });
        button.addEventListener('click', function () {
            if (input.disabled) return;
            if (!list.hidden) {
                closeList();
                restoreLabel();
                return;
            }
            input.focus();
            openList('');
        });

        select.addEventListener('focus', function () {
            input.focus();
        });
        select.addEventListener('change', function () {
            if (document.activeElement !== input) restoreLabel();
        });

        new MutationObserver(function () {
            syncDisabled();
            if (document.activeElement === input && !list.hidden) {
                render(fold(input.value) === fold(currentLabel()) ? '' : input.value);
                placeList();
                return;
            }
            restoreLabel();
        }).observe(select, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['disabled', 'selected']
        });

        syncDisabled();
        restoreLabel();
    }

    function scan(root) {
        if (!root || !root.querySelectorAll) return;
        if (root.nodeType === 1 && root.matches && root.matches('select')) enhance(root);
        root.querySelectorAll('select').forEach(enhance);
    }

    function boot() {
        scan(document);
        new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(scan);
            });
        }).observe(document.body, { childList: true, subtree: true });

        window.addEventListener('resize', function () {
            if (openApi) openApi.place();
        });
        window.addEventListener('scroll', function () {
            if (openApi) openApi.place();
        }, true);
        document.addEventListener('mousedown', function (event) {
            if (!openApi) return;
            if (event.target.closest && event.target.closest('.sg-combo, .sg-combo-list')) return;
            openApi.close();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
