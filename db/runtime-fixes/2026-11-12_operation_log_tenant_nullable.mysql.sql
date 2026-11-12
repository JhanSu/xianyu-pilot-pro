-- 修复：平台管理员编辑用户时提示「操作审计服务暂时不可用，本次操作已取消」
--
-- 背景：
--   operation_log.tenant_id 在旧数据库中为 NOT NULL，
--   但平台管理员登录时 TenantContext.tenantId 为 NULL（超级管理员可跨租户查看），
--   导致 OperationAuditService.recordRequired 插入审计日志失败并回滚业务操作。
--
-- 适用数据库：MySQL 8.x / core-api 数据库（默认 xianyu_assistant_admin）
-- 执行前请先备份；本脚本可重复执行。

ALTER TABLE operation_log
    MODIFY COLUMN tenant_id BIGINT NULL DEFAULT NULL;
