package com.example.demo.dto.org;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.*;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UpdateMemberRoleRequest {
    @JsonProperty("org_role")
    private String orgRole;
}
