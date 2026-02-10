package com.example.demo.config;

import com.example.demo.enums.UserRole;
import com.example.demo.enums.UserTeam;
import com.example.demo.enums.UserType;
import com.example.demo.model.User;
import com.example.demo.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
@RequiredArgsConstructor
@Order(1)
public class DataInitializer implements CommandLineRunner {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    @Override
    public void run(String... args) throws Exception {

        if (userRepository.count() == 0) {
            if (userRepository.count() == 0) {
                User admin = User.builder()
                        .name("Nguyễn Phúc Nhân")
                        .email("phucnhan289@gmail.com")
                        .password(passwordEncoder.encode("hehehe"))
                        .role(UserRole.ROLE_ADMIN)
                        .team(UserTeam.RESEARCH)
                        .code("2312438")
                        .type(UserType.DT)
                        .totalScore(10000)
                        .active(true)
                        .build();

                userRepository.save(admin);

                System.out.println("Default users inserted: admin, manager, user");
            }
        }
    }
}