/**
 * São Geraldo — shared loading overlay
 * API: window.showAppLoading(message?), window.hideAppLoading()
 */
(function () {
    'use strict';

    var overlay = null;
    var textEl = null;
    var subEl = null;
    var pendingFetch = 0;
    var navShown = false;
    var fetchShowTimer = null;
    var FETCH_SHOW_DELAY_MS = 120;
    var DEFAULT_MSG = 'Processando…';
    var DEFAULT_SUB = 'Buscando informações…';

    function ensureOverlay() {
        if (overlay) return overlay;
        overlay = document.getElementById('sg-app-loading');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'sg-app-loading';
            overlay.setAttribute('role', 'status');
            overlay.setAttribute('aria-live', 'polite');
            overlay.setAttribute('aria-busy', 'false');
            overlay.innerHTML =
                '<div class="sg-app-loading-card">' +
                '  <div class="sg-app-loading-spinner" aria-hidden="true"></div>' +
                '  <p class="sg-app-loading-text"></p>' +
                '  <p class="sg-app-loading-sub"></p>' +
                '</div>';
            (document.body || document.documentElement).appendChild(overlay);
        }
        textEl = overlay.querySelector('.sg-app-loading-text');
        subEl = overlay.querySelector('.sg-app-loading-sub');
        return overlay;
    }

    function setMessages(message, sub) {
        ensureOverlay();
        if (textEl) textEl.textContent = message || DEFAULT_MSG;
        if (subEl) {
            var s = sub == null ? DEFAULT_SUB : sub;
            subEl.textContent = s;
            subEl.hidden = !s;
        }
    }

    function showAppLoading(message, sub) {
        ensureOverlay();
        setMessages(message, sub);
        overlay.classList.add('is-visible');
        overlay.setAttribute('aria-busy', 'true');
    }

    function hideAppLoading(force) {
        if (!overlay && !document.getElementById('sg-app-loading')) return;
        ensureOverlay();
        if (!force && (pendingFetch > 0 || navShown)) return;
        if (force) {
            pendingFetch = 0;
            navShown = false;
            if (fetchShowTimer) {
                clearTimeout(fetchShowTimer);
                fetchShowTimer = null;
            }
        }
        overlay.classList.remove('is-visible');
        overlay.setAttribute('aria-busy', 'false');
    }

    function bumpFetch(delta) {
        pendingFetch = Math.max(0, pendingFetch + delta);
        if (pendingFetch > 0) {
            if (navShown) {
                showAppLoading(DEFAULT_MSG, DEFAULT_SUB);
                return;
            }
            if (!fetchShowTimer) {
                fetchShowTimer = setTimeout(function () {
                    fetchShowTimer = null;
                    if (pendingFetch > 0) {
                        showAppLoading(DEFAULT_MSG, DEFAULT_SUB);
                    }
                }, FETCH_SHOW_DELAY_MS);
            }
        } else {
            if (fetchShowTimer) {
                clearTimeout(fetchShowTimer);
                fetchShowTimer = null;
            }
            if (!navShown) {
                hideAppLoading(true);
            }
        }
    }

    function isModifiedClick(ev) {
        return ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button === 1;
    }

    function shouldSkipLink(a) {
        if (!a || a.hasAttribute('data-no-loading')) return true;
        if (a.target && a.target !== '' && a.target !== '_self') return true;
        if (a.hasAttribute('download')) return true;
        var href = a.getAttribute('href');
        if (!href || href === '#' || href.indexOf('javascript:') === 0) return true;
        if (href.charAt(0) === '#') return true;
        try {
            var url = new URL(href, window.location.href);
            if (url.origin !== window.location.origin) return true;
            if (url.pathname === window.location.pathname &&
                url.search === window.location.search &&
                url.hash) {
                return true;
            }
        } catch (e) {
            return true;
        }
        return false;
    }

    function onDocumentClick(ev) {
        if (isModifiedClick(ev)) return;
        var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
        if (!a || shouldSkipLink(a)) return;
        // Defer so preventDefault (JS-only buttons) can cancel the overlay
        setTimeout(function () {
            if (ev.defaultPrevented) return;
            navShown = true;
            showAppLoading('Carregando…', DEFAULT_SUB);
        }, 0);
    }

    function onDocumentSubmit(ev) {
        var form = ev.target;
        if (!form || form.tagName !== 'FORM') return;
        if (form.hasAttribute('data-no-loading')) return;
        if (form.getAttribute('target') && form.getAttribute('target') !== '_self') return;
        // Defer: AJAX forms that preventDefault should not stick the overlay
        setTimeout(function () {
            if (ev.defaultPrevented) return;
            navShown = true;
            showAppLoading(DEFAULT_MSG, DEFAULT_SUB);
        }, 0);
    }

    function wrapFetch() {
        if (typeof window.fetch !== 'function') return;
        var nativeFetch = window.fetch.bind(window);
        window.fetch = function () {
            var args = arguments;
            var input = args[0];
            var init = args[1] || {};
            var skip = false;
            try {
                if (init && init.sgSkipLoading) skip = true;
                var urlStr = typeof input === 'string' ? input :
                    (input && input.url ? input.url : '');
                if (urlStr) {
                    var u = new URL(urlStr, window.location.href);
                    if (u.protocol === 'blob:' || u.protocol === 'data:') skip = true;
                }
            } catch (e) { /* continue */ }

            if (skip) return nativeFetch.apply(window, args);

            bumpFetch(1);
            return nativeFetch.apply(window, args).then(
                function (res) {
                    bumpFetch(-1);
                    return res;
                },
                function (err) {
                    bumpFetch(-1);
                    throw err;
                }
            );
        };
    }

    function wrapXHR() {
        if (typeof XMLHttpRequest === 'undefined') return;
        var open = XMLHttpRequest.prototype.open;
        var send = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function () {
            this.__sgTracked = true;
            return open.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function () {
            var xhr = this;
            if (xhr.__sgTracked && !xhr.__sgCounted) {
                xhr.__sgCounted = true;
                bumpFetch(1);
                var done = function () {
                    if (xhr.__sgDone) return;
                    xhr.__sgDone = true;
                    bumpFetch(-1);
                };
                xhr.addEventListener('loadend', done);
                xhr.addEventListener('abort', done);
                xhr.addEventListener('error', done);
            }
            return send.apply(this, arguments);
        };
    }

    function resetStuck() {
        pendingFetch = 0;
        navShown = false;
        if (fetchShowTimer) {
            clearTimeout(fetchShowTimer);
            fetchShowTimer = null;
        }
        hideAppLoading(true);
    }

    document.addEventListener('click', onDocumentClick, true);
    document.addEventListener('submit', onDocumentSubmit, true);
    window.addEventListener('pageshow', function () {
        resetStuck();
    });
    document.addEventListener('DOMContentLoaded', function () {
        ensureOverlay();
        resetStuck();
    });

    wrapFetch();
    wrapXHR();

    window.showAppLoading = showAppLoading;
    window.hideAppLoading = function () { hideAppLoading(true); };
})();
