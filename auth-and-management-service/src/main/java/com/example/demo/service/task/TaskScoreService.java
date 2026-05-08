package com.example.demo.service.task;

import com.example.demo.dto.taskscore.TaskScoreRequest;
import com.example.demo.dto.taskscore.TaskScoreResponse;
import com.example.demo.enums.UserRole;
import com.example.demo.exception.ForbiddenException;
import com.example.demo.exception.ResourceNotFoundException;
import com.example.demo.model.Task;
import com.example.demo.model.TaskScore;
import com.example.demo.model.User;
import com.example.demo.repository.TaskRepository;
import com.example.demo.repository.TaskScoreRepository;
import com.example.demo.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * TaskScoreService - quản lý điểm số cho task assignees.
 *
 * Cải tiến:
 * - requireAdminOrManager() tập trung permission check, không lặp lại
 * - adjustUserScore() tập trung logic cộng/trừ totalScore, không lặp lại
 * - Lambda ngắn gọn trong initializeScores, applyScores
 * - Typed exceptions
 */
@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class TaskScoreService {

    private final TaskScoreRepository taskScoreRepo;
    private final TaskRepository taskRepo;
    private final UserRepository userRepo;

    private static final Set<String> PRIVILEGED = Set.of(UserRole.ROLE_ADMIN, UserRole.ROLE_MANAGER);

    // ── Reads ────────────────────────────────────────────────────────────────

    public TaskScoreResponse getScore(Long taskId, Long userId) {
        return mapToResponse(findScore(taskId, userId));
    }

    public List<TaskScoreResponse> getTaskScores(Long taskId) {
        requireTaskExists(taskId);
        return taskScoreRepo.findByTaskIdWithDetails(taskId).stream()
                .map(this::mapToResponse)
                .toList();
    }

    public List<TaskScoreResponse> getUserScores(Long userId) {
        return taskScoreRepo.findByUserId(userId).stream()
                .map(this::mapToResponse)
                .toList();
    }

    public Integer getTotalAppliedScore(Long userId) {
        Integer total = taskScoreRepo.getTotalAppliedScoreForUser(userId);
        return total != null ? total : 0;
    }

    // ── Writes ───────────────────────────────────────────────────────────────

    @Transactional
    public TaskScoreResponse setScore(TaskScoreRequest req, Long adminId) {
        var admin = requireAdminOrManager(adminId);
        var task  = findTask(req.getTaskId());
        var user  = findUser(req.getUserId());

        var score = taskScoreRepo.findByTaskIdAndUserId(req.getTaskId(), req.getUserId())
                .orElseGet(() -> TaskScore.builder().task(task).user(user).build());

        // Nếu đã applied: bù sự chênh lệch vào totalScore ngay lập tức
        if (Boolean.TRUE.equals(score.getApplied())) {
            int delta = req.getScore() - (score.getScore() != null ? score.getScore() : 0);
            adjustUserScore(user, delta);
        }

        score.setScore(req.getScore());
        score.setScoredBy(admin);
        score.setScoredAt(LocalDateTime.now());
        score.setNotes(req.getNotes());

        return mapToResponse(taskScoreRepo.save(score));
    }

    @Transactional
    public TaskScoreResponse deductScore(Long taskId, Long userId, int amount, String reason, Long adminId) {
        var admin = requireAdminOrManager(adminId);
        var user  = findUser(userId);
        var score = findScore(taskId, userId);

        int newScore = Math.max(0, score.getScore() - amount); // điểm không âm
        if (Boolean.TRUE.equals(score.getApplied())) {
            adjustUserScore(user, newScore - score.getScore());
        }

        score.setScore(newScore);
        score.setScoredBy(admin);
        score.setScoredAt(LocalDateTime.now());
        score.setNotes("Deducted: " + reason);

        log.info("Deducted {} pts from user {} on task {}", amount, userId, taskId);
        return mapToResponse(taskScoreRepo.save(score));
    }

    @Transactional
    public List<TaskScoreResponse> applyScoresToTask(Long taskId, Long adminId) {
        requireAdminOrManager(adminId);
        requireTaskExists(taskId);

        var now = LocalDateTime.now();
        var pending = taskScoreRepo.findByTaskIdAndAppliedFalse(taskId)
                .stream()
                .filter(s -> s.getScore() > 0)
                .toList();

        if (pending.isEmpty()) return getTaskScores(taskId);

        pending.forEach(s -> {
            s.setApplied(true);
            s.setAppliedAt(now);
        });
        taskScoreRepo.saveAll(pending);

        var userScoreDeltas = pending.stream()
                .collect(Collectors.groupingBy(
                    s -> s.getUser().getId(),
                    Collectors.summingInt(TaskScore::getScore)
                ));
        
        var users = userRepo.findAllById(userScoreDeltas.keySet());
        users.forEach(u -> u.setTotalScore(
            u.getTotalScore() + userScoreDeltas.get(u.getId())
        ));
        userRepo.saveAll(users);

        log.info("Applied scores to {} users for task {}", pending.size(), taskId);
        return taskScoreRepo.findByTaskId(taskId).stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Transactional
    public TaskScoreResponse toggleApplyScore(Long taskId, Long userId, boolean apply, Long adminId) {
        requireAdminOrManager(adminId);
        var score = findScore(taskId, userId);

        if (apply && !Boolean.TRUE.equals(score.getApplied())) {
            adjustUserScore(score.getUser(), score.getScore());
            score.setApplied(true);
            score.setAppliedAt(LocalDateTime.now());
        } else if (!apply && Boolean.TRUE.equals(score.getApplied())) {
            adjustUserScore(score.getUser(), -score.getScore());
            score.setApplied(false);
            score.setAppliedAt(null);
        }

        return mapToResponse(taskScoreRepo.save(score));
    }

    @Transactional
    public void deleteScore(Long taskId, Long userId, Long adminId) {
        requireAdminOrManager(adminId);
        var score = findScore(taskId, userId);

        if (Boolean.TRUE.equals(score.getApplied()) && score.getScore() > 0) {
            adjustUserScore(score.getUser(), -score.getScore());
        }
        taskScoreRepo.delete(score);
    }

    @Transactional
    public List<TaskScoreResponse> initializeScoresForTask(Long taskId, int initialScore, Long adminId) {
        var admin = requireAdminOrManager(adminId);
        var task = findTask(taskId);

        var existingUserIds = taskScoreRepo.findByTaskId(taskId).stream()
                .map(s -> s.getUser().getId())
                .collect(Collectors.toSet());

        var newScores = task.getAssignees().stream()
                .filter(ut -> !existingUserIds.contains(ut.getUser().getId()))
                .map(ut -> TaskScore.builder()
                        .task(task)
                        .user(ut.getUser())
                        .score(initialScore)
                        .scoredBy(admin)
                        .scoredAt(LocalDateTime.now())
                        .applied(false)
                        .build())
                .toList();

        if (!newScores.isEmpty()) {
            taskScoreRepo.saveAll(newScores);
        }

        return taskScoreRepo.findByTaskId(taskId).stream()
                .map(this::mapToResponse)
                .toList();
    }

    @Transactional
    public List<TaskScoreResponse> completeTaskAndApplyScores(Long taskId, Long adminId) {
        requireAdminOrManager(adminId);
        var task = findTask(taskId);
        task.setColumnId("done");
        taskRepo.save(task);
        return applyScoresToTask(taskId, adminId);
    }

    // ── Private helpers ──────────────────────────────────────────────────────

    /**
     * Cộng/trừ điểm vào totalScore, save ngay - không cần load user lại.
     */
    private void adjustUserScore(User user, int delta) {
        user.setTotalScore((user.getTotalScore() != null ? user.getTotalScore() : 0) + delta);
        userRepo.save(user);
    }

    private User requireAdminOrManager(Long userId) {
        var user = findUser(userId);
        if (!PRIVILEGED.contains(user.getRole())) {
            throw new ForbiddenException("Only ADMIN or MANAGER can manage task scores");
        }
        return user;
    }

    private TaskScore findScore(Long taskId, Long userId) {
        return taskScoreRepo.findByTaskIdAndUserId(taskId, userId)
                .orElseThrow(() -> new ResourceNotFoundException(
                    "Score not found for task " + taskId + " and user " + userId));
    }

    private Task findTask(Long id) {
        return taskRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Task", id));
    }

    private User findUser(Long id) {
        return userRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("User", id));
    }

    private void requireTaskExists(Long taskId) {
        if (!taskRepo.existsById(taskId)) {
            throw new ResourceNotFoundException("Task", taskId);
        }
    }

    private TaskScoreResponse mapToResponse(TaskScore s) {
        return TaskScoreResponse.builder()
                .id(s.getId())
                .taskId(s.getTask().getId())
                .taskTitle(s.getTask().getTitle())
                .userId(s.getUser().getId())
                .userName(s.getUser().getName())
                .userEmail(s.getUser().getEmail())
                .userCode(s.getUser().getCode())
                .score(s.getScore())
                .applied(s.getApplied())
                .scoredById(s.getScoredBy() != null ? s.getScoredBy().getId() : null)
                .scoredByName(s.getScoredBy() != null ? s.getScoredBy().getName() : null)
                .scoredAt(s.getScoredAt())
                .appliedAt(s.getAppliedAt())
                .notes(s.getNotes())
                .build();
    }
}