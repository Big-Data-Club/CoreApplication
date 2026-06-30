package com.example.demo.dto.org;

import lombok.*;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CreateOrgRequest {
    private String name;
    private String slug;
    private String description;
    private String logoUrl;
    private OrgSettingsDTO settings;
}
