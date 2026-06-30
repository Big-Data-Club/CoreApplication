package com.example.demo.dto.org;

import lombok.*;
import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BulkAddMembersResponse {
    private List<String> added;
    private List<String> notFound;
}
