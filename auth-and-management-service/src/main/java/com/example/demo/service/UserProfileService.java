package com.example.demo.service;

import com.example.demo.dto.AliasCheckResponse;
import com.example.demo.dto.PublicUserProfileResponse;
import com.example.demo.dto.UserProfileConfigRequest;
import com.example.demo.exception.ResourceNotFoundException;
import com.example.demo.model.User;
import com.example.demo.model.UserProfile;
import com.example.demo.model.UserProfileAliasHistory;
import com.example.demo.repository.UserProfileAliasHistoryRepository;
import com.example.demo.repository.UserProfileRepository;
import com.example.demo.repository.UserRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.jsoup.Jsoup;
import org.jsoup.safety.Safelist;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserProfileService {

    private final UserProfileRepository userProfileRepository;
    private final UserProfileAliasHistoryRepository aliasHistoryRepository;
    private final UserRepository userRepository;
    private final ObjectMapper objectMapper;

    private static final Pattern ALIAS_PATTERN = Pattern.compile("^[a-z0-9]+(-[a-z0-9]+)*$");
    private static final Set<String> RESERVED_ALIASES = Set.of(
            "admin", "administrator", "api", "auth", "bdc-hub", "myaccount", "settings",
            "login", "register", "logout", "system", "support", "help", "root", "null",
            "undefined", "profile", "dashboard", "user", "users", "chat", "lms"
    );

    @Transactional(readOnly = true)
    public PublicUserProfileResponse getPublicProfileByIdentifier(String identifier, String requesterEmail) {
        String cleanIdentifier = identifier.trim().toLowerCase();
        Optional<UserProfile> profileOpt = Optional.empty();
        Optional<User> userOpt = Optional.empty();

        // 1. Try finding by numeric user ID
        if (cleanIdentifier.matches("^\\d+$")) {
            Long userId = Long.parseLong(cleanIdentifier);
            userOpt = userRepository.findById(userId);
            if (userOpt.isPresent()) {
                profileOpt = userProfileRepository.findById(userId);
            }
        }

        // 2. Try finding by current alias
        if (profileOpt.isEmpty()) {
            profileOpt = userProfileRepository.findByAlias(cleanIdentifier);
            if (profileOpt.isPresent()) {
                userOpt = Optional.of(profileOpt.get().getUser());
            }
        }

        // 3. Try finding by old alias in history
        if (profileOpt.isEmpty()) {
            Optional<UserProfileAliasHistory> historyOpt = aliasHistoryRepository.findFirstByOldAliasOrderByCreatedAtDesc(cleanIdentifier);
            if (historyOpt.isPresent()) {
                Long historicalUserId = historyOpt.get().getUserId();
                userOpt = userRepository.findById(historicalUserId);
                if (userOpt.isPresent()) {
                    profileOpt = userProfileRepository.findById(historicalUserId);
                }
            }
        }

        if (userOpt.isEmpty()) {
            throw new ResourceNotFoundException("Người dùng không tồn tại: " + identifier);
        }

        User user = userOpt.get();
        UserProfile profile = profileOpt.orElseGet(() -> createDefaultProfile(user));

        boolean isOwner = requesterEmail != null && requesterEmail.equalsIgnoreCase(user.getEmail());

        // Protection Check
        if (!Boolean.TRUE.equals(profile.getPublished()) && !isOwner) {
            return PublicUserProfileResponse.builder()
                    .userId(user.getId())
                    .alias(profile.getAlias())
                    .published(false)
                    .message("Người dùng đã bảo vệ thông tin cá nhân.")
                    .fullName(user.getName())
                    .avatarUrl(user.getProfilePicture())
                    .allowDirectChat(profile.getAllowDirectChat())
                    .build();
        }

        Object parsedSections = parseJsonSafely(profile.getSectionsJson());
        Object parsedLayout = parseJsonSafely(profile.getLayoutConfigJson());
        Object parsedStats = parseJsonSafely(profile.getStatsCacheJson());

        return PublicUserProfileResponse.builder()
                .userId(user.getId())
                .alias(profile.getAlias())
                .published(profile.getPublished())
                .fullName(user.getName())
                .email(user.getEmail())
                .avatarUrl(user.getProfilePicture())
                .userType(user.getType())
                .organization(user.getOrganization())
                .title(profile.getTitle())
                .bio(profile.getBio())
                .sections(parsedSections)
                .layoutConfig(parsedLayout)
                .stats(parsedStats)
                .allowDirectChat(profile.getAllowDirectChat())
                .message(isOwner && !Boolean.TRUE.equals(profile.getPublished()) ? "(Chế độ xem trước - Profile chưa công khai)" : null)
                .build();
    }

    @Transactional
    public PublicUserProfileResponse getProfileConfig(String userEmail) {
        User user = userRepository.findByEmailForUpdate(userEmail)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userEmail));

        UserProfile profile = userProfileRepository.findById(user.getId())
                .orElseGet(() -> createDefaultProfile(user));

        return PublicUserProfileResponse.builder()
                .userId(user.getId())
                .alias(profile.getAlias())
                .published(profile.getPublished())
                .fullName(user.getName())
                .email(user.getEmail())
                .avatarUrl(user.getProfilePicture())
                .userType(user.getType())
                .organization(user.getOrganization())
                .title(profile.getTitle())
                .bio(profile.getBio())
                .sections(parseJsonSafely(profile.getSectionsJson()))
                .layoutConfig(parseJsonSafely(profile.getLayoutConfigJson()))
                .stats(parseJsonSafely(profile.getStatsCacheJson()))
                .allowDirectChat(profile.getAllowDirectChat())
                .build();
    }

    @Transactional
    public PublicUserProfileResponse updateProfileConfig(String userEmail, UserProfileConfigRequest request) {
        User user = userRepository.findByEmailForUpdate(userEmail)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userEmail));

        UserProfile profile = userProfileRepository.findById(user.getId())
                .orElseGet(() -> createDefaultProfile(user));

        // Alias Validation & History tracking
        if (request.getAlias() != null && !request.getAlias().isBlank()) {
            String newAlias = request.getAlias().trim().toLowerCase();
            if (!newAlias.equals(profile.getAlias())) {
                validateAlias(newAlias, user.getId());
                if (profile.getAlias() != null && !profile.getAlias().isBlank()) {
                    aliasHistoryRepository.save(UserProfileAliasHistory.builder()
                            .userId(user.getId())
                            .oldAlias(profile.getAlias())
                            .build());
                }
                profile.setAlias(newAlias);
            }
        }

        if (request.getPublished() != null) {
            profile.setPublished(request.getPublished());
        }

        if (request.getTitle() != null) {
            profile.setTitle(Jsoup.clean(request.getTitle(), Safelist.none()));
        }

        if (request.getBio() != null) {
            profile.setBio(Jsoup.clean(request.getBio(), Safelist.basicWithImages()));
        }

        if (request.getSectionsJson() != null) {
            profile.setSectionsJson(request.getSectionsJson());
        }

        if (request.getLayoutConfigJson() != null) {
            profile.setLayoutConfigJson(request.getLayoutConfigJson());
        }

        if (request.getAllowDirectChat() != null) {
            profile.setAllowDirectChat(request.getAllowDirectChat());
        }

        UserProfile saved = userProfileRepository.save(profile);
        log.info("Updated profile config for user: {} ({})", userEmail, saved.getAlias());

        return getProfileConfig(userEmail);
    }

    @Transactional(readOnly = true)
    public AliasCheckResponse checkAliasAvailability(String alias, String userEmail) {
        if (alias == null || alias.isBlank()) {
            return new AliasCheckResponse(false, alias, "Alias không được để trống");
        }
        String cleanAlias = alias.trim().toLowerCase();

        if (RESERVED_ALIASES.contains(cleanAlias)) {
            return new AliasCheckResponse(false, cleanAlias, "Alias này nằm trong danh sách hệ thống bảo lưu");
        }

        if (!ALIAS_PATTERN.matcher(cleanAlias).matches()) {
            return new AliasCheckResponse(false, cleanAlias, "Alias chỉ gồm chữ cái viết thường, số và dấu gạch ngang (-)");
        }

        User user = userEmail != null ? userRepository.findByEmail(userEmail).orElse(null) : null;
        Long currentUserId = user != null ? user.getId() : -1L;

        boolean exists = userProfileRepository.existsByAliasAndUserIdNot(cleanAlias, currentUserId);
        if (exists) {
            return new AliasCheckResponse(false, cleanAlias, "Alias đã được người dùng khác sử dụng");
        }

        return new AliasCheckResponse(true, cleanAlias, "Alias khả dụng");
    }

    @Transactional
    public void updateUserStatsCache(Long userId, String statsJson) {
        userProfileRepository.findById(userId).ifPresent(profile -> {
            profile.setStatsCacheJson(statsJson);
            userProfileRepository.save(profile);
            log.info("Updated stats cache for user ID: {}", userId);
        });
    }

    private void validateAlias(String alias, Long currentUserId) {
        if (RESERVED_ALIASES.contains(alias)) {
            throw new IllegalArgumentException("Alias '" + alias + "' thuộc danh sách từ khóa bảo lưu của hệ thống.");
        }
        if (!ALIAS_PATTERN.matcher(alias).matches()) {
            throw new IllegalArgumentException("Alias không hợp lệ. Chỉ chấp nhận chữ cái thường, số và dấu gạch ngang.");
        }
        if (userProfileRepository.existsByAliasAndUserIdNot(alias, currentUserId)) {
            throw new IllegalArgumentException("Alias '" + alias + "' đã được đăng ký bởi người dùng khác.");
        }
    }

    private UserProfile createDefaultProfile(User user) {
        String defaultAlias = "user-" + user.getId();

        String defaultSections = """
        [
          {
            "id": "sec_bio",
            "type": "BIO",
            "title": "Giới thiệu cá nhân",
            "visible": true,
            "order": 0,
            "items": []
          },
          {
            "id": "sec_academic",
            "type": "ACADEMIC",
            "title": "Học vấn & Bằng cấp",
            "visible": true,
            "order": 1,
            "items": []
          },
          {
            "id": "sec_experience",
            "type": "EXPERIENCE",
            "title": "Kinh nghiệm làm việc",
            "visible": true,
            "order": 2,
            "items": []
          },
          {
            "id": "sec_social",
            "type": "SOCIAL",
            "title": "Mạng xã hội & Liên hệ",
            "visible": true,
            "order": 3,
            "items": []
          }
        ]
        """;

        String defaultStats = """
        {
          "courses_enrolled": 0,
          "courses_completed": 0,
          "courses_created": 0,
          "total_learning_hours": 0
        }
        """;

        UserProfile newProfile = UserProfile.builder()
                .user(user)
                // @MapsId derives user_id from the managed User.  Setting it
                // explicitly makes JpaRepository choose merge() for a new
                // profile and Hibernate then fails with a null identifier.
                .alias(defaultAlias)
                .published(false)
                .title("Thành viên BDC Core")
                .bio("Chào mừng đến với trang cá nhân của tôi trên BDC Hub!")
                .sectionsJson(defaultSections)
                .statsCacheJson(defaultStats)
                .allowDirectChat(true)
                .build();

        return userProfileRepository.save(newProfile);
    }

    private Object parseJsonSafely(String json) {
        if (json == null || json.isBlank()) return null;
        try {
            return objectMapper.readValue(json, Object.class);
        } catch (JsonProcessingException e) {
            log.error("Failed to parse JSON content", e);
            return null;
        }
    }
}
