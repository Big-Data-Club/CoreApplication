package com.example.demo.tenantsite.web;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class TenantSiteRateLimitTest {
    @Test void throttlesAndResetsWithBoundedKeys() {
        var filter = new TenantSiteRateLimitFilter();
        assertTrue(filter.allow("user", 2, 1)); assertTrue(filter.allow("user", 2, 1));
        assertFalse(filter.allow("user", 2, 1)); assertTrue(filter.allow("user", 2, 2));
        for (int i = 0; i < 9999; i++) assertTrue(filter.allow("ip" + i, 2, 2));
        assertFalse(filter.allow("new-ip", 2, 2)); assertTrue(filter.allow("new-ip", 2, 3));
    }
}
