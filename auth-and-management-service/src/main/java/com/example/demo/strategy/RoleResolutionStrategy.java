package com.example.demo.strategy;

import java.util.List;

public interface RoleResolutionStrategy {
    List<String> resolve(String role);
}