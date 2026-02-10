package com.example.demo.mapper;

import com.example.demo.dto.announcement.AnnouncementRequest;
import com.example.demo.dto.announcement.AnnouncementResponse;
import com.example.demo.model.Announcement;
import com.example.demo.model.User;

public class AnnouncementMapper {

    public static AnnouncementResponse toResponse(Announcement entity) {
        return AnnouncementResponse.builder()
                .id(entity.getId())
                .title(entity.getTitle())
                .content(entity.getContent())
                .images(entity.getImages())
                .status(entity.getStatus())
                .createdAt(entity.getCreatedAt())
                .createdBy(entity.getCreatedBy() != null ? entity.getCreatedBy().getEmail() : null)
                .updatedAt(entity.getUpdatedAt())
                .updatedBy(entity.getUpdatedBy() != null ? entity.getUpdatedBy().getEmail() : null)
                .build();
    }

    public static Announcement toEntity(AnnouncementRequest request, User creator) {
        return Announcement.builder()
                .title(request.getTitle())
                .content(request.getContent())
                .images(request.getImages() != null ? new java.util.ArrayList<>(request.getImages()) : new java.util.ArrayList<>())
                .status(request.getStatus())
                .createdBy(creator)
                .build();
    }
}
