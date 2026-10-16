package com.example.demo.service.farm;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import javax.sql.DataSource;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.ArrayList;
import java.util.concurrent.Future;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="FARM_TEST_JDBC_URL", matches=".+")
class FarmRewardPostgresTest {
    @Configuration
    @EnableTransactionManagement
    static class Config {
        @Bean DataSource dataSource() {
            return new DriverManagerDataSource(System.getenv("FARM_TEST_JDBC_URL"), "farm_test", "farm_test");
        }
        @Bean JdbcTemplate jdbc(DataSource ds) { return new JdbcTemplate(ds); }
        @Bean PlatformTransactionManager transactionManager(DataSource ds) { return new DataSourceTransactionManager(ds); }
        @Bean FarmRewardService service(JdbcTemplate jdbc) { return new FarmRewardService(jdbc); }
    }
    @Test void duplicateConcurrentLateAndRollbackDelivery() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("CREATE TABLE IF NOT EXISTS users(id BIGINT PRIMARY KEY, total_score INTEGER, updated_at TIMESTAMPTZ)");
            jdbc.execute(Files.readString(Path.of("migrations/V20261017__farm_score_receipts.sql")));
            jdbc.execute("TRUNCATE users,farm_score_receipts");
            jdbc.update("INSERT INTO users(id,total_score) VALUES(41,100)");
            var service = context.getBean(FarmRewardService.class);
            var event = FarmRewardContractTest.fixture();
            try (var pool = Executors.newFixedThreadPool(8)) {
                var jobs = new ArrayList<Future<?>>();
                for (int i=0;i<20;i++) jobs.add(pool.submit(() -> service.apply(event)));
                // Simultaneous task-score increment must not be overwritten by farm rewards.
                jobs.add(pool.submit(() -> jdbc.update("UPDATE users SET total_score=total_score+10 WHERE id=41")));
                for (var job: jobs) job.get();
            }
            assertEquals(115, jdbc.queryForObject("SELECT total_score FROM users WHERE id=41", Integer.class));
            assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM farm_score_receipts", Integer.class));
            String missingId = UUID.randomUUID().toString();
            var missing = new FarmRewardEvent(1, missingId, missingId, 42, 5, event.occurredAt(), event.signature());
            assertThrows(IllegalStateException.class, () -> service.apply(missing));
            assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM farm_score_receipts", Integer.class));
            jdbc.update("INSERT INTO users(id,total_score) VALUES(42,0)");
            service.apply(missing); // delayed valid delivery can recover after user is available
            assertEquals(5, jdbc.queryForObject("SELECT total_score FROM users WHERE id=42", Integer.class));
        }
    }
}
