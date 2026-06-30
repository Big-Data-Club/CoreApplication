package com.example.demo.dto.org;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.*;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AddMemberRequest {
    @JsonProperty("user_id")
    private Long userID;

    @JsonProperty("org_role")
    private String orgRole; // OWNER, ADMIN, MEMBER
}
