package com.example.demo.service.farm;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class FarmRewardContractTest {
    static final String SECRET = "farm-contract-test-secret-32-bytes";
    static FarmRewardEvent fixture() throws Exception {
        return new ObjectMapper().readValue(FarmRewardContractTest.class.getResourceAsStream("/farm-reward-v1.json"), FarmRewardEvent.class);
    }
    @Test void acceptsGoSignatureAndAdditiveFields() throws Exception {
        fixture().validate(SECRET, "41");
    }
    @Test void rejectsTamperingWrongKeyAndSchema() throws Exception {
        var e = fixture();
        assertThrows(IllegalArgumentException.class, () -> e.validate(SECRET, "42"));
        assertThrows(IllegalArgumentException.class, () -> e.validate("different-key", "41"));
        assertThrows(IllegalArgumentException.class, () -> new FarmRewardEvent(2,e.eventId(),e.harvestId(),41,5,e.occurredAt(),e.signature()).validate(SECRET,"41"));
        assertThrows(IllegalArgumentException.class, () -> new FarmRewardEvent(1,e.eventId(),e.harvestId(),41,50,e.occurredAt(),e.signature()).validate(SECRET,"41"));
    }
    @Test void consumerDoesNotSwallowDatabaseFailure() throws Exception {
        var mapper = new ObjectMapper();
        var service = mock(FarmRewardService.class);
        doThrow(new IllegalStateException("database offline")).when(service).apply(any());
        var consumer = new FarmRewardConsumer(mapper, service, SECRET);
        var record = new ConsumerRecord<String,String>("farm.harvest.reward.v1",0,1,"41",mapper.writeValueAsString(fixture()));
        assertThrows(IllegalStateException.class, () -> consumer.consume(record));
    }
    @Test void invalidSignatureNeverReachesScoreService() throws Exception {
        var mapper = new ObjectMapper();
        var service = mock(FarmRewardService.class);
        var consumer = new FarmRewardConsumer(mapper, service, SECRET);
        assertThrows(IllegalArgumentException.class, () -> consumer.consume(new ConsumerRecord<>("farm.harvest.reward.v1",0,1,"42",mapper.writeValueAsString(fixture()))));
        verifyNoInteractions(service);
    }
    @Test void receiptDuplicateDoesNotUpdateUser() throws Exception {
        var jdbc = mock(JdbcTemplate.class);
        new FarmRewardService(jdbc).apply(fixture());
        verify(jdbc, times(1)).update(anyString(), any(Object[].class));
    }
}
