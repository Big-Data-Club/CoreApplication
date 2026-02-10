package com.example.demo.utils;

import org.springframework.data.domain.Sort;

public class SortUtils {

    // sortParams example: ["createdAt:desc", "title:asc"]
    public static Sort parseSort(String[] sortParams) {
        Sort sort = Sort.unsorted();
        if (sortParams != null) {
            for (String param : sortParams) {
                String[] parts = param.split(":");
                String field = parts[0];
                Sort.Direction direction = parts.length > 1 && parts[1].equalsIgnoreCase("desc")
                        ? Sort.Direction.DESC : Sort.Direction.ASC;
                sort = sort.and(Sort.by(direction, field));
            }
        }
        return sort;
    }
}
