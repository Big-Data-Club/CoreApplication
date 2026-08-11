package com.example.demo.dto.common;

import lombok.AllArgsConstructor;
import lombok.Getter;

import java.util.List;

/** Stable API shape for database-backed lists. */
@Getter
@AllArgsConstructor
public class PageResponse<T> {
    private final List<T> items;
    private final int page;
    private final int pageSize;
    private final long total;
    private final int totalPages;
    private final boolean hasNext;
}
