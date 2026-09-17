package com.example.demo.dto.org;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.*;
import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OrgMemberResponse {
    @JsonProperty("user_id")
    private Long userID;

    @JsonProperty("full_name")
    private String fullName;

    private String email;

    @JsonProperty("org_role")
    private String orgRole;

    @JsonProperty("student_code")
    private String studentCode;

    @JsonProperty("joined_at")
    private LocalDateTime joinedAt;
}
