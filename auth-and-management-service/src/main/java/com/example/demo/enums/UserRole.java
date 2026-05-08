package com.example.demo.enums;

/**
 * Well-known role constants.
 *
 * Converted from enum to String constants so that roles are fully dynamic
 * (stored in the {@code roles} DB table) while keeping backward compatibility
 * with every call-site that references {@code UserRole.ROLE_ADMIN} etc.
 */
public final class UserRole {
    public static final String ROLE_ADMIN   = "ROLE_ADMIN";
    public static final String ROLE_MANAGER = "ROLE_MANAGER";
    public static final String ROLE_USER    = "ROLE_USER";

    private UserRole() {}
}
