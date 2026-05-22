package com.example.demo.service.admin;

import com.example.demo.exception.BadRequestException;
import com.example.demo.exception.ResourceNotFoundException;
import com.example.demo.model.Team;
import com.example.demo.model.UserTypeOption;
import com.example.demo.repository.TeamRepository;
import com.example.demo.repository.UserTypeOptionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class TeamAndTypeService {

    private final TeamRepository teamRepo;
    private final UserTypeOptionRepository typeRepo;

    // ── Teams CRUD ───────────────────────────────────────────────────────────

    public List<Team> listTeams() {
        return teamRepo.findAll();
    }

    @Transactional
    public Team createTeam(String code, String name, String description) {
        String cleanCode = code.trim().toUpperCase();
        if (teamRepo.existsByCode(cleanCode)) {
            throw new BadRequestException("Team with code " + cleanCode + " already exists.");
        }
        var team = Team.builder()
                .code(cleanCode)
                .name(name.trim())
                .description(description != null ? description.trim() : null)
                .build();
        log.info("Created team: {}", cleanCode);
        return teamRepo.save(team);
    }

    @Transactional
    public Team updateTeam(Long id, String name, String description) {
        var team = teamRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Team", id));
        if (name != null) team.setName(name.trim());
        if (description != null) team.setDescription(description.trim());
        log.info("Updated team ID: {}", id);
        return teamRepo.save(team);
    }

    @Transactional
    public void deleteTeam(Long id) {
        var team = teamRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Team", id));
        teamRepo.delete(team);
        log.info("Deleted team ID: {}", id);
    }

    // ── Types CRUD ───────────────────────────────────────────────────────────

    public List<UserTypeOption> listTypes() {
        return typeRepo.findAll();
    }

    @Transactional
    public UserTypeOption createType(String code, String name, String description) {
        String cleanCode = code.trim().toUpperCase();
        if (typeRepo.existsByCode(cleanCode)) {
            throw new BadRequestException("User type with code " + cleanCode + " already exists.");
        }
        var type = UserTypeOption.builder()
                .code(cleanCode)
                .name(name.trim())
                .description(description != null ? description.trim() : null)
                .build();
        log.info("Created user type: {}", cleanCode);
        return typeRepo.save(type);
    }

    @Transactional
    public UserTypeOption updateType(Long id, String name, String description) {
        var type = typeRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("UserTypeOption", id));
        if (name != null) type.setName(name.trim());
        if (description != null) type.setDescription(description.trim());
        log.info("Updated user type ID: {}", id);
        return typeRepo.save(type);
    }

    @Transactional
    public void deleteType(Long id) {
        var type = typeRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("UserTypeOption", id));
        typeRepo.delete(type);
        log.info("Deleted user type ID: {}", id);
    }
}
