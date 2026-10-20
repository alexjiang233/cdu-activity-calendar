# 生产部署（示例，未验证）

**本机没有可用服务器，以下配置没有实际部署过。** 记录的是同源方案，便于有环境时照做。

## 组成

- Caddy（唯一反向代理）：静态页面与 `assets/` 直出，`/api/`、`/manage/`、`/static/` 转给 gunicorn；旧 `/admin/` 仅跳转新版。
- Django + gunicorn（127.0.0.1:8791）。
- PostgreSQL：`POSTGRES_*` 环境变量；`DEBUG=0` 时 `SECRET_KEY` 必填。

## 步骤

1. 建目录 `/srv/campus`，放 `backend/`、`frontend/`、`deploy/`，先执行 `python frontend/build.py`。
2. `python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt`。
3. 复制 `deploy/.env.example` 为 `.env`，填域名、数据库与密钥（不要提交）。
4. `cd backend && ../.venv/bin/python manage.py migrate`。
5. `../.venv/bin/python manage.py collectstatic --noinput`。
6. `../.venv/bin/python manage.py createsuperuser`（交互创建，不用默认弱密码）。
7. 迁移数据：`manage.py migrate_legacy --source /srv/data/campus.sqlite3 --public-page /srv/data/public-page.html`。
8. 启动 systemd 单元，Caddy 指向 `deploy/Caddyfile`。

## 回滚

- 代码：保留上一个 release 目录，切换 systemd 的 WorkingDirectory 后 restart。
- 数据库：PostgreSQL 每日 `pg_dump`，恢复前先 `pg_restore` 到新库验证再切换。
- 静态页面：`frontend/dist` 有版本目录即可整体回退。

## 未验证项

- PostgreSQL 实跑（本机未安装，未连接过）。
- Caddy / systemd 实机启动。
- 公网 DNS、证书、访问速度。
