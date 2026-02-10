import { useState, useCallback, useEffect } from 'react';

interface TutorialState {
  [key: string]: {
    viewed: boolean;
    lastViewedAt: string;
  };
}

const STORAGE_KEY = 'app_tutorials_state';

export const useTutorialManager = () => {
  const [tutorials, setTutorials] = useState<TutorialState>({});

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        setTutorials(JSON.parse(saved));
      } catch (error) {
        console.error('Error loading tutorials:', error);
      }
    }
  }, []);

  useEffect(() => {
    if (Object.keys(tutorials).length > 0) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(tutorials));
    }
  }, [tutorials]);

  const markTutorialAsViewed = useCallback((tutorialId: string) => {
    setTutorials((prev) => ({
      ...prev,
      [tutorialId]: {
        viewed: true,
        lastViewedAt: new Date().toISOString(),
      },
    }));
  }, []);

  const resetTutorial = useCallback((tutorialId: string) => {
    setTutorials((prev) => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [tutorialId]: _removed, ...rest } = prev;
      return rest;
    });
  }, []);

  const resetAllTutorials = useCallback(() => {
    setTutorials({});
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const isTutorialViewed = useCallback(
    (tutorialId: string) => {
      return tutorials[tutorialId]?.viewed || false;
    },
    [tutorials]
  );

  const shouldShowTutorial = useCallback(
    (tutorialId: string, alwaysShow?: boolean) => {
      if (alwaysShow) return true;
      return !isTutorialViewed(tutorialId);
    },
    [isTutorialViewed]
  );

  return {
    markTutorialAsViewed,
    resetTutorial,
    resetAllTutorials,
    isTutorialViewed,
    shouldShowTutorial,
    allTutorials: tutorials,
  };
};
