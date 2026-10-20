"""前端唯一构建入口：把 src 组装为 dist（Django 同源提供）。

产物：frontend/dist/index.html + frontend/dist/assets/*
不内嵌活动数据；页面启动后按需请求 /api/v1/。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / 'src'
DIST = HERE / 'dist'
ASSETS = DIST / 'assets'

SCRIPTS = ['core.js', 'calendar-core.js', 'page.js', 'catalog-ui.js', 'calendar-ui.js', 'life.js', 'explore.js']

BOOT_STYLE = """
/* 启动与失败状态：数据未就绪时给出可见反馈，不把空白当成“没有内容” */
#boot-status{position:fixed;left:0;right:0;top:0;z-index:80;display:flex;justify-content:center;
  padding:10px 16px;background:#6b1723;color:#fff4e8;font-size:14px;line-height:1.5}
#boot-status[hidden]{display:none}
#boot-status[data-state=error]{background:#7d1d2a}
#boot-status button{margin-left:14px;border:1px solid #ffd9c2;background:transparent;color:inherit;
  border-radius:6px;padding:4px 10px;font:inherit;cursor:pointer}
"""

BOOT_SCRIPT = """
<script src="assets/api.js"></script>
<script>
(function(){
  var status=document.getElementById('boot-status');
  function say(text,state){
    if(!status)return;
    status.hidden=false;status.dataset.state=state||'loading';
    status.innerHTML='';
    status.append(document.createTextNode(text));
    if(state==='error'){
      var retry=document.createElement('button');retry.type='button';retry.textContent='重新载入';
      retry.addEventListener('click',function(){location.reload()});
      status.append(retry);
    }
  }
  say('正在载入校园活动数据…');
  window.CduApi.boot().then(function(){
    return window.CduApi.loadScripts(SCRIPTS_PLACEHOLDER);
  }).then(function(){
    if(status)status.hidden=true;
  }).catch(function(error){
    console.error(error);
    say('数据载入失败：'+(error&&error.message?error.message:'网络异常')+'。页面没有显示“没有内容”，可以重试。','error');
  });
})();
</script>
"""


def build():
    template = (SRC / 'index.template.html').read_text(encoding='utf-8')
    css = (SRC / 'styles' / 'app.css').read_text(encoding='utf-8')
    for name in SCRIPTS:
        if not (SRC / 'scripts' / name).exists():
            raise SystemExit(f'缺少脚本：{name}')
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / 'app.css').write_text(css + BOOT_STYLE, encoding='utf-8', newline='\n')
    shutil.copyfile(SRC / 'scripts' / 'api.js', ASSETS / 'api.js')
    for name in SCRIPTS:
        shutil.copyfile(SRC / 'scripts' / name, ASSETS / name)

    boot = BOOT_SCRIPT.replace('SCRIPTS_PLACEHOLDER', json.dumps([f'assets/{n}' for n in SCRIPTS]))
    page = template.replace('</head>', ' <link rel="stylesheet" href="assets/app.css"></head>')
    # 启动状态条放在 body 开头
    import re as _re
    page = _re.sub(r'(<body[^>]*>)', r'\1\n<div id="boot-status" role="status" aria-live="polite">正在载入…</div>', page, count=1)
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
