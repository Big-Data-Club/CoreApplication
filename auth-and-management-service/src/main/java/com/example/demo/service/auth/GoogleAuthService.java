package com.example.demo.service.auth;

import com.example.demo.dto.auth.GoogleProfileResponse;
import com.example.demo.dto.auth.GoogleRegisterRequest;
import com.example.demo.enums.AuthProvider;
import com.example.demo.enums.UserRole;
import com.example.demo.exception.BadRequestException;
import com.example.demo.exception.DuplicateResourceException;
import com.example.demo.exception.UnauthorizedException;
import com.example.demo.model.User;
import com.example.demo.model.Organization;
import com.example.demo.model.OrganizationMember;
import com.example.demo.repository.UserRepository;
import com.example.demo.repository.RoleRepository;
import com.example.demo.repository.OrganizationRepository;
import com.example.demo.repository.OrganizationMemberRepository;
import com.example.demo.service.user.UserSyncService;
import com.example.demo.service.org.OrganizationSyncService;
import com.example.demo.utils.PasswordGenerator;
import com.google.api.client.googleapis.auth.oauth2.GoogleIdToken;
import com.google.api.client.googleapis.auth.oauth2.GoogleIdTokenVerifier;
import com.google.api.client.http.javanet.NetHttpTransport;
import com.google.api.client.json.gson.GsonFactory;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collections;
import java.util.Optional;

@Slf4j
@Service
@RequiredArgsConstructor
public class GoogleAuthService {

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final OrganizationRepository organizationRepository;
    private final OrganizationMemberRepository organizationMemberRepository;
    private final OrganizationSyncService organizationSyncService;
    private final PasswordEncoder passwordEncoder;
    private final UserSyncService userSyncService;

    @Value("${google.client-id}")
    private String googleClientId;

    @Value("${app.default-role:ROLE_USER}")
    private String defaultRole;

    private GoogleIdTokenVerifier verifier;

    @PostConstruct
    public void init() {
        verifier = new GoogleIdTokenVerifier.Builder(
                new NetHttpTransport(), GsonFactory.getDefaultInstance())
                .setAudience(Collections.singletonList(googleClientId))
                .build();
    }

    /**
     * Verify Google ID token and return the payload.
     * Throws UnauthorizedException if the token is invalid.
     */
    public GoogleIdToken.Payload verifyIdToken(String idTokenString) {
        try {
            GoogleIdToken idToken = verifier.verify(idTokenString);
            if (idToken == null) {
                throw new UnauthorizedException("Invalid Google ID token");
            }
            return idToken.getPayload();
        } catch (UnauthorizedException e) {
            throw e;
        } catch (Exception e) {
            log.error("Google ID token verification failed: {}", e.getMessage());
            throw new UnauthorizedException("Google ID token verification failed");
        }
    }

    /**
     * Attempt to find an existing user by Google ID or email.
     * Returns Optional.empty() if user does not exist.
     */
    @Transactional(readOnly = true)
    public Optional<User> findExistingUser(GoogleIdToken.Payload payload) {
        String googleId = payload.getSubject();
        String email = payload.getEmail();

        // Try by googleId first, then by email
        Optional<User> user = userRepository.findByGoogleId(googleId);
        if (user.isPresent()) {
            return user;
        }
        return userRepository.findByEmail(email);
    }

    /**
     * Build a GoogleProfileResponse from the token payload.
     */
    public GoogleProfileResponse buildProfileResponse(GoogleIdToken.Payload payload) {
        return GoogleProfileResponse.builder()
                .googleId(payload.getSubject())
                .email(payload.getEmail())
                .name((String) payload.get("name"))
                .picture((String) payload.get("picture"))
                .build();
    }

    /**
     * Register a new user from Google OAuth.
     * User is created with active=false, pendingApproval=true.
     */
    @Transactional
    public User registerWithGoogle(GoogleRegisterRequest req) {
        GoogleIdToken.Payload payload = verifyIdToken(req.getIdToken());
        String googleId = payload.getSubject();
        String email = payload.getEmail();

        // Check for duplicates
        if (userRepository.findByGoogleId(googleId).isPresent()) {
            throw new DuplicateResourceException("User", "googleId", googleId);
        }
        if (userRepository.existsByEmail(email)) {
            throw new DuplicateResourceException("User", "email", email);
        }
        if (userRepository.existsByCode(req.getCode())) {
            throw new DuplicateResourceException("User", "code", req.getCode());
        }

        // Generate a random password (user won't use it - Google login only)
        String randomPassword = PasswordGenerator.generateStrongPassword();

        String resolvedRole = defaultRole;
        if (!roleRepository.existsByName(resolvedRole)) {
            log.warn("Default role '{}' not found in database! Creating user with fallback 'ROLE_USER'", resolvedRole);
            resolvedRole = "ROLE_USER";
        }

        User user = User.builder()
                .name(req.getName())
                .email(email)
                .password(passwordEncoder.encode(randomPassword))
                .role(resolvedRole)
                .team(req.getTeam())
                .code(req.getCode())
                .type(req.getType())
                .organization(req.getOrganization())
                .authProvider(AuthProvider.GOOGLE)
                .googleId(googleId)
                .active(false)
                .pendingApproval(true)
                .totalScore(0)
                .profilePicture((String) payload.get("picture"))
                .build();

        User saved = userRepository.save(user);
        log.info("Google user registered (pending approval): email={}, googleId={}, role={}", email, googleId, resolvedRole);

        // Link user to their selected organization
        if (req.getOrganization() != null && !req.getOrganization().trim().isEmpty()) {
            Optional<Organization> orgOpt = organizationRepository.findByName(req.getOrganization());
            if (!orgOpt.isPresent()) {
                // Try looking up by slug
                String slug = req.getOrganization().toLowerCase().trim().replace(" ", "-");
                orgOpt = organizationRepository.findBySlug(slug);
            }
            if (orgOpt.isPresent()) {
                OrganizationMember member = OrganizationMember.builder()
                        .organization(orgOpt.get())
                        .user(saved)
                        .orgRole("MEMBER")
                        .build();
                organizationMemberRepository.save(member);
                organizationSyncService.syncMember(member);
            } else {
                log.warn("Organization '{}' not found during Google register!", req.getOrganization());
            }
        }

        return saved;
    }
}
