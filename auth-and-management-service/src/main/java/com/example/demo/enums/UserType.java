package com.example.demo.enums;

/**
 * Well-known type constants.
 *
 * Converted from enum to String constants so that types are fully dynamic
 * (no database check-constraint) while keeping backward compatibility
 * with every call-site that references {@code UserType.CLC} etc.
 */
public final class UserType {
    public static final String CLC = "CLC";
    public static final String TN  = "TN";
    public static final String DT  = "DT";

    private UserType() {}
}
