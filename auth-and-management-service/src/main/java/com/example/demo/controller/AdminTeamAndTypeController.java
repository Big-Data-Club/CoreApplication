package com.example.demo.controller;

import com.example.demo.model.Team;
import com.example.demo.model.UserTypeOption;
import com.example.demo.service.admin.TeamAndTypeService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class AdminTeamAndTypeController {

    private final TeamAndTypeService service;

    // ── Admin Teams CRUD ─────────────────────────────────────────────────────

    @GetMapping("/teams")
    public ResponseEntity<List<Team>> listTeams() {
        return ResponseEntity.ok(service.listTeams());
    }

    @PostMapping("/teams")
    public ResponseEntity<Team> createTeam(@RequestBody Map<String, String> body) {
        var team = service.createTeam(
                body.get("code"),
                body.get("name"),
                body.get("description"));
        return ResponseEntity.status(HttpStatus.CREATED).body(team);
    }

    @PutMapping("/teams/{id}")
    public ResponseEntity<Team> updateTeam(@PathVariable Long id,
                                           @RequestBody Map<String, String> body) {
        return ResponseEntity.ok(service.updateTeam(id, body.get("name"), body.get("description")));
    }

    @DeleteMapping("/teams/{id}")
    public ResponseEntity<Void> deleteTeam(@PathVariable Long id) {
        service.deleteTeam(id);
        return ResponseEntity.noContent().build();
    }

    // ── Admin Types CRUD ─────────────────────────────────────────────────────

    @GetMapping("/types")
    public ResponseEntity<List<UserTypeOption>> listTypes() {
        return ResponseEntity.ok(service.listTypes());
    }

    @PostMapping("/types")
    public ResponseEntity<UserTypeOption> createType(@RequestBody Map<String, String> body) {
        var type = service.createType(
                body.get("code"),
                body.get("name"),
                body.get("description"));
        return ResponseEntity.status(HttpStatus.CREATED).body(type);
    }

    @PutMapping("/types/{id}")
    public ResponseEntity<UserTypeOption> updateType(@PathVariable Long id,
                                                     @RequestBody Map<String, String> body) {
        return ResponseEntity.ok(service.updateType(id, body.get("name"), body.get("description")));
    }

    @DeleteMapping("/types/{id}")
    public ResponseEntity<Void> deleteType(@PathVariable Long id) {
        service.deleteType(id);
        return ResponseEntity.noContent().build();
    }
}
