# 部署、备份与回滚

## 公开静态体验

直接托管 web/ 内容（保留 config.json 的 runtime=local）。本轮可用 gh-pages 分支根目录发布，GitHub Settings → Pages 选择该分支与 /(root)。所有路径相对当前目录，不需要 Node 构建。

此地址只提供浏览器本地文档导入、检索与历史，不能运行 Python API；它不是完整服务已经部署的证据。localStorage 按浏览器和域名隔离。公开演示未调用大模型。

## 完整服务本机运行

见 README；Python 3.12，依赖锁定在 server/requirements.lock.txt；同源访问 http://127.0.0.1:8765/。生产演示请先获得服务器/域名与成本授权，本轮没有擅自购买。

## Docker + 主机 Caddy（配置已提供，尚未容器实测）

从仓库根目录：

```bash
cp .env.example .env
# 编辑 .env：APP_ENV=production；设置随机初始密码，ADMIN_PASSWORD 至少 16 字符；
# PUBLIC_ORIGIN 为真实 HTTPS origin；公网演示保持 AI_MODE=retrieval。
docker compose -f deploy/compose.yaml up -d --build
curl -f http://127.0.0.1:8765/api/health
```

Compose 读取 .env，应用只绑定主机 127.0.0.1:8765，数据在 knowpage-data 命名卷。将 deploy/Caddyfile.example 中域名替换为已授权域名，确保 DNS 正确，再由主机 Caddy 代理到该回环端口。生产 HTTPS 页面下 Secure cookie 才生效；不要把反向代理放进独立容器后还使用它自己的 127.0.0.1。

容器镜像使用非 root 用户、单 worker、持久卷、内存/进程限制和健康检查。SQLite 是单机方案，不适合多副本共享文件。上线路径检查：登录→上传原创文档→提问→核查引用→退出→重启后验证持久化。

## SQLite 在线备份与恢复

直接运行模式，Python 标准库 backup API 产生一致性快照：

```bash
python -c "import sqlite3; s=sqlite3.connect('data/knowpage.db'); d=sqlite3.connect('knowpage-backup.db'); s.backup(d); d.close(); s.close()"
```

备份含用户/会话/文档，属于私有数据，严禁推送仓库。容器模式可在 app 内运行相同 backup 逻辑将副本写到 /app/data/backup.db，再用 docker compose cp 复制到受控位置。生产使用受限权限并做恢复演练。

恢复前停止服务并保留当前数据库副本，再用验证过的备份替换 knowpage.db。恢复后核对权限、文档、问答；旧会话可能随备份恢复，应按需要清空 sessions。不能在服务写入时直接覆盖数据库；不要执行 down -v 删除数据卷。

## 模型与公网成本

AI_BASE_URL 是管理员指定的 HTTPS 兼容接口（本机模型可用回环 HTTP），不是终端用户传入的抓取 URL。不向浏览器注入 API Key。适配器只调用 /chat/completions，当前无 live 凭据实测。

默认仅检索，不产生模型调用。单进程请求限速不等于费用上限；若要开启付费模型公网访问，先加总额度/每日配额、可信代理限流、用量审计，再根据用户预算启用。没有这些条件不开放付费 live 公网演示。

## 升级

记录部署源 commit→一致性备份→拉取指定版本→检查 user_version 兼容性→重建与冒烟测试。当前数据库版本为 1；未来迁移需新增版本化迁移，不可假定任意旧版本都能读新库。回滚同时考虑模式兼容。

## 尚未完成的环境验证

本机没有 Docker，尚未提供完整服务的公网服务器/域名。Docker、HTTPS、生产备份恢复命令是可执行部署材料，不能标记为已运行成功。完整 Python 服务、真实 PDF 上传和 API 权限已在本机测试。
