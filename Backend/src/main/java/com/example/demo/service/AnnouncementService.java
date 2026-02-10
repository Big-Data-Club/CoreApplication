package com.example.demo.service;

import com.example.demo.dto.announcement.*;
import com.example.demo.mapper.AnnouncementMapper;
import com.example.demo.model.Announcement;
import com.example.demo.model.User;
import com.example.demo.repository.AnnouncementRepository;
import com.example.demo.repository.UserRepository;
import jakarta.persistence.EntityNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class AnnouncementService {

    private final AnnouncementRepository announcementRepository;
    private final UserRepository userRepository;

    private User getCurrentUser() {
        String email = (String) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        return userRepository.findByEmail(email)
                .orElseThrow(() -> new EntityNotFoundException("User not found: " + email));
    }

    @Transactional(readOnly = true)
    public List<AnnouncementResponse> getAll() {
        List<Announcement> announcements = announcementRepository.findAll();
        announcements.forEach(a -> a.getImages().size());
        return announcements.stream()
                .map(AnnouncementMapper::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public AnnouncementResponse getById(Long id) {
        Announcement announcement = announcementRepository.findById(id)
                .orElseThrow(() -> new EntityNotFoundException("Announcement not found with id " + id));
        announcement.getImages().size();
        return AnnouncementMapper.toResponse(announcement);
    }

    public AnnouncementResponse create(AnnouncementRequest request) {
        User creator = getCurrentUser();
        Announcement announcement = AnnouncementMapper.toEntity(request, creator);
        announcement.setCreatedAt(LocalDateTime.now());
        return AnnouncementMapper.toResponse(announcementRepository.save(announcement));
    }

    public AnnouncementResponse update(Long id, AnnouncementRequest request) {
        Announcement existing = announcementRepository.findById(id)
                .orElseThrow(() -> new EntityNotFoundException("Announcement not found with id " + id));

        User updater = getCurrentUser();

        existing.setTitle(request.getTitle());
        existing.setContent(request.getContent());
        existing.setImages(request.getImages());
        existing.setStatus(request.getStatus());
        existing.setUpdatedAt(LocalDateTime.now());
        existing.setUpdatedBy(updater);

        return AnnouncementMapper.toResponse(announcementRepository.save(existing));
    }

    public void delete(Long id) {
        Announcement announcement = announcementRepository.findById(id)
                .orElseThrow(() -> new EntityNotFoundException("Announcement not found with id " + id));
        announcementRepository.delete(announcement);
    }
}
