"use client";
import React from "react";
import UserApp from "@/components/user/UserApp";
import TutorialGuide from '@/components/ui/TutorialGuide';
import { tutorialConfig } from '@/config/tutorials';

export default function Page() {
  return (
    <div id="users-page">
      <UserApp />
      <TutorialGuide 
        steps={tutorialConfig.users}
        onComplete={() => {}}
      />
    </div>
  );
}
