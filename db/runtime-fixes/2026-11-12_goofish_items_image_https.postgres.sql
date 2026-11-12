-- 修复：商机发掘/店铺采集商品图片不显示
--
-- 原因：
--   crawler-service 从闲鱼 MTOP 拿到的图片常为 http://img.alicdn.com/...，
--   user-web 的 CSP 只允许 https: 图片，浏览器会拦截所有 HTTP 图片。
--
-- 适用数据库：PostgreSQL / crawler-service 数据库（默认 xianyu_crawler）
-- 执行前请先备份；本脚本可重复执行。

BEGIN;

-- 1) 修复已经入库的历史数据
UPDATE goofish_items
SET image_url = regexp_replace(image_url, '^http://', 'https://')
WHERE image_url LIKE 'http://%';

-- 2) 后续 crawler-service 新增/更新商品时自动归一化
CREATE OR REPLACE FUNCTION normalize_goofish_image_url()
RETURNS trigger AS $$
BEGIN
    IF NEW.image_url IS NOT NULL AND NEW.image_url LIKE 'http://%' THEN
        NEW.image_url := 'https://' || substr(NEW.image_url, 8);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_normalize_goofish_image_url ON goofish_items;

CREATE TRIGGER trg_normalize_goofish_image_url
BEFORE INSERT OR UPDATE OF image_url ON goofish_items
FOR EACH ROW
EXECUTE FUNCTION normalize_goofish_image_url();

COMMIT;
