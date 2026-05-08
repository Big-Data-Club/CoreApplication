package com.example.demo.service.user;

import com.example.demo.dto.auth.PasswordChangeRequest;
import com.example.demo.dto.user.UpdateUserRequest;
import com.example.demo.dto.user.UserResponse;
import com.example.demo.model.User;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

public interface UserService {

    List<UserResponse> getAllUsers();

    UserResponse getUserById(Long id);

    User getUserByEmail(String email);

    UserResponse updateUser(Long id, UpdateUserRequest request);

    UserResponse updateRole(Long id, String role);

    void changePassword(Long userId, String currentPassword, String newPassword);

    void requestPasswordChange(PasswordChangeRequest request);

    void confirmPasswordChange(String token, String newPassword);

    /** Gửi link đặt lại mật khẩu về email (không yêu cầu đăng nhập). */
    void forgotPassword(String email);

    /** Đặt lại mật khẩu bằng token từ email (không yêu cầu đăng nhập). */
    void resetPassword(String token, String newPassword);

    String uploadProfilePicture(Long userId, MultipartFile file);

    void deleteUser(Long id);

    UserResponse toggleActive(Long id);

    /** Get all users pending admin approval (Google OAuth registrations). */
    List<UserResponse> getPendingUsers();

    /** Approve a pending user: set active=true, pendingApproval=false, send welcome email. */
    UserResponse approveUser(Long id);

    /** Reject a pending user: set active=false, pendingApproval=false (blocked). */
    UserResponse rejectUser(Long id);
}
