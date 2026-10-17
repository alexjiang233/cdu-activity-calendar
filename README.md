# 成都大学校园活动索引

让学生按月份、类型和参与对象了解校园活动，保留各年公告、分条要求和来源。历史活动不代表当届正在报名。

网站：https://alexjiang233.github.io/cdu-activity-calendar/

## 当前结构

官方正文与附件 → 本地证据校验 → SQLite正式资料库 → 静态网页 → GitHub Pages。

数据库只供本地维护，浏览器不直接访问它。网站无需常驻服务器、账号或在线数据库。首次迁移保留484活动、555公告、4878事实。

- scripts/catalog_store.py：存取、结构检查、事务、版本与回退。
- scripts/manage_content.py：统一维护入口。
- scripts/schema/001_initial.sql：结构与索引。
- scripts/share_demo.py：数据库到网页的兼容导出。
- data/：本地数据库与备份，不公开；原始资料保持原位。
- docs/体系架构与边界.md：设计、数据语义和扩展边界。
- docs/数据维护操作手册.md：接入、检查、构建、备份、恢复。

## 从公开页面恢复维护环境

基础维护使用Python 3.10+标准库。公开仓库网页在根目录index.html，本地工作区网页在public/index.html。

```sh
python scripts/manage_content.py migrate --release index.html --batch-id initial-restore --reason "从已发布网页恢复公开数据"
python scripts/manage_content.py check
python scripts/manage_content.py export --output work/export
python scripts/manage_content.py build --output work/preview/index.html
python -m unittest discover -s tests -p test_catalog_store.py
```

首次迁移只执行一次，已有库拒绝重新灌入网页。构建不会自动推送或重新采集。

原始证据、待处理队列、旧批次适配器及依赖保留在完整本地维护环境。公开运行源码不包含这些材料；sync-legacy仅供完整维护环境接入经原有证据管线校验的更新。公开源码可独立执行基础迁移、检查、导出、构建、备份和回退。

## 发布与交接

公开仓库只放网站、运行源码、规范和测试。SQLite、备份、原始资料、私人证据、待处理队列和凭据不公开。导入和最终网页共用隐私闸；历史版本不因过期删除。入库与云端发布分别记录，不能把本地入库称为已上线。

源站只托管公开文件。没有在线后台、多人编辑、账号同步或异地自动备份；按实际需求再加，避免预先增加维护负担。字体许可位于licenses/fonts/。
