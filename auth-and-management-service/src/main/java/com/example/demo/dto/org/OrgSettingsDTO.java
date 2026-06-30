package com.example.demo.dto.org;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.*;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OrgSettingsDTO {
    @JsonProperty("allow_self_enrollment")
    private boolean allowSelfEnrollment;

    @JsonProperty("allow_cross_org_courses")
    private boolean allowCrossOrgCourses;

    @JsonProperty("default_course_visibility")
    private String defaultCourseVisibility; // "PUBLIC", "ORG_ONLY"

    @JsonProperty("max_members")
    private Integer maxMembers;
}
