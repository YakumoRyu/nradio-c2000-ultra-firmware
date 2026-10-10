'use strict';
'require view';
'require rpc';
'require fs';
'require ui';

var callSystemInfo = rpc.declare({
	object: 'system', method: 'info', expect: { '': {} }
});

function mib(value) {
	return (Number(value || 0) / 1048576).toFixed(1) + ' MiB';
}

return view.extend({
	load: function() { return callSystemInfo(); },
	updateMemory: function(info) {
		var m = info.memory || {};
		Object.keys(this.fields).forEach(function(key) {
			this.fields[key].textContent = mib(m[key]);
		}, this);
	},
	handleRelease: function(ev) {
		var button = ev.currentTarget;
		button.disabled = true;
		this.result.textContent = '正在同步并释放文件缓存…';
		this.result.className = 'alert-message notice';
		return callSystemInfo().then(function(before) {
			return fs.exec('/usr/libexec/ramfree').then(function(result) {
				if (result.code !== 0)
					throw new Error(result.stderr || ('操作失败，退出码：' + result.code));
				return callSystemInfo();
			}).then(function(after) {
				this.updateMemory(after);
				this.result.textContent = '文件缓存清理完成。可用内存：' +
					mib(before.memory.available) + ' → ' + mib(after.memory.available) +
					'。系统会按需要重新建立缓存。';
				this.result.className = 'alert-message success';
			}.bind(this));
		}.bind(this)).catch(function(error) {
			this.result.textContent = '释放失败：' + error.message;
			this.result.className = 'alert-message warning';
		}.bind(this)).finally(function() { button.disabled = false; });
	},
	render: function(info) {
		this.fields = {};
		var rows = [['total', '内存总量'], ['available', '可用内存'],
			['free', '空闲内存'], ['cached', '文件缓存'], ['buffered', '缓冲区']].map(function(item) {
			var value = this.fields[item[0]] = E('td');
			return E('tr', { 'class': 'tr' }, [E('td', { 'class': 'td' }, item[1]), value]);
		}, this);
		this.result = E('p', { 'id': 'ramfree-result', 'role': 'status', 'aria-live': 'polite' },
			'点击按钮后，执行结果会显示在这里。');
		this.updateMemory(info);
		return E('div', {}, [
			E('h2', {}, '释放内存'),
			E('p', {}, '手动释放可回收的文件缓存。缓存本身可以被系统自动回收，通常无需频繁清理。'),
			E('table', { 'class': 'table' }, rows),
			E('button', { 'id': 'ramfree-release', 'class': 'cbi-button cbi-button-action',
				'disabled': !L.hasViewPermission() || null, 'click': ui.createHandlerFn(this, 'handleRelease') }, '立即释放'),
			this.result
		]);
	},
	handleSaveApply: null, handleSave: null, handleReset: null
});
