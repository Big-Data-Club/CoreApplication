"""
Mastery Engine - Rule-based mastery calculation for skill states.

This module calculates student mastery scores based on learning events.
MVP uses deterministic rules; can be replaced with ML (BKT, DKT) later.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import math


class MasteryEngine:
    """
    Rule-based mastery calculation engine.

    Formula:
    mastery = (accuracy × difficulty_adjustment)
              - hint_penalty
              - repeated_failure_penalty
              + recency_boost
    """

    def __init__(self):
        # Configuration
        self.min_attempts_for_confidence = 10
        self.recency_decay_days = 7
        self.difficulty_weight = 0.3
        self.hint_penalty_weight = 0.2
        self.failure_penalty_max = 0.3
        self.recency_boost_max = 0.1

    def calculate_mastery(
        self,
        events: List[Dict],
        current_state: Optional[Dict] = None
    ) -> Dict:
        """
        Calculate mastery score based on learning events.

        Args:
            events: List of learning event dictionaries
            current_state: Optional current skill state for incremental updates

        Returns:
            Dictionary with mastery metrics:
            {
                'mastery_score': float,           # 0-1
                'confidence_score': float,         # 0-1
                'accuracy': float,                 # 0-1
                'attempt_count': int,
                'avg_response_time_ms': int,
                'hint_dependency': float,          # 0-1
                'recommended_difficulty': float,   # 0-1
                'last_practiced_at': datetime
            }
        """
        if not events:
            return self._default_state()

        # Sort events by timestamp
        events = sorted(events, key=lambda e: e.get('created_at', datetime.now()))

        # Calculate basic metrics
        correct_count = sum(1 for e in events if e.get('correct') is True)
        incorrect_count = sum(1 for e in events if e.get('correct') is False)
        total_attempts = correct_count + incorrect_count

        if total_attempts == 0:
            return self._default_state()

        accuracy = correct_count / total_attempts

        # Calculate hint dependency
        hint_events = sum(e.get('hint_count', 0) or 0 for e in events)
        hint_dependency = min(1.0, hint_events / max(1, total_attempts))

        # Calculate average response time
        response_times = [
            e.get('response_time_ms')
            for e in events
            if e.get('response_time_ms') is not None
        ]
        avg_response_time = int(sum(response_times) / len(response_times)) if response_times else 0

        # Difficulty adjustment
        difficulties = [e.get('difficulty', 0.5) for e in events if e.get('difficulty') is not None]
        avg_difficulty = sum(difficulties) / len(difficulties) if difficulties else 0.5
        difficulty_adjustment = 1.0 + (avg_difficulty - 0.5) * self.difficulty_weight

        # Hint penalty
        hint_penalty = hint_dependency * self.hint_penalty_weight

        # Repeated failure penalty (check recent 5 attempts)
        recent_events = events[-5:]
        recent_failures = sum(1 for e in recent_events if e.get('correct') is False)
        failure_penalty = min(recent_failures * 0.1, self.failure_penalty_max)

        # Recency boost
        last_event_time = events[-1].get('created_at')
        if isinstance(last_event_time, str):
            last_event_time = datetime.fromisoformat(last_event_time.replace('Z', '+00:00'))

        days_since = (datetime.now(last_event_time.tzinfo if last_event_time.tzinfo else None) - last_event_time).days
        recency_boost = self.recency_boost_max * math.exp(-days_since / self.recency_decay_days)

        # Calculate mastery score
        base_mastery = accuracy * difficulty_adjustment
        mastery_score = max(0.0, min(1.0,
            base_mastery - hint_penalty - failure_penalty + recency_boost
        ))

        # Confidence based on sample size
        confidence_score = min(1.0, total_attempts / self.min_attempts_for_confidence)

        # Recommended difficulty based on mastery level
        recommended_difficulty = self._calculate_recommended_difficulty(
            mastery_score, avg_difficulty, accuracy, hint_dependency
        )

        return {
            'mastery_score': round(mastery_score, 3),
            'confidence_score': round(confidence_score, 3),
            'accuracy': round(accuracy, 3),
            'attempt_count': total_attempts,
            'avg_response_time_ms': avg_response_time,
            'hint_dependency': round(hint_dependency, 3),
            'recommended_difficulty': round(recommended_difficulty, 2),
            'last_practiced_at': last_event_time
        }

    def _calculate_recommended_difficulty(
        self,
        mastery_score: float,
        current_difficulty: float,
        accuracy: float,
        hint_dependency: float
    ) -> float:
        """
        Calculate recommended difficulty for next content.

        Rules:
        - mastery < 0.3 → easier content (remedial)
        - 0.3-0.6 → similar difficulty (practice)
        - 0.6-0.8 → slightly harder (advancing)
        - > 0.8 → harder (mastered, advance)

        Additional adjustments:
        - high accuracy + fast → increase more
        - low accuracy + many hints → decrease more
        """
        base_difficulty = current_difficulty

        if mastery_score < 0.3:
            # Struggling - need easier content
            adjustment = -0.2
            if hint_dependency > 0.5:
                adjustment -= 0.1  # Even easier if using many hints
        elif mastery_score < 0.6:
            # Developing - maintain similar difficulty
            adjustment = 0.0
            if accuracy < 0.5:
                adjustment = -0.1
        elif mastery_score < 0.8:
            # Advancing - slightly harder
            adjustment = 0.1
            if accuracy > 0.8 and hint_dependency < 0.2:
                adjustment = 0.15  # Confident, advance faster
        else:
            # Mastered - significantly harder
            adjustment = 0.2
            if accuracy > 0.9 and hint_dependency < 0.1:
                adjustment = 0.25  # Very confident, advance more

        recommended = base_difficulty + adjustment
        return max(0.1, min(1.0, recommended))

    def _default_state(self) -> Dict:
        """Return default state for students with no events."""
        return {
            'mastery_score': 0.0,
            'confidence_score': 0.0,
            'accuracy': 0.0,
            'attempt_count': 0,
            'avg_response_time_ms': 0,
            'hint_dependency': 0.0,
            'recommended_difficulty': 0.3,  # Start with easier content
            'last_practiced_at': None
        }

    def get_mastery_level(self, mastery_score: float) -> str:
        """
        Get human-readable mastery level.

        Returns: 'struggling', 'developing', 'advancing', or 'mastered'
        """
        if mastery_score < 0.3:
            return 'struggling'
        elif mastery_score < 0.6:
            return 'developing'
        elif mastery_score < 0.8:
            return 'advancing'
        else:
            return 'mastered'

    def should_review(
        self,
        mastery_score: float,
        last_practiced_at: Optional[datetime],
        days_threshold: int = 7
    ) -> bool:
        """
        Determine if skill needs spaced review.

        Args:
            mastery_score: Current mastery score (0-1)
            last_practiced_at: Last practice timestamp
            days_threshold: Days since last practice to trigger review

        Returns:
            True if skill should be reviewed
        """
        if last_practiced_at is None:
            return False

        if mastery_score >= 0.8:
            # Mastered skills need spaced review
            days_since = (datetime.now(last_practiced_at.tzinfo) - last_practiced_at).days
            return days_since >= days_threshold

        return False


# Global instance
mastery_engine = MasteryEngine()
