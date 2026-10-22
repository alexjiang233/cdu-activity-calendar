"""前端唯一构建入口：把 src 组装为 dist（Django 同源提供）。

产物：frontend/dist/index.html + frontend/dist/assets/*
不内嵌活动数据；页面启动后按需请求 /api/v1/。
"""
from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / 'src'
DIST = HERE / 'dist'
ASSETS = DIST / 'assets'

SCRIPTS = ['core.js', 'calendar-core.js', 'page.js', 'catalog-ui.js', 'calendar-ui.js', 'life.js', 'explore.js']

BOOT_STYLE = """
/* 启动与失败状态：数据未就绪时给出可见反馈，不把空白当成“没有内容” */
#boot-status{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:24px;background:#6b1723;color:#fff1da;font:14px/1.5 system-ui,sans-serif;overflow:hidden}
#boot-status[hidden]{display:none}
.is-booting{overflow:hidden}
.is-booting>header,.is-booting>main,.is-booting>footer,.is-booting>.skip{visibility:hidden}
.boot-scene{width:130px;height:110px;position:relative}
.boot-ticket{position:absolute;width:76px;height:94px;left:27px;top:8px;border:1px solid #efd3ab80;border-radius:8px;background:#85313b;transform:rotate(-16deg);animation:boot-float 2s ease-in-out infinite}
.boot-ticket:nth-child(2){transform:rotate(14deg);background:#b16362;animation-delay:-.65s}
.boot-ticket:nth-child(3){transform:rotate(-2deg);background:#ffe3b6;color:#6b1723;display:grid;place-items:center;animation-delay:-1.3s}
.boot-ticket svg{width:42px;height:42px;fill:none;stroke:currentColor;stroke-width:1.4;stroke-linecap:round}
.boot-brand{font:500 11px/1.5 system-ui,sans-serif;letter-spacing:.27em;opacity:.65}
.boot-title{font:600 clamp(26px,5vw,40px)/1.4 Georgia,'Noto Serif SC',serif;letter-spacing:.05em;margin:0}
.boot-message{font-size:13px;color:#edc8bd;min-height:24px;text-align:center;max-width:85vw}
.boot-line{width:94px;height:2px;background:#efc9af30;overflow:hidden}
.boot-line:after{content:'';display:block;width:45%;height:100%;background:#ffe3b6;animation:boot-line 1.3s ease-in-out infinite}
#boot-status.is-leaving{animation:boot-reveal .75s cubic-bezier(.22,1,.36,1) both;pointer-events:none}
body.is-revealing>header,body.is-revealing>main,body.is-revealing>footer{animation:content-reveal .85s cubic-bezier(.22,1,.36,1) both}
#boot-status[data-state=error] .boot-line{display:none}
#boot-status button{margin-left:14px;border:1px solid #ffd9c2;background:transparent;color:inherit;
  border-radius:6px;padding:4px 10px;font:inherit;cursor:pointer}
@keyframes boot-float{50%{translate:0 -8px}}
@keyframes boot-line{from{translate:-110% 0}to{translate:330% 0}}
@keyframes boot-reveal{to{opacity:0}}
@keyframes content-reveal{from{opacity:0;translate:0 12px}to{opacity:1;translate:0 0}}
@media(prefers-reduced-motion:reduce){.boot-ticket,.boot-line:after,body.is-revealing>header,body.is-revealing>main,body.is-revealing>footer{animation:none}#boot-status.is-leaving{animation:none;opacity:0}}
"""

BOOT_MARKUP = '''<div id="boot-status" role="status" aria-live="polite"><div class="boot-brand">CDU / CAMPUS LIFE</div><div class="boot-scene" aria-hidden="true"><div class="boot-ticket"></div><div class="boot-ticket"></div><div class="boot-ticket"><svg viewBox="0 0 40 40"><rect x="5" y="8" width="30" height="28" rx="5"/><path d="M5 16h30M13 4v8M27 4v8M12 23h5M23 23h5M12 29h5"/></svg></div></div><p class="boot-title">校园，正在展开。</p><div class="boot-line" aria-hidden="true"></div><div class="boot-message">正在准备页面…</div></div><noscript><style>.is-booting{overflow:auto}.is-booting>header,.is-booting>main,.is-booting>footer,.is-booting>.skip{visibility:visible}#boot-status{display:none}</style><p>请启用 JavaScript 以查看校园活动和指南。</p></noscript>'''

BOOT_SCRIPT = """
<script src="assets/api.js"></script>
<script>
(function(){
  var status=document.getElementById('boot-status');
  var content=Array.from(document.querySelectorAll('body>header,body>main,body>footer'));
  content.forEach(function(node){node.inert=true});
  function say(text,state){
    if(!status)return;
    status.hidden=false;status.dataset.state=state||'loading';
    var message=status.querySelector('.boot-message');message.replaceChildren(document.createTextNode(text));
    if(state==='error'){
      var retry=document.createElement('button');retry.type='button';retry.textContent='重新载入';
      retry.addEventListener('click',function(){location.reload()});
      message.append(retry);
    }
  }
  say('正在载入校园活动数据…');
  var slow=setTimeout(function(){say('网络有点慢，仍在加载…')},10000);
  Promise.resolve().then(function(){if(!window.CduApi)throw new Error('页面脚本未能下载');return window.CduApi.boot()}).then(function(){
    return window.CduApi.loadScripts(SCRIPTS_PLACEHOLDER);
  }).then(function(){
    return window.CduInitialViewReady;
  }).then(function(){
    clearTimeout(slow);
    requestAnimationFrame(function(){requestAnimationFrame(function(){
      document.body.classList.remove('is-booting');document.body.classList.add('is-revealing');content.forEach(function(node){node.inert=false});
      setTimeout(function(){document.body.classList.remove('is-revealing')},900);
      if(status){status.classList.add('is-leaving');setTimeout(function(){status.hidden=true},matchMedia('(prefers-reduced-motion:reduce)').matches?0:750)}
    })});
  }).catch(function(error){
    clearTimeout(slow);
    console.error(error);
    say('加载未完成，请检查网络后重试。','error');
  });
})();
</script>
"""


def build():
    template = (SRC / 'index.template.html').read_text(encoding='utf-8')
    css = (SRC / 'styles' / 'app.css').read_text(encoding='utf-8') + '\n' + (SRC / 'styles' / 'activity-views.css').read_text(encoding='utf-8')
    for name in SCRIPTS:
        if not (SRC / 'scripts' / name).exists():
            raise SystemExit(f'缺少脚本：{name}')
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / 'app.css').write_text(css + BOOT_STYLE, encoding='utf-8', newline='\n')
    shutil.copyfile(SRC / 'scripts' / 'api.js', ASSETS / 'api.js')
    for name in SCRIPTS:
        shutil.copyfile(SRC / 'scripts' / name, ASSETS / name)

    digest = hashlib.sha256((template+css+BOOT_SCRIPT+BOOT_STYLE).encode())
    for name in ['api.js',*SCRIPTS]:digest.update((SRC/'scripts'/name).read_bytes())
    version = digest.hexdigest()[:16]
    boot = BOOT_SCRIPT.replace('SCRIPTS_PLACEHOLDER', json.dumps([f'assets/{n}?v={version}' for n in SCRIPTS]))
    boot = boot.replace('src="assets/api.js"',f'src="assets/api.js?v={version}"')
    page = template.replace('</head>', '<style>'+BOOT_STYLE+f'</style><link rel="stylesheet" href="assets/app.css?v={version}"></head>')
    # 启动状态条放在 body 开头
    import re as _re
    page = _re.sub(r'(<body[^>]*>)', lambda m:m.group(1)+BOOT_MARKUP, page, count=1)
    page = page.replace('</body>', boot + '</body>')
    if 'id="catalog-data"' in page or 'id="campus-life-data"' in page:
        raise SystemExit('模板里仍然内嵌数据块，已停止构建')
    (DIST / 'index.html').write_text(page, encoding='utf-8', newline='\n')

    info = {
        'index_bytes': (DIST / 'index.html').stat().st_size,
        'css_bytes': (ASSETS / 'app.css').stat().st_size,
        'scripts': SCRIPTS,
        'embedded_data': False,
    }
    (DIST / 'build-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(info, ensure_ascii=False))


if __name__ == '__main__':
    build()
