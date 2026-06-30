package com.example.demo.dto.org;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.*;
import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OrgResponse {
    private Long id;
    private String name;
    private String slug;
    private String description;

    @JsonProperty("logo_url")
    private String logoUrl;

    @JsonProperty("is_active")
    private boolean isActive;

    private OrgSettingsDTO settings;

    @JsonProperty("created_by")
    private Long createdBy;

    @JsonProperty("created_at")
    private LocalDateTime createdAt;

    @JsonProperty("updated_at")
    private LocalDateTime updatedAt;
}
