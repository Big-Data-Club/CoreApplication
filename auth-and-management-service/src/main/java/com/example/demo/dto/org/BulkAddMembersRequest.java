package com.example.demo.dto.org;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.*;
import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BulkAddMembersRequest {
    private List<String> emails;

    @JsonProperty("raw_input")
    private String rawInput;

    @JsonProperty("org_role")
    private String orgRole;
}
