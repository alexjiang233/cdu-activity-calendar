/* 统一数据访问层：所有页面只通过这里取数，不再依赖内嵌全量目录。 */
/* 兼容层：公开投影已由后端完成，前端只保留同名的空实现。 */
window.CduProjection = window.CduProjection || {
  apply: (catalog) => catalog,
  collegeOutOfFeatured: () => false,
};

window.CduApi = (() => {
  'use strict';
  const BASE = '/api/v1/';
  const listeners = new Set();

  async function request(path, options) {
    const response = await fetch(BASE + path, Object.assign({ headers: { Accept: 'application/json' } }, options));
    if (!response.ok) {
      const error = new Error('HTTP ' + response.status);
      error.status = response.status;
      try { error.detail = (await response.json()).detail; } catch (_) { /* 非 JSON 错误体 */ }
      throw error;
    }
    return response.json();
  }

  const state = { meta: null, taxonomies: null, home: null, ready: false, error: null };

  function catalogShell() {
    const tax = state.taxonomies || {};
    const levels = {};
    (tax.level || []).forEach((item) => { levels[item.code] = item.label; });
    const colleges = {};
    (tax.college || []).forEach((item) => { colleges[item.code] = item.label; });
    const categories = {};
    (tax.category || []).forEach((item) => { categories[item.code] = item.label; });
    return {
      schema_version: tax.schema_version || 'catalog-1',
      colleges: colleges,
      levels: levels,
      categories: categories,
      entries: [],
      coverage: tax.coverage || {},
      display_options: tax.display_options || {},
      policies: tax.policies || {},
      year_policy: (tax.policies || {}).year_policy || '',
      college_policy: (tax.policies || {}).college_policy || '',
      status_policy: (tax.policies || {}).status_policy || '',
    };
  }

  async function boot() {
    try {
      const [meta, taxonomies, home] = await Promise.all([
        request('meta/'), request('taxonomies/'), request('home/'),
      ]);
      state.meta = meta;
      state.taxonomies = taxonomies;
      state.home = home;
      state.ready = true;
      window.CduData = {
        meta: meta, taxonomies: taxonomies, home: home,
        catalog: catalogShell(),
        guides: home.guides || [],
        services: [],
      };
    } catch (error) {
      state.error = error;
      document.dispatchEvent(new CustomEvent('cdu:data-error', { detail: error }));
      throw error;
    }
    document.dispatchEvent(new Event('cdu:data-ready'));
    return state;
  }

  function activities(params) {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      query.set(key, value);
    });
    return request('activities/?' + query.toString());
  }

  function detail(id, noticeId) {
    const suffix = noticeId ? '?notice=' + encodeURIComponent(noticeId) : '';
    return request('activities/' + encodeURIComponent(id) + '/' + suffix);
  }

  function calendar(params) {
    const query = new URLSearchParams(params || {});
    return request('calendar/?' + query.toString());
  }

  function guides(params) {
    const query = new URLSearchParams(params || {});
    return request('guides/?' + query.toString());
  }

  function guide(id) { return request('guides/' + encodeURIComponent(id) + '/'); }

  function services(params) {
    const query = new URLSearchParams(params || {});
    return request('services/?' + query.toString());
  }

  function onReady(handler) {
    if (state.ready) { handler(state); return; }
    listeners.add(handler);
    document.addEventListener('cdu:data-ready', () => {
      listeners.forEach((fn) => fn(state));
      listeners.clear();
    }, { once: true });
  }

  // 启动：取到 meta/taxonomies/home 后再按顺序加载页面脚本（脚本内可同步读取 CduData）
  function loadScripts(list) {
    return Promise.all(list.map(src => new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = false; // 并行下载，仍按插入顺序执行。
      script.onload = resolve;
      script.onerror = () => reject(new Error('脚本加载失败：' + src));
      document.body.append(script);
    })));
  }

  return { boot, request, activities, detail, calendar, guides, guide, services, onReady,
           loadScripts, state };
})();
