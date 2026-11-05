package com.example.demo.tenantsite.model;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity @Table(name = "tenant_sites") @Getter @Setter @NoArgsConstructor
public class TenantSite {
    @Id @Column(name = "org_id") private Long orgId;
    private long revision;
    @Column(nullable = false, columnDefinition = "TEXT") private String draft;
    @Column(columnDefinition = "TEXT") private String published;
    private Instant publishedAt;
}
