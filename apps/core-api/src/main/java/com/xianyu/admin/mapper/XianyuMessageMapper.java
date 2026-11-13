package com.xianyu.admin.mapper;

import com.xianyu.admin.entity.XianyuMessage;
import org.apache.ibatis.annotations.*;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

@Mapper
public interface XianyuMessageMapper {

    @Select("SELECT * FROM xianyu_message WHERE tenant_id = #{tenantId} AND conversation_id = #{conversationId} AND deleted = 0 ORDER BY created_time ASC LIMIT #{offset}, #{limit}")
    List<XianyuMessage> listByConversationId(@Param("tenantId") Long tenantId, @Param("conversationId") Long conversationId, @Param("offset") int offset, @Param("limit") int limit);

    @Select("SELECT COUNT(*) FROM xianyu_message WHERE tenant_id = #{tenantId} AND deleted = 0")
    int countAll(@Param("tenantId") Long tenantId);

    @Select("SELECT COUNT(*) FROM xianyu_message WHERE tenant_id = #{tenantId} AND account_id = #{accountId} AND deleted = 0")
    int count(@Param("tenantId") Long tenantId, @Param("accountId") Long accountId);

    @Select("SELECT DATE(created_time) AS stat_date, COUNT(*) AS count FROM xianyu_message " +
            "WHERE tenant_id = #{tenantId} AND deleted = 0 AND created_time >= #{startDate} " +
            "GROUP BY DATE(created_time) ORDER BY stat_date ASC")
    List<Map<String, Object>> countDaily(@Param("tenantId") Long tenantId,
                                        @Param("startDate") LocalDate startDate);

    @Select("<script>" +
            "SELECT DATE(created_time) AS stat_date, COUNT(*) AS count FROM xianyu_message " +
            "WHERE tenant_id = #{tenantId} AND deleted = 0 AND created_time &gt;= #{startDate} " +
            "<if test='accountId != null'> AND account_id = #{accountId} </if>" +
            "GROUP BY DATE(created_time) ORDER BY stat_date ASC" +
            "</script>")
    List<Map<String, Object>> countDailyByAccount(@Param("tenantId") Long tenantId,
                                                  @Param("accountId") Long accountId,
                                                  @Param("startDate") LocalDate startDate);

    @Select("SELECT COUNT(*) FROM xianyu_message WHERE tenant_id = #{tenantId} AND conversation_id = #{conversationId} AND deleted = 0")
    int countByConversationId(@Param("tenantId") Long tenantId, @Param("conversationId") Long conversationId);

    @Insert("INSERT INTO xianyu_message(tenant_id, account_id, conversation_id, from_user_id, to_user_id, content, message_type, direction, is_auto_reply, deleted, created_time, updated_time) " +
            "VALUES(#{tenantId}, #{accountId}, #{conversationId}, #{fromUserId}, #{toUserId}, #{content}, #{messageType}, #{direction}, #{isAutoReply}, 0, NOW(), NOW())")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(XianyuMessage message);
}
