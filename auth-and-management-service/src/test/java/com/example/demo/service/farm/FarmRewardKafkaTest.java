package com.example.demo.service.farm;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.autoconfigure.kafka.KafkaProperties;
import org.springframework.context.annotation.*;
import org.springframework.core.env.MapPropertySource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import javax.sql.DataSource;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="FARM_TEST_KAFKA_BROKERS", matches=".+")
class FarmRewardKafkaTest {
    static class Listener {
        final CountDownLatch deliveries = new CountDownLatch(5);
        final FarmRewardConsumer consumer;
        Listener(FarmRewardService service) {
            consumer = new FarmRewardConsumer(new ObjectMapper(), service, FarmRewardContractTest.SECRET);
        }
        @KafkaListener(topics="farm.harvest.reward.v1", groupId="auth-farm-rewards-test", containerFactory="farmRewardContainerFactory")
        public void receive(ConsumerRecord<String,String> record) throws Exception {
            consumer.consume(record);
            deliveries.countDown();
        }
    }
    @Configuration
    @EnableKafka
    @EnableTransactionManagement
    @Import(FarmKafkaConfiguration.class)
    static class Config {
        @Bean DataSource dataSource() {
            return new DriverManagerDataSource(System.getenv("FARM_TEST_JDBC_URL"),"farm_test","farm_test");
        }
        @Bean JdbcTemplate jdbc(DataSource ds) { return new JdbcTemplate(ds); }
        @Bean PlatformTransactionManager transactionManager(DataSource ds) { return new DataSourceTransactionManager(ds); }
        @Bean FarmRewardService service(JdbcTemplate jdbc) { return new FarmRewardService(jdbc); }
        @Bean Listener listener(FarmRewardService service) { return new Listener(service); }
        @Bean KafkaProperties kafkaProperties() {
            var properties = new KafkaProperties();
            properties.setBootstrapServers(List.of(System.getenv("FARM_TEST_KAFKA_BROKERS")));
            return properties;
        }
    }
    @Test void realBrokerDeliveryAndReplayCreditOnce() throws Exception {
        var ds = new DriverManagerDataSource(System.getenv("FARM_TEST_JDBC_URL"),"farm_test","farm_test");
        var jdbc = new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE IF NOT EXISTS users(id BIGINT PRIMARY KEY,total_score INTEGER,updated_at TIMESTAMPTZ)");
        jdbc.execute(Files.readString(Path.of("migrations/V20261017__farm_score_receipts.sql")));
        jdbc.execute("TRUNCATE users,farm_score_receipts");
        jdbc.update("INSERT INTO users(id,total_score) VALUES(41,100)");
        try (var context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("farm-test",Map.of("app.farm.rewards-enabled","true")));
            context.register(Config.class);
            context.refresh();
            Map<String,Object> properties = Map.of(
                    "bootstrap.servers",System.getenv("FARM_TEST_KAFKA_BROKERS"),
                    "key.serializer",StringSerializer.class,
                    "value.serializer",StringSerializer.class,
                    "acks","all");
            try (var producer = new KafkaProducer<String,String>(properties)) {
                var payload = new ObjectMapper().writeValueAsString(FarmRewardContractTest.fixture());
                for (int i=0;i<5;i++) producer.send(new ProducerRecord<>("farm.harvest.reward.v1","41",payload)).get(20,TimeUnit.SECONDS);
            }
            assertTrue(context.getBean(Listener.class).deliveries.await(40,TimeUnit.SECONDS),"broker deliveries not consumed");
            assertEquals(105,jdbc.queryForObject("SELECT total_score FROM users WHERE id=41",Integer.class));
            assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM farm_score_receipts",Integer.class));
        }
    }
}
