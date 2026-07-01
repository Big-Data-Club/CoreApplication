package com.example.demo.dto.org;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.*;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UpdateOrgRequest {
    private String name;
    private String slug;
    private String description;
    @JsonProperty("logo_url")
    private String logoUrl;
    private OrgSettingsDTO settings;
}
