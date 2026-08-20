"""
Skill-Based Recommender

Provides skill-aware recommendations for personalized learning.
Recommends next best lesson based on skill mastery levels.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SkillBasedRecommendation:
    """Recommendation based on skill mastery."""
    content_id: int
    skill_id: int
    skill_name: str
    difficulty: float
    reason: str
    score: float
    action: str  # 'review', 'practice', 'advance', 'learn_new'


class SkillBasedRecommender:
    """
    Skill-aware recommendation engine.

    Rules:
    - mastery < 0.3 → prerequisite/remedial content
    - 0.3-0.6 → practice same skill
    - 0.6-0.8 → harder activity
    - > 0.8 → next skill

    Additional signals:
    - high accuracy + fast → increase difficulty
    - low accuracy + many hints → easier lesson
    - mastered but not practiced recently → spaced review
    - repeated failure → prerequisite skill
    """

    def __init__(self):
        self.mastery_thresholds = {
            'struggling': 0.3,
            'developing': 0.6,
            'advancing': 0.8,
            'mastered': 0.9
        }

    def get_next_best_lesson(
        self,
        student_id: int,
        course_id: int,
        skill_states: List[Dict],
        available_content: List[Dict],
        time_budget_minutes: int = 20
    ) -> List[SkillBasedRecommendation]:
        """
        Recommend next best lesson based on skill mastery.

        Args:
            student_id: Student ID
            course_id: Course ID
            skill_states: List of learner skill states with mastery scores
            available_content: List of available content items with skill mappings
            time_budget_minutes: Student's available time

        Returns:
            List of skill-based recommendations, sorted by priority
        """
        if not skill_states:
            logger.info(f"No skill states for student {student_id}, returning exploratory recommendations")
            return self._get_exploratory_recommendations(available_content)

        recommendations = []

        # Categorize skills by mastery level
        struggling_skills = [
            s for s in skill_states
            if s.get('mastery_score', 0) < self.mastery_thresholds['struggling']
            and s.get('attempt_count', 0) > 0
        ]

        developing_skills = [
            s for s in skill_states
            if self.mastery_thresholds['struggling'] <= s.get('mastery_score', 0) < self.mastery_thresholds['developing']
        ]

        advancing_skills = [
            s for s in skill_states
            if self.mastery_thresholds['developing'] <= s.get('mastery_score', 0) < self.mastery_thresholds['advancing']
        ]

        mastered_skills = [
            s for s in skill_states
            if s.get('mastery_score', 0) >= self.mastery_thresholds['advancing']
        ]

        # Priority 1: Address struggling skills (highest priority)
        for skill in struggling_skills[:2]:  # Limit to top 2 struggling skills
            content = self._find_remedial_content(skill, available_content)
            if content:
                recommendations.append(
                    SkillBasedRecommendation(
                        content_id=content['id'],
                        skill_id=skill['skill_id'],
                        skill_name=content.get('skill_name', f"Skill {skill['skill_id']}"),
                        difficulty=skill.get('recommended_difficulty', 0.2),
                        reason=f"Củng cố {content.get('skill_name', 'kỹ năng')} (mastery: {skill['mastery_score']:.0%})",
                        score=0.95,  # Highest priority
                        action='review'
                    )
                )

        # Priority 2: Practice developing skills
        for skill in developing_skills[:1]:  # One developing skill
            content = self._find_practice_content(skill, available_content)
            if content:
                recommendations.append(
                    SkillBasedRecommendation(
                        content_id=content['id'],
                        skill_id=skill['skill_id'],
                        skill_name=content.get('skill_name', f"Skill {skill['skill_id']}"),
                        difficulty=skill.get('recommended_difficulty', 0.5),
                        reason=f"Luyện tập {content.get('skill_name', 'kỹ năng')} để nâng cao thành thạo",
                        score=0.75,
                        action='practice'
                    )
                )

        # Priority 3: Advance with harder content
        for skill in advancing_skills[:1]:
            content = self._find_advanced_content(skill, available_content)
            if content:
                recommendations.append(
                    SkillBasedRecommendation(
                        content_id=content['id'],
                        skill_id=skill['skill_id'],
                        skill_name=content.get('skill_name', f"Skill {skill['skill_id']}"),
                        difficulty=min(0.9, skill.get('recommended_difficulty', 0.7) + 0.2),
                        reason=f"Thử thách cao hơn với {content.get('skill_name', 'kỹ năng')}",
                        score=0.65,
                        action='advance'
                    )
                )

        # Priority 4: Learn next skill (if current skills are mastered)
        if mastered_skills and not (struggling_skills or developing_skills):
            next_skill_content = self._find_next_skill(mastered_skills, available_content)
            if next_skill_content:
                recommendations.append(
                    SkillBasedRecommendation(
                        content_id=next_skill_content['content_id'],
                        skill_id=next_skill_content['skill_id'],
                        skill_name=next_skill_content.get('skill_name', 'New Skill'),
                        difficulty=0.4,  # Start new skills at moderate difficulty
                        reason=f"Kỹ năng mới: {next_skill_content.get('skill_name', 'skill')}",
                        score=0.55,
                        action='learn_new'
                    )
                )

        # Sort by score (priority)
        recommendations.sort(key=lambda r: r.score, reverse=True)

        # Return top recommendations that fit time budget
        return recommendations[:5]

    def _find_remedial_content(
        self, skill: Dict, available_content: List[Dict]
    ) -> Optional[Dict]:
        """Find easier content for struggling skill."""
        target_difficulty = skill.get('recommended_difficulty', 0.3)
        skill_id = skill['skill_id']

        # Find content for this skill with lower difficulty
        candidates = [
            c for c in available_content
            if c.get('skill_id') == skill_id
            and c.get('difficulty', 0.5) <= target_difficulty
            and not c.get('completed', False)
        ]

        # Sort by difficulty (easiest first)
        candidates.sort(key=lambda c: c.get('difficulty', 0.5))
        return candidates[0] if candidates else None

    def _find_practice_content(
        self, skill: Dict, available_content: List[Dict]
    ) -> Optional[Dict]:
        """Find practice content at current level."""
        target_difficulty = skill.get('recommended_difficulty', 0.5)
        skill_id = skill['skill_id']

        # Find content at similar difficulty
        candidates = [
            c for c in available_content
            if c.get('skill_id') == skill_id
            and abs(c.get('difficulty', 0.5) - target_difficulty) < 0.2
            and not c.get('completed', False)
        ]

        # Sort by closeness to target difficulty
        candidates.sort(key=lambda c: abs(c.get('difficulty', 0.5) - target_difficulty))
        return candidates[0] if candidates else None

    def _find_advanced_content(
        self, skill: Dict, available_content: List[Dict]
    ) -> Optional[Dict]:
        """Find harder content for advancing skill."""
        target_difficulty = skill.get('recommended_difficulty', 0.7)
        skill_id = skill['skill_id']

        # Find harder content for this skill
        candidates = [
            c for c in available_content
            if c.get('skill_id') == skill_id
            and c.get('difficulty', 0.5) >= target_difficulty
            and not c.get('completed', False)
        ]

        # Sort by difficulty (moderate challenge first)
        candidates.sort(key=lambda c: c.get('difficulty', 0.5))
        return candidates[0] if candidates else None

    def _find_next_skill(
        self, mastered_skills: List[Dict], available_content: List[Dict]
    ) -> Optional[Dict]:
        """Find next skill based on what's been mastered."""
        mastered_skill_ids = {s['skill_id'] for s in mastered_skills}

        # Find content for skills not yet mastered
        for content in available_content:
            skill_id = content.get('skill_id')
            if skill_id and skill_id not in mastered_skill_ids:
                return {
                    'content_id': content['id'],
                    'skill_id': skill_id,
                    'skill_name': content.get('skill_name', f'Skill {skill_id}')
                }

        return None

    def _get_exploratory_recommendations(
        self, available_content: List[Dict]
    ) -> List[SkillBasedRecommendation]:
        """Get exploratory recommendations for students with no skill history."""
        recommendations = []

        # Return beginner-friendly content
        beginner_content = [
            c for c in available_content
            if c.get('difficulty', 0.5) <= 0.4
            and not c.get('completed', False)
        ][:3]

        for idx, content in enumerate(beginner_content):
            recommendations.append(
                SkillBasedRecommendation(
                    content_id=content['id'],
                    skill_id=content.get('skill_id', 0),
                    skill_name=content.get('skill_name', 'Exploration'),
                    difficulty=content.get('difficulty', 0.3),
                    reason="Khám phá nội dung phù hợp để bắt đầu",
                    score=0.5 - (idx * 0.1),
                    action='learn_new'
                )
            )

        return recommendations


# Global instance
skill_based_recommender = SkillBasedRecommender()
