package com.example.demo.repository;

import com.example.demo.model.Organization;
import com.example.demo.model.OrganizationMember;
import com.example.demo.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

public interface OrganizationMemberRepository extends JpaRepository<OrganizationMember, Long> {
    List<OrganizationMember> findByUser(User user);
    List<OrganizationMember> findByOrganization(Organization org);
    Optional<OrganizationMember> findByOrganizationAndUser(Organization org, User user);
    boolean existsByOrganizationAndUser(Organization org, User user);
    void deleteByOrganizationAndUser(Organization org, User user);
}
