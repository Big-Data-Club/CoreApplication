package com.example.demo.model;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

/** Durable Kafka inbox; insert and users.total_score increment share one transaction. */
@Entity
@Table(name = "farm_score_receipts", uniqueConstraints = @UniqueConstraint(columnNames = "harvest_id"))
public class FarmScoreReceipt {
    @Id
    @Column(name = "event_id")
    private UUID eventId;
    @Column(name = "harvest_id", nullable = false)
    private UUID harvestId;
    @Column(name = "user_id", nullable = false)
    private Long userId;
    @Column(nullable = false)
    private Integer delta;
    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;
    @Column(name = "applied_at", nullable = false)
    private Instant appliedAt;
    protected FarmScoreReceipt() {}
}
