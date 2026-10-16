package com.example.demo.service.farm;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;

@Service
@ConditionalOnProperty(name = "app.farm.rewards-enabled", havingValue = "true")
public class FarmRewardService {
    private final JdbcTemplate jdbc;
    public FarmRewardService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Transactional
    public void apply(FarmRewardEvent event) {
        int inserted = jdbc.update("""
                INSERT INTO farm_score_receipts(event_id,harvest_id,user_id,delta,occurred_at,applied_at)
                VALUES (?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING
                """, UUID.fromString(event.eventId()), UUID.fromString(event.harvestId()),
                event.userId(), event.delta(), Timestamp.from(Instant.parse(event.occurredAt())));
        if (inserted == 0) return;
        int updated = jdbc.update("""
                UPDATE users SET total_score=COALESCE(total_score,0)+?,updated_at=CURRENT_TIMESTAMP WHERE id=?
                """, event.delta(), event.userId());
        // Roll back the receipt too. Missing users / DB failures must not silently lose points.
        if (updated != 1) throw new IllegalStateException("Farm reward user not available");
    }
}
