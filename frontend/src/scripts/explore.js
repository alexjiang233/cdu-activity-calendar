/* 活动探索左右快捷区 + 日历小日历联动。只操作 DOM，不改数据与筛选逻辑。 */
(() => {
  'use strict';
  const motion = matchMedia('(prefers-reduced-motion:reduce)');
  const scrollBehavior = () => (motion.matches ? 'instant' : 'smooth');
  const svg = (paths) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    node.setAttribute('viewBox', '0 0 24 24');
    node.setAttribute('aria-hidden', 'true');
    for (const d of paths) {
      const p = document.createElementNS(node.namespaceURI, 'path');
      p.setAttribute('d', d);
      node.append(p);
    }
    return node;
  };
  const ICONS = {
    filter: ['M3 6h18', 'M6 12h12', 'M10 18h4'],
    list: ['M4 6h16', 'M4 12h16', 'M4 18h10'],
    star: ['M12 4l2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.5-4.8 2.5.9-5.4L4.2 9.7l5.4-.8z'],
    grid: ['M4 5h6v6H4z', 'M14 5h6v6h-6z', 'M4 15h6v4H4z', 'M14 15h6v4h-6z'],
    clock: ['M12 21a9 9 0 100-18 9 9 0 000 18z', 'M12 7v5l3.5 2'],
    up: ['M12 19V5', 'M6 11l6-6 6 6'],
    close: ['M6 6l12 12', 'M18 6L6 18'],
    calendar: ['M4 6h16v14H4z', 'M8 3v4', 'M16 3v4', 'M4 11h16'],
  };

  function button(icon, label, action, extra) {
    const b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('aria-label', label);
    b.title = label;
    b.append(svg(ICONS[icon]));
    const tip = document.createElement('span');
    tip.className = 'rail-tip';
    tip.textContent = label;
    b.append(tip);
    b.addEventListener('click', action);
    if (extra) extra(b);
    return b;
  }

  const scrollTo = (target, offset = 92) => {
    if (!target) return;
    const top = target.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top: Math.max(0, top), behavior: scrollBehavior() });
  };
  const goView = (view) => {
    const link = document.querySelector('#views [data-view="' + view + '"]');
    if (link) {
      link.click();
      scrollTo(document.getElementById('results'), 96);
    }
  };
  const rails = document.createElement('div');
  rails.className = 'rail-wrap';
  rails.hidden = true;
  const left = document.createElement('aside');
  left.className = 'side-rail rail-left';
  left.setAttribute('aria-label', '活动探索快捷操作');
  left.append(
    button('filter', '回到筛选', () => {
      scrollTo(document.querySelector('.explore-controls'), 88);
      const first = document.getElementById('my-college');
      if (first) first.focus({ preventScroll: true });
    }),
    button('list', '跳到活动列表', () => {
      scrollTo(document.getElementById('catalog-list'), 96);
      const heading = document.querySelector('#catalog-list .entry-title-button');
      if (heading) heading.focus({ preventScroll: true });
    }),
    button('star', '只看精选活动', () => goView('discover')),
    button('grid', '看全部活动', () => goView('all')),
    button('clock', '看往届对比', () => goView('compare'))
  );
  const right = document.createElement('aside');
  right.className = 'side-rail rail-right';
  right.setAttribute('aria-label', '活动探索快捷操作');
  right.append(
    button('up', '回到页面顶部', () => window.scrollTo({ top: 0, behavior: scrollBehavior() })),
    button('close', '清除全部筛选', () => {
      const reset = document.getElementById('reset');
      if (reset) reset.click();
      scrollTo(document.getElementById('results'), 96);
    }),
    button('calendar', '切到活动日历', () => {
      location.hash = '#calendar';
      window.scrollTo({ top: 0, behavior: scrollBehavior() });
    })
  );
  rails.append(left, right);
  document.body.append(rails);

  // 小屏：只留两个明确用途的浮动按钮，不遮挡内容。
  const fab = document.createElement('div');
  fab.className = 'fab-stack';
  fab.setAttribute('data-show', 'false');
  fab.append(
    button('up', '回到顶部', () => window.scrollTo({ top: 0, behavior: scrollBehavior() })),
    button('filter', '调整筛选', () => {
      scrollTo(document.querySelector('.explore-controls'), 88);
    })
  );
  document.body.append(fab);

  const compact = matchMedia('(max-width: 1431px)');
  const syncRails = () => {
    const onQuery = document.body.dataset.page === 'query';
    rails.hidden = !onQuery;
    fab.setAttribute('data-show', String(onQuery && compact.matches));
  };
  addEventListener('scroll', syncRails, { passive: true });
  addEventListener('resize', syncRails);
  compact.addEventListener('change', syncRails);
  document.addEventListener('cdu:view', syncRails);
  syncRails();

  // ---------- 日历页：小日历跟随所选月份 ----------
  const MONTHS_EN = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];
  const MONTHS_SHORT = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
  const CN_NUM = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'];

  function paintMiniCalendar() {
    const title = document.getElementById('calendar-month-title');
    const card = document.querySelector('.mini-calendar');
    if (!title || !card) return;
    const match = String(title.textContent || '').match(/(\d{4})\s*年\s*(\d{1,2})\s*月/);
    if (!match) return;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const label = card.querySelector('.mini-calendar-top b');
    const word = card.querySelector('.mini-calendar-top span');
    const grid = card.querySelector('.mini-calendar-grid');
    const backword = document.querySelector('.art-calendar .art-backword');
    if (label) label.textContent = String(month);
    if (word) word.textContent = MONTHS_EN[month - 1];
    if (backword) backword.textContent = MONTHS_SHORT[month - 1];
    if (!grid) return;
    const firstWeekday = new Date(Date.UTC(year, month - 1, 1)).getUTCDay(); // 周日 0
    const offset = (firstWeekday + 6) % 7; // 周一为一周起点
    const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const now = new Date();
    const todayParts = { year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() };
    const markDay = todayParts.year === year && todayParts.month === month ? todayParts.day : Math.min(todayParts.day, days);
    const cells = [];
    for (let i = 0; i < offset; i += 1) {
      const blank = document.createElement('span');
      blank.className = 'is-empty';
      cells.push(blank);
    }
    for (let day = 1; day <= days; day += 1) {
      const cell = document.createElement('span');
      cell.textContent = String(day);
      if (day === markDay) cell.className = 'is-mark';
      cells.push(cell);
    }
    grid.replaceChildren(...cells);
    grid.setAttribute('aria-hidden', 'true');
  }

  function watchCalendar() {
    const title = document.getElementById('calendar-month-title');
    if (!title) return;
    let last = '';
    const update = () => {
      const text = title.textContent || '';
      if (text === last) return;
      last = text;
      paintMiniCalendar();
    };
    new MutationObserver(update).observe(title, { childList: true, characterData: true, subtree: true });
    document.addEventListener('cdu:view', () => requestAnimationFrame(update));
    update();
  }

  const panels=[...document.querySelectorAll('.quick-filter-panel')];
  for(const panel of panels){
    panel.addEventListener('toggle',()=>{if(panel.open)for(const other of panels)if(other!==panel)other.open=false});
    panel.addEventListener('keydown',event=>{if(event.key==='Escape'){panel.open=false;panel.querySelector('summary').focus()}});
  }
  watchCalendar();
})();
