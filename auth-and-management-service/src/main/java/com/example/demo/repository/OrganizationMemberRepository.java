package com.example.demo.repository;

import com.example.demo.model.Organization;
import com.example.demo.model.OrganizationMember;
import com.example.demo.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface OrganizationMemberRepository extends JpaRepository<OrganizationMember, Long> {
    List<OrganizationMember> findByUser(User user);
    List<OrganizationMember> findByOrganization(Organization org);
    Optional<OrganizationMember> findByOrganizationAndUser(Organization org, User user);
    boolean existsByOrganizationAndUser(Organization org, User user);
    void deleteByOrganizationAndUser(Organization org, User user);

    interface UserOrganizationName {
        Long getUserId();
        String getOrganizationName();
    }

    @Query("""
        select om.user.id as userId, om.organization.name as organizationName
        from OrganizationMember om
        where om.user.id in :userIds
        order by om.user.id, om.organization.name
        """)
    List<UserOrganizationName> findOrganizationNamesByUserIds(@Param("userIds") Collection<Long> userIds);
}
