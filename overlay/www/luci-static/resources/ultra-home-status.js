(function (root) {
    'use strict';
    var pending = Object.create(null);
    function get(key, url, params, callback) {
        if (pending[key] || document.hidden) return false;
        var xhr = new XMLHttpRequest();
        pending[key] = xhr;
        var query = new URLSearchParams(params || {}).toString();
        xhr.open('GET', url + (query ? '?' + query : ''), true);
        xhr.timeout = 10000;
        function finish() { if (pending[key] === xhr) delete pending[key]; }
        xhr.onload = function () {
            finish();
            if (xhr.status !== 200) return;
            var data;
            try { data = JSON.parse(xhr.responseText); } catch (_) { return; }
            callback(xhr, data);
        };
        xhr.onerror = xhr.ontimeout = xhr.onabort = finish;
        try { xhr.send(null); } catch (_) { finish(); return false; }
        return true;
    }
    root.UltraHomeStatus = {get: get};
})(window);
