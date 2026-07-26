package com.example.demo.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserProfileConfigRequest {
    private String alias;
    private Boolean published;
    private String title;
    private String bio;
    private String sectionsJson;
    private String layoutConfigJson;
    private Boolean allowDirectChat;
}
