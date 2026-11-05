package com.example.demo.tenantsite;

import com.example.demo.tenantsite.controller.*;
import com.example.demo.tenantsite.service.TenantSiteService;
import com.example.demo.tenantsite.web.TenantSiteErrors;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.context.annotation.*;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.context.*;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.beans.factory.annotation.Autowired;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@ExtendWith(SpringExtension.class) @ContextConfiguration(classes = TenantSiteSecurityTest.Config.class) @WebAppConfiguration
class TenantSiteSecurityTest {
    @Configuration @EnableWebMvc @EnableMethodSecurity @org.springframework.security.config.annotation.web.configuration.EnableWebSecurity
    @Import({TenantSiteAdminController.class, TenantSitePublicController.class, TenantSiteErrors.class})
    static class Config {
        @Bean TenantSiteService service() { return mock(TenantSiteService.class); }
        @Bean SecurityFilterChain chain(HttpSecurity http) throws Exception {
            return http.csrf(c -> c.disable()).authorizeHttpRequests(a -> a.requestMatchers("/api/tenant-sites/**").permitAll().anyRequest().authenticated()).httpBasic(org.springframework.security.config.Customizer.withDefaults()).build();
        }
    }
    @Autowired WebApplicationContext context;
    @Autowired TenantSiteService service;
    MockMvc mvc;
    @BeforeEach void setup() { reset(service); mvc = MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build(); }
    @Test void writesRequireAuthenticatedGlobalAdmin() throws Exception {
        mvc.perform(get("/api/admin/organizations/9/site")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/admin/organizations/9/site").with(user("member").roles("USER"))).andExpect(status().isForbidden());
        when(service.editor(9L)).thenReturn(new TenantSiteService.Editor(0, null, null));
        mvc.perform(get("/api/admin/organizations/9/site").with(user("admin").roles("ADMIN"))).andExpect(status().isOk()).andExpect(jsonPath("revision").value(0));
        verify(service).editor(9L);
    }
    @Test void publicRouteHasNoDraftAndBadPayloadIs400() throws Exception {
        when(service.published("cce")).thenReturn(new TenantSiteService.Published(3, new com.fasterxml.jackson.databind.ObjectMapper().readTree("{}")));
        mvc.perform(get("/api/tenant-sites/cce")).andExpect(status().isOk()).andExpect(jsonPath("draft").doesNotExist()).andExpect(header().string("Cache-Control", "max-age=30, public"));
        mvc.perform(put("/api/admin/organizations/9/site").with(user("admin").roles("ADMIN")).contentType("application/json").content("{")) .andExpect(status().isBadRequest());
    }
}
