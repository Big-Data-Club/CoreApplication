import { useState, useCallback } from 'react';
import { TutorialStep } from '@/components/ui/TutorialGuide';

export const useTutorial = (steps: TutorialStep[]) => {
  const [showTutorial, setShowTutorial] = useState(false);

  const startTutorial = useCallback(() => {
    setShowTutorial(true);
  }, []);

  const endTutorial = useCallback(() => {
    setShowTutorial(false);
  }, []);

  return {
    showTutorial,
    startTutorial,
    endTutorial,
    steps,
  };
};
