"""工作流商品草稿箱服务：CRUD + 重试发布

设计说明：
- workflow_goods_draft 表为状态机模型：一商品一记录，可重复发布（draft → publishing → published/failed）
- 与 workflow_publish_record（每次发布动作新增一条记录的流水模型）互补
- 重试发布复用 XianyuItemPublisher，与 automation_runtime.py PUBLISH 节点保持一致
"""
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _serialize_datetime(value: Any) -> Optional[str]:
    """将 datetime/ date 等时间对象序列化为 ISO 字符串"""
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _safe_json_parse(value: Any) -> Any:
    """若 value 是字符串则尝试 JSON 解析；否则原样返回"""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


async def list_drafts(
    session: AsyncSession,
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    workflow_id: Optional[int] = None,
    keyword: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """分页查询草稿列表"""
    conditions = ["tenant_id = :tenant_id", "deleted = 0"]
    params: Dict[str, Any] = {"tenant_id": tenant_id}
    if status and status != "all":
        conditions.append("publish_status = :status")
        params["status"] = status
    if workflow_id:
        conditions.append("workflow_id = :workflow_id")
        params["workflow_id"] = workflow_id
    if keyword:
        conditions.append("(title LIKE :keyword OR description LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if start_date:
        conditions.append("created_time >= :start_date")
        params["start_date"] = start_date
    if end_date:
        conditions.append("created_time <= :end_date")
        params["end_date"] = end_date

    where_clause = " AND ".join(conditions)
    offset = max(0, (page - 1) * page_size)

    count_sql = f"SELECT COUNT(*) FROM workflow_goods_draft WHERE {where_clause}"
    total = await session.scalar(text(count_sql), params)
    total = int(total or 0)

    list_sql = (
        "SELECT id, tenant_id, user_id, workflow_id, workflow_execution_id, workflow_name, "
        "node_key, account_id, title, price, description, cover_pic, image_urls, category, "
        "stock, publish_status, publish_time, xianyu_goods_id, publish_error_message, "
        "publish_attempt_count, created_time, updated_time "
        f"FROM workflow_goods_draft WHERE {where_clause} "
        "ORDER BY created_time DESC LIMIT :limit OFFSET :offset"
    )
    params_with_paging = {**params, "limit": page_size, "offset": offset}
    result = await session.execute(text(list_sql), params_with_paging)
    records = [dict(row._mapping) for row in result.all()]

    for r in records:
        r["image_urls"] = _safe_json_parse(r.get("image_urls"))
        r["publish_time"] = _serialize_datetime(r.get("publish_time"))
        r["created_time"] = _serialize_datetime(r.get("created_time"))
        r["updated_time"] = _serialize_datetime(r.get("updated_time"))

    return {"records": records, "total": total, "page": page, "pageSize": page_size}


async def get_draft(session: AsyncSession, draft_id: int, tenant_id: int) -> Optional[Dict[str, Any]]:
    """获取草稿详情"""
    result = await session.execute(
        text("SELECT * FROM workflow_goods_draft WHERE id=:id AND tenant_id=:tid AND deleted=0"),
        {"id": draft_id, "tid": tenant_id},
    )
    row = result.first()
    if not row:
        return None
    record = dict(row._mapping)
    record["image_urls"] = _safe_json_parse(record.get("image_urls"))
    record["location"] = _safe_json_parse(record.get("location"))
    record["raw_payload"] = _safe_json_parse(record.get("raw_payload"))
    for k in ("publish_time", "created_time", "updated_time"):
        record[k] = _serialize_datetime(record.get(k))
    return record


async def update_draft(
    session: AsyncSession,
    draft_id: int,
    tenant_id: int,
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """编辑草稿的标题、价格、分类、库存、商品详情。"""
    result = await session.execute(
        text("SELECT * FROM workflow_goods_draft WHERE id=:id AND tenant_id=:tid AND deleted=0"),
        {"id": draft_id, "tid": tenant_id},
    )
    row = result.first()
    if not row:
        raise ValueError("草稿不存在")

    allowed = {"title", "price", "category", "stock", "description"}
    fields: Dict[str, Any] = {}
    for key in allowed:
        if key not in updates:
            continue
        value = updates.get(key)
        if key == "title":
            title = str(value or "").strip()
            if not title:
                raise ValueError("标题不能为空")
            fields["title"] = title[:500]
        elif key == "price":
            fields["price"] = str(value or "").strip()[:50] or None
        elif key == "category":
            fields["category"] = str(value or "").strip()[:100] or None
        elif key == "stock":
            try:
                stock = int(value)
            except (TypeError, ValueError):
                raise ValueError("库存必须为整数")
            if stock < 0:
                raise ValueError("库存不能为负数")
            fields["stock"] = stock
        elif key == "description":
            fields["description"] = str(value or "")

    if not fields:
        raise ValueError("没有可更新的字段")

    set_clause = ", ".join(f"{key}=:{key}" for key in fields)
    params = {**fields, "id": draft_id, "tid": tenant_id}
    await session.execute(
        text(
            f"UPDATE workflow_goods_draft SET {set_clause}, updated_time=NOW() "
            "WHERE id=:id AND tenant_id=:tid AND deleted=0"
        ),
        params,
    )
    await session.commit()
    updated = await get_draft(session, draft_id, tenant_id)
    if updated is None:
        raise ValueError("草稿不存在")
    return updated


async def batch_update_drafts(
    session: AsyncSession,
    tenant_id: int,
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """批量更新草稿字段；items 每项包含 id 及要修改的字段。"""
    if not isinstance(items, list) or not items:
        raise ValueError("items 不能为空")
    if len(items) > 500:
        raise ValueError("单次最多修改 500 个商品")

    updated = 0
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue
        try:
            draft_id = int(item.get("id"))
        except (TypeError, ValueError):
            skipped += 1
            continue
        payload = {k: v for k, v in item.items() if k in {"title", "price", "category", "stock", "description"}}
        if not payload:
            skipped += 1
            continue
        try:
            await update_draft(session, draft_id, tenant_id, payload)
            updated += 1
        except ValueError:
            skipped += 1
    return {"updated": updated, "skipped": skipped, "total": len(items)}


async def retry_publish_draft(
    session: AsyncSession,
    draft_id: int,
    tenant_id: int,
    override_account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """重试发布单个草稿

    状态机：draft/failed → publishing → published/failed
    拒绝状态：publishing（正在发布中）、published（已发布成功）

    :param override_account_id: 可选，指定重新发布使用的账号 ID。
        传值时使用该账号发布（草稿原账号 ID 仅作回退参考）；
        不传值时回退到草稿原 account_id。
    """
    result = await session.execute(
        text("SELECT * FROM workflow_goods_draft WHERE id=:id AND tenant_id=:tid AND deleted=0"),
        {"id": draft_id, "tid": tenant_id},
    )
    row = result.first()
    if not row:
        raise ValueError("草稿不存在")
    draft = dict(row._mapping)

    if draft.get("publish_status") == "publishing":
        raise ValueError("该草稿正在发布中，请勿重复操作")
    if draft.get("publish_status") == "published":
        raise ValueError("该草稿已发布成功，无需重试")

    # 选定本次发布使用的账号 ID：优先使用 override，回退到草稿原账号
    effective_account_id = override_account_id or draft.get("account_id")

    # 更新状态为发布中（同时记录本次使用的账号 ID，便于后续审计）
    await session.execute(
        text(
            "UPDATE workflow_goods_draft "
            "SET publish_status='publishing', publish_attempt_count=publish_attempt_count+1, "
            "account_id=:aid, publish_time=NOW(), updated_time=NOW() WHERE id=:id"
        ),
        {"id": draft_id, "aid": effective_account_id},
    )
    await session.commit()

    # 复用 XianyuItemPublisher（与 automation_runtime.py PUBLISH 节点一致）
    try:
        from app.services.xianyu_goods_sync import (
            XianyuItemPublisher,
            extract_token_from_cookie,
            _resolve_account_cookie,
        )

        account_id = effective_account_id
        cookie_str: Optional[str] = None
        if account_id:
            cookie_str, cookie_err, _ = await _resolve_account_cookie(
                session, tenant_id, account_id, {}
            )
            if cookie_err or not cookie_str:
                raise RuntimeError("发布账号登录状态不可用，请重新登录")
        else:
            raise RuntimeError("草稿未关联发布账号，请选择账号后重试")

        token = extract_token_from_cookie(cookie_str)
        if not token:
            raise RuntimeError("Cookie中缺少_m_h5_tk，请重新登录")

        publisher = XianyuItemPublisher(cookie_str, tenant_id)
        image_urls = _safe_json_parse(draft.get("image_urls")) or []
        item_data: Dict[str, Any] = {
            "title": draft.get("title", ""),
            "desc": draft.get("description", "") or "",
            "imageUrls": image_urls,
            "price": draft.get("price", "1") or "1",
            "quantity": int(draft.get("stock") or 1),
        }
        if draft.get("category"):
            item_data["category"] = {"catName": draft["category"]}
        location = _safe_json_parse(draft.get("location"))
        if location:
            item_data["location"] = location

        result_pub = publisher.publish(item_data)
        if result_pub.get("success"):
            xianyu_goods_id = str(result_pub.get("itemId", ""))
            await session.execute(
                text(
                    "UPDATE workflow_goods_draft "
                    "SET publish_status='published', xianyu_goods_id=:gid, "
                    "publish_error_message=NULL, updated_time=NOW() WHERE id=:id"
                ),
                {"gid": xianyu_goods_id, "id": draft_id},
            )
            await session.commit()
            return {"success": True, "xianyuGoodsId": xianyu_goods_id, "draftId": draft_id}

        err_msg = str(result_pub.get("error") or result_pub.get("message") or "发布失败")
        await session.execute(
            text(
                "UPDATE workflow_goods_draft "
                "SET publish_status='failed', publish_error_message=:err, updated_time=NOW() WHERE id=:id"
            ),
            {"err": err_msg[:2000], "id": draft_id},
        )
        await session.commit()
        return {"success": False, "error": err_msg, "draftId": draft_id}

    except Exception as e:
        logger.exception("[草稿重试] 发布失败 draft_id=%s", draft_id)
        await session.execute(
            text(
                "UPDATE workflow_goods_draft "
                "SET publish_status='failed', publish_error_message=:err, updated_time=NOW() WHERE id=:id"
            ),
            {"err": str(e)[:2000], "id": draft_id},
        )
        await session.commit()
        return {"success": False, "error": str(e), "draftId": draft_id}


async def batch_retry_publish_drafts(
    session: AsyncSession,
    draft_ids: List[int],
    tenant_id: int,
    override_account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """批量重试发布

    :param override_account_id: 可选，指定重新发布使用的账号 ID。
        传值时所有草稿都使用该账号发布；不传时回退到各草稿原 account_id。
    """
    results = []
    success_count = 0
    failed_count = 0
    for draft_id in draft_ids:
        try:
            r = await retry_publish_draft(session, draft_id, tenant_id, override_account_id)
            results.append({"draftId": draft_id, **r})
            if r.get("success"):
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            results.append({"draftId": draft_id, "success": False, "error": str(e)})
            failed_count += 1
    return {
        "results": results,
        "total": len(draft_ids),
        "success": success_count,
        "failed": failed_count,
    }


async def delete_draft(session: AsyncSession, draft_id: int, tenant_id: int) -> bool:
    """软删除草稿"""
    result = await session.execute(
        text(
            "UPDATE workflow_goods_draft SET deleted=1, updated_time=NOW() "
            "WHERE id=:id AND tenant_id=:tid"
        ),
        {"id": draft_id, "tid": tenant_id},
    )
    await session.commit()
    return result.rowcount > 0


async def get_draft_stats(session: AsyncSession, tenant_id: int) -> Dict[str, int]:
    """草稿统计：按 publish_status 分组计数"""
    total = await session.scalar(
        text("SELECT COUNT(*) FROM workflow_goods_draft WHERE tenant_id=:tid AND deleted=0"),
        {"tid": tenant_id},
    )
    draft = await session.scalar(
        text(
            "SELECT COUNT(*) FROM workflow_goods_draft "
            "WHERE tenant_id=:tid AND deleted=0 AND publish_status='draft'"
        ),
        {"tid": tenant_id},
    )
    published = await session.scalar(
        text(
            "SELECT COUNT(*) FROM workflow_goods_draft "
            "WHERE tenant_id=:tid AND deleted=0 AND publish_status='published'"
        ),
        {"tid": tenant_id},
    )
    failed = await session.scalar(
        text(
            "SELECT COUNT(*) FROM workflow_goods_draft "
            "WHERE tenant_id=:tid AND deleted=0 AND publish_status='failed'"
        ),
        {"tid": tenant_id},
    )
    return {
        "total": int(total or 0),
        "draft": int(draft or 0),
        "published": int(published or 0),
        "failed": int(failed or 0),
    }
