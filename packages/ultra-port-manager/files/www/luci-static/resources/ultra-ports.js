/* C2000 Ultra port 1 UI. No role changes occur without an authenticated POST. */
(function () {
    'use strict';
    if (window.ultraPorts) return;
    var script = document.currentScript;
    var api = script && script.getAttribute('data-api');
    if (!api) return;
    var pageMode = script.getAttribute('data-page') === '1';
    var dialog, panel, current, timer, active = false, busy = false, dismissed = false, lastStatus = 0;
    var style = document.createElement('style');
    style.textContent = '.upx{color:var(--text-color,#333);background:var(--background-color,#fff);font:14px/1.6 sans-serif;padding:22px;border:1px solid #9995;border-radius:12px;box-sizing:border-box;max-width:600px;width:100%}.upx-dialog{padding:0;border:0;border-radius:12px;max-width:calc(100vw - 30px);max-height:90vh;overflow:auto}.upx-dialog::backdrop{background:#0008}.upx h3{margin:0 0 12px}.upx label{display:block;margin:12px 0 3px}.upx input,.upx select{box-sizing:border-box;width:100%;padding:8px;background:inherit;color:inherit;border:1px solid #8888;border-radius:5px}.upx button,.upx-link{padding:7px 12px;cursor:pointer;border:1px solid #8888;border-radius:6px;margin:5px 8px 0 0;white-space:nowrap}.upx button:disabled{opacity:.5;cursor:wait}.upx .upx-primary{background:#245ecc;color:white}.upx .upx-error{color:#d23535;white-space:pre-wrap}.upx .upx-note{font-size:12px;opacity:.8}.upx .upx-pending{padding:12px;background:#f7ad2830;border-radius:6px;margin-bottom:12px}.upx [hidden]{display:none!important}.upx-actions{display:flex;flex-wrap:wrap;gap:5px}.upx-link{font-size:11px;color:var(--t1,inherit);background:transparent}.upx-ask{position:fixed;right:16px;bottom:16px;width:min(380px,calc(100vw - 32px));z-index:11000;box-shadow:0 3px 20px #0003}';
    document.head.appendChild(style);
    style.textContent += `
    .upx{position:relative;background:radial-gradient(ellipse at 50% 0,#e8faff88,transparent 42%),#fff;color:#202436;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif;max-width:550px;padding:34px;border:1px solid #e6e8f0;border-radius:24px;line-height:1.7}
    .upx-dialog{position:fixed!important;inset:0!important;margin:auto!important;width:550px;height:max-content;max-width:calc(100vw - 32px);max-height:calc(100dvh - 40px);border-radius:24px;background:transparent;box-shadow:0 20px 80px #27365420}
    .upx-dialog::backdrop{background:#77869e88;backdrop-filter:blur(15px)}
    .upx h3{font-size:22px;line-height:1.5;font-weight:750;text-align:center;color:#202436;background:none;padding:0;margin:16px 0}
    .upx p{margin:10px 0;color:#727c92}.upx .upx-note{font-size:13px;line-height:1.8;text-align:center;opacity:1;color:#7b8498}
    .upx-art{position:relative;width:106px;height:106px;margin:6px auto 20px;border:1px solid #87d6e7;border-radius:50%;display:grid;place-items:center;box-shadow:0 0 0 15px #bcecff18}
    .upx-art span{display:grid;place-items:center;width:76px;height:76px;border-radius:23px;background:linear-gradient(135deg,#8a5cff,#27c3e5);color:white}
    .upx-badge{display:table;margin:0 auto;border-radius:30px;padding:3px 14px;background:#e6f4f8;color:#089cba;font-size:12px;font-weight:650}
    .upx label{font-size:13px;color:#737c91;margin-top:16px}.upx input,.upx select{height:44px;border:1px solid #e1e4ee;border-radius:10px;background:#f8f9fc;color:#252b3b;padding:8px 12px;outline:none}.upx input:focus,.upx select:focus{border-color:#906cff;box-shadow:0 0 0 3px #906cff12}
    .upx button{font-weight:650;font-size:14px;line-height:1.5;padding:13px 15px;border-radius:14px;border:1px solid #dfe2eb;background:#f6f7fb;color:#747d92;margin:0;box-shadow:none}.upx button:hover{filter:brightness(.98)}
    .upx button.upx-primary{background:linear-gradient(105deg,#8057ff,#a181ff);border-color:transparent;color:#fff}
    .upx-actions{display:grid;grid-template-columns:1fr 1fr;margin-top:22px;gap:10px}.upx-actions [data-save]{order:2}.upx .upx-error{font-size:13px;color:#d64a56;text-align:left}
    .upx-pending{background:#f3efff!important;border:1px solid #e6dcff}.upx-pending p{font-size:13px!important;color:#7757bc}.upx-pending button{margin:6px 8px 0 0;padding:8px 12px}
    .upx-details{padding:2px 16px;margin:24px 0 20px;border:1px solid #e1e4ec;border-radius:18px;background:#f8f9fb}.upx-row{display:grid;grid-template-columns:110px 1fr;gap:15px;padding:13px 0;font-size:13px;align-items:center}.upx-row+.upx-row{border-top:1px dashed #dfe4ed}.upx-row span{color:#798198}.upx-row strong{text-align:right;font-weight:650;color:#252b3b}.upx-row:last-child strong{color:#8663ff}
    .upx-link{border-color:#a28be744;background:#8e65ff12;color:var(--t1,#70609b);border-radius:8px;font-size:11px;padding:7px 10px}
    #ultra-port-page.upx{margin:18px auto 32px}
    @media(max-width:560px){.upx{padding:25px 22px;border-radius:22px}.upx h3{font-size:19px}.upx-art{width:92px;height:92px}.upx-art span{width:66px;height:66px}.upx-row{grid-template-columns:85px 1fr;font-size:12px}}
    `;

    function el(tag, text, cls) {
        var node = document.createElement(tag);
        if (text != null) node.textContent = text;
        if (cls) node.className = cls;
        return node;
    }
    function token() {
        if (window.L && L.env && L.env.token) return L.env.token;
        var input = document.querySelector('input[name="token"]');
        return input ? input.value : '';
    }
    function request(action, form) {
        var controller = new AbortController();
        var timeout = setTimeout(function () { controller.abort(); }, 15000);
        var opts = {credentials:'same-origin', cache:'no-store', signal:controller.signal};
        if (form) {
            var body = new URLSearchParams(form); body.set('token', token());
            opts.method = 'POST'; opts.body = body;
        }
        return fetch(api + '/' + action, opts).then(function (res) {
            if (!res.ok) throw new Error('请求失败（' + res.status + '），请确认登录仍有效。');
            return res.json();
        }).then(function (data) {
            if (!data.ok) throw new Error(data.error || '网口操作未完成');
            return data;
        }).finally(function () { clearTimeout(timeout); });
    }
    function error(e) {
        if (panel) {
            var target=panel.querySelector('[data-error]');
            if(!target){target=el('p','','upx-error');target.dataset.error='1';panel.appendChild(target);}
            target.textContent = e.message || String(e);
        }
    }
    function field(name, title, type) {
        var label = el('label', title), input;
        if (type === 'select') {
            input = el('select');
        } else {
            input = el('input'); input.type = type || 'text'; input.autocomplete = name === 'password' ? 'new-password' : 'off';
        }
        input.name = name;
        if (type !== 'select') input.maxLength = 128;
        label.appendChild(input); panel.appendChild(label); return input;
    }
    function option(select, value, title) {
        var opt = el('option', title); opt.value = value; select.appendChild(opt);
    }
    function header(target,badge,title) {
        var art=el('div','','upx-art'), icon=el('span');
        icon.innerHTML='<svg width="38" height="38" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="23" width="28" height="11" rx="2"/><path d="M13 12a11 11 0 0 1 14 0M16 16a6 6 0 0 1 8 0M20 21v2"/><circle cx="12" cy="28.5" r=".6" fill="currentColor"/><circle cx="17" cy="28.5" r=".6" fill="currentColor"/></svg>';
        art.appendChild(icon);target.appendChild(art);target.appendChild(el('div',badge,'upx-badge'));target.appendChild(el('h3',title));
    }
    function detail(target,label,value) {
        var row=el('div','','upx-row');row.appendChild(el('span',label));row.appendChild(el('strong',value));target.appendChild(row);
    }
    function toggleFields() {
        var wan = panel.querySelector('[name=mode]').value === 'wan';
        var proto = panel.querySelector('[name=proto]').value;
        panel.querySelector('[name=proto]').parentElement.hidden = !wan;
        ['username','password'].forEach(function (k) { panel.querySelector('[name='+k+']').parentElement.hidden = !wan || proto !== 'pppoe'; });
        ['ipaddr','netmask','gateway','dns'].forEach(function (k) { panel.querySelector('[name='+k+']').parentElement.hidden = !wan || proto !== 'static'; });
    }
    function paint(data) {
        current = data;
        panel.replaceChildren();
        header(panel,'网口 1 · '+(data.carrier?'已连接':'未接网线'),'1口 WAN / LAN 设置');
        var pending = el('div', '', 'upx-pending'); pending.dataset.pending = '1'; panel.appendChild(pending);
        var mode = field('mode', '1口用途', 'select'); option(mode,'lan','LAN：电脑或其他终端'); option(mode,'wan','WAN：上级路由器或光猫'); mode.value=data.mode;
        var proto = field('proto', '有线上网方式', 'select'); option(proto,'dhcp','DHCP（自动获取）'); option(proto,'pppoe','PPPoE（宽带拨号）'); option(proto,'static','静态IPv4'); proto.value=data.proto;
        field('username','宽带账号').value=data.username || '';
        var password=field('password','宽带密码','password'); password.placeholder=data.has_pass?'已保存，留空保留':'';
        ['ipaddr','netmask','gateway','dns'].forEach(function(k,i){field(k,['IPv4地址','子网掩码','网关','DNS（用空格分隔）'][i]).value=data[k] || '';});
        mode.addEventListener('change',toggleFields);proto.addEventListener('change',toggleFields);
        var err=el('p','','upx-error');err.dataset.error='1';err.setAttribute('role','alert');panel.appendChild(err);
        var actions=el('div','','upx-actions');panel.appendChild(actions);
        var save=el('button','应用设置','upx-primary');save.type='button';save.dataset.save='1';save.addEventListener('click',apply);actions.appendChild(save);
        if (pageMode) {var refresh=el('button','刷新状态');refresh.type='button';refresh.addEventListener('click',function(){load(true);});actions.appendChild(refresh);}
        if (!pageMode) {var close=el('button','关闭');close.type='button';close.addEventListener('click',function(){dialog.close();active=false;});actions.appendChild(close);}
        toggleFields();paintPending(data.pending);
    }
    function paintPending(p) {
        var box=panel.querySelector('[data-pending]');box.replaceChildren();box.hidden=!p;
        panel.querySelectorAll('input,select,[data-save]').forEach(function(n){n.disabled=!!p||busy;});
        if (!p) return;
        var remain=Math.max(0,Math.ceil(p.deadline-Date.now()/1000));
        box.appendChild(el('p',p.phase==='rollback_conflict'?'配置已另行修改': '设置已应用 · '+remain+'秒内选择保留更改'));
        var yes=el('button','保留更改','upx-primary');yes.type='button';yes.disabled=p.phase!=='awaiting_confirmation';yes.dataset.confirm='1';yes.onclick=function(){finish('confirm',p.id);};box.appendChild(yes);
        var back=el('button','立即回退');back.type='button';back.dataset.rollback='1';back.onclick=function(){finish('rollback',p.id);};box.appendChild(back);
    }
    function apply() {
        if (busy) return;
        var form={};panel.querySelectorAll('input,select').forEach(function(n){form[n.name]=n.value;});
        busy=true;panel.querySelector('[data-save]').disabled=true;panel.querySelector('[data-error]').textContent='';
        request('apply',form).then(function(r){current.pending=r.pending||null;paintPending(current.pending);setTimeout(function(){load(true);},3000);}).catch(error).finally(function(){busy=false;if(!current.pending)panel.querySelector('[data-save]').disabled=false;});
    }
    function finish(action,id) {
        request(action,{id:id}).then(function(){load(true);}).catch(error);
    }
    function load(force) {
        lastStatus=Date.now();
        return request('status').then(function(r){if(!panel)return;if(force || !current || (current.pending&&!r.pending))paint(r);else{current.pending=r.pending;paintPending(r.pending);}}).catch(error);
    }
    function open(pre) {
        if (!pageMode && !dialog) {
            dialog=el('dialog','','upx-dialog');panel=el('div','','upx');dialog.appendChild(panel);document.body.appendChild(dialog);
            dialog.addEventListener('close',function(){active=false;});
        }
        active=true;if(dialog&&!dialog.open)dialog.showModal();
        panel.replaceChildren(el('p','正在读取网口状态…'));current=null;
        return load(true).then(function(){
            if(pre&&pre.mode&&panel.querySelector('[name=mode]')&&!current.pending){
                panel.querySelector('[name=mode]').value=pre.mode;
                panel.querySelector('[name=proto]').value=pre.proto||'dhcp';toggleFields();
            }
        });
    }
    function addButton() {
        document.querySelectorAll('#dv-ports .dv-port').forEach(function(card){
            var name=card.querySelector('.pname');
            if (!name || name.textContent.trim()!=='网口 1' || card.querySelector('.upx-link')) return;
            var b=el('button','WAN / LAN','upx-link');b.type='button';b.setAttribute('aria-label','切换1口WAN/LAN');b.addEventListener('click',open);card.querySelector('.pm').after(b);
        });
    }
    var ask;
    function removeAsk() {if(ask){if(ask.open)ask.close();ask.remove();ask=null;}}
    function discovery() {
        if(document.hidden||active||dismissed)return;
        request('probe').then(function(r){
            if(r.state!=='router'||r.ignored){removeAsk();return;}
            if(ask)return;
            ask=el('dialog','','upx-dialog');var card=el('div','','upx');ask.appendChild(card);
            header(card,'网口接入检测','检测到路由器或网关设备，是否把1口切换为 WAN 口？');
            card.appendChild(el('p','1口当前为 LAN，已收到上级设备的上网响应。','upx-note'));
            var list=el('div','','upx-details');card.appendChild(list);
            detail(list,'识别依据',r.kind==='pppoe'?'对方响应宽带拨号（PPPoE）':'对方会自动分配上网地址（DHCP）');
            detail(list,'上级网关',r.gateway||'—');detail(list,'推荐上网方式',r.kind==='pppoe'?'PPPoE（宽带拨号）':'DHCP（自动获取）');
            var actions=el('div','','upx-actions');card.appendChild(actions);
            var ignore=el('button','忽略');ignore.onclick=function(){request('ignore',{}).then(removeAsk).catch(function(){dismissed=true;removeAsk();});};actions.appendChild(ignore);
            var go=el('button','→  切换为 WAN 口','upx-primary');go.onclick=function(){var proto=r.kind==='pppoe'?'pppoe':'dhcp';removeAsk();open({mode:'wan',proto:proto});};actions.appendChild(go);
            card.appendChild(el('p','忽略仅对本次接入有效，重新插入网线后再次检测。','upx-note'));
            document.body.appendChild(ask);ask.showModal();
        }).catch(function(){dismissed=true;removeAsk();});
    }
    function tick() {
        if(active&&!document.hidden&&current&&(current.pending||Date.now()-lastStatus>15000))load(false);
        setTimeout(tick,3000);
    }
    window.ultraPorts={open:open};
    function boot() {
        if(pageMode){panel=document.getElementById('ultra-port-page');panel.className='upx';active=true;load(true);}
        else{
            var box=document.getElementById('dv-ports');
            if(box){new MutationObserver(addButton).observe(box,{childList:true,subtree:true});addButton();}
            timer=setInterval(discovery,15000);setTimeout(discovery,1800);
        }
        setTimeout(tick,3000);
    }
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
}());
