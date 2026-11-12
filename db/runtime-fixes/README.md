# 运行时数据库修复

本目录记录 2026-11-12 部署环境中执行过、但不属于常规版本迁移的数据库修复。
这些脚本不是 Flyway 迁移，需在维护窗口手动执行，执行前请先备份数据库。

| 数据库 | 脚本 | 用途 |
| --- | --- | --- |
| MySQL `core-api` | `2026-11-12_operation_log_tenant_nullable.mysql.sql` | 允许平台管理员跨租户操作写入操作审计日志 |
| PostgreSQL `crawler-service` | `2026-11-12_goofish_items_image_https.postgres.sql` | 历史商品图片 URL 升级 HTTPS，并自动规范化后续写入 |

## 说明

- SVP 会员数据（指定用户的 `vip_level=2`、永久有效）属于个人运行数据，**没有写入本仓库**，避免公开泄露账号信息；请通过后台「用户与权限 → 用户管理 → 编辑用户」或对应管理 API 设置。
- 执行前备份示例：
  - MySQL：`mysqldump ... xianyu_assistant_admin > backup.sql`
  - PostgreSQL：`pg_dump ... xianyu_crawler > crawler.dump`
