const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const sent = [];
class XHR {
  open(method, url) { this.method = method; this.url = url; }
  send() { sent.push(this); }
}
const context = {window: {}, document: {hidden: false}, XMLHttpRequest: XHR, URLSearchParams};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../overlay/www/luci-static/resources/ultra-home-status.js'), 'utf8'), context);
const get = context.window.UltraHomeStatus.get;
let calls = 0;
assert.equal(get('modem', '/modem', {action: 'info'}, () => calls++), true);
for (let i = 0; i < 10; i++) assert.equal(get('modem', '/modem', {}, () => calls++), false);
assert.equal(sent.length, 1);
assert.equal(sent[0].timeout, 10000);
assert.equal(sent[0].url, '/modem?action=info');
sent[0].status = 200; sent[0].responseText = '{"ok":true}'; sent[0].onload();
assert.equal(calls, 1);
assert.equal(get('modem', '/modem', {}, () => calls++), true);
sent[1].ontimeout();
assert.equal(get('modem', '/modem', {}, () => calls++), true);
sent[2].onerror();
context.document.hidden = true;
assert.equal(get('device', '/device', {}, () => calls++), false);
context.document.hidden = false;
assert.equal(get('device', '/device', {}, () => calls++), true);
sent[3].status = 200; sent[3].responseText = 'invalid json'; sent[3].onload();
assert.equal(calls, 1);
assert.equal(get('device', '/device', {}, () => calls++), true);
sent[4].status = 503; sent[4].responseText = '{}'; sent[4].onload();
assert.equal(calls, 1);
assert.equal(get('device', '/device', {}, () => calls++), true);
sent[5].onabort();
assert.equal(get('gateway', '/gateway', {}, () => calls++), true);
assert.equal(get('device', '/device', {}, () => calls++), true);
console.log('Home polling: coalescing, timeouts, visibility, malformed JSON and independent keys passed');
