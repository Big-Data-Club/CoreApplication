package com.example.demo.controller;

import com.example.demo.dto.AliasCheckResponse;
import com.example.demo.dto.PublicUserProfileResponse;
import com.example.demo.service.UserProfileService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/hub")
@RequiredArgsConstructor
public class HubPublicController {

    private final UserProfileService userProfileService;

    @GetMapping("/{identifier}")
    public ResponseEntity<PublicUserProfileResponse> getPublicProfile(@PathVariable String identifier) {
        String requesterEmail = null;
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.isAuthenticated() && auth.getPrincipal() instanceof String) {
            requesterEmail = (String) auth.getPrincipal();
        }

        PublicUserProfileResponse response = userProfileService.getPublicProfileByIdentifier(identifier, requesterEmail);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/alias/check")
    public ResponseEntity<AliasCheckResponse> checkAlias(@RequestParam String alias) {
        String requesterEmail = null;
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.isAuthenticated() && auth.getPrincipal() instanceof String) {
            requesterEmail = (String) auth.getPrincipal();
        }

        return ResponseEntity.ok(userProfileService.checkAliasAvailability(alias, requesterEmail));
    }
}
