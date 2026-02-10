package com.example.demo.dto.announcement;

import com.example.demo.enums.StatusPermission;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class AnnouncementRequest {
    private String title;
    private String content;
    private List<String> images;
    private StatusPermission status; // Optional: Admin/Manager can update status
}
