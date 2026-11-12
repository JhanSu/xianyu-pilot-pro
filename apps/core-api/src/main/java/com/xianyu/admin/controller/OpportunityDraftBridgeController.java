package com.xianyu.admin.controller;

import com.xianyu.admin.common.BizException;
import com.xianyu.admin.common.Result;
import com.xianyu.admin.service.AutomationClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 商机发掘商品批量存入商品草稿箱。
 *
 * <p>单独成类，避免 AutomationProxyController 继续膨胀；实际草稿写入由
 * automation-service 的 /api/workflow/drafts/batch-create 完成。</p>
 */
@RestController
@RequestMapping("/api")
public class OpportunityDraftBridgeController {
    private final AutomationClient automationClient;

    public OpportunityDraftBridgeController(AutomationClient automationClient) {
        this.automationClient = automationClient;
    }

    @PostMapping("/workflow/drafts/batch-create")
    public Result<Object> batchCreateWorkflowDrafts(@RequestBody(required = false) Map<String, Object> body) {
        Map<String, Object> payload = body == null ? new LinkedHashMap<>() : new LinkedHashMap<>(body);
        try {
            return Result.ok(automationClient.postInternalForData(
                    "/api/workflow/drafts/batch-create", payload));
        } catch (BizException e) {
            throw e;
        } catch (Exception ex) {
            throw new BizException(503, "存入草稿箱暂时不可用，请稍后重试");
        }
    }
}
