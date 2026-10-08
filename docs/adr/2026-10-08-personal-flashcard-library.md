# Personal flashcards within courses, independent of knowledge nodes

Status: accepted for implementation. Owner: LMS/AI teams.

Learners need a private library per course, usable for any subject. Node-bound generation and self-rating alone do not support this
workflow.

AI retains ownership of flashcard persistence, consistent with the existing
runtime. A new library schema separates decks, editable cards, reviews and jobs
from the old node records. V017 adds course scope without rewriting an already
applied V016; existing cards are split using their legacy course IDs. LMS remains the authenticated browser boundary;
learner identity and an authorized course scope are injected server-side. AI generation/checking runs in the existing
Kafka worker. Generated cards require an explicit user save.

Exact matching normalizes Unicode and whitespace and optionally case, while
preserving punctuation, accents, operators and digits. Authors can provide
alternative accepted answers or choose semantic checking. A malformed/failed
model verdict does not count as a review. Correct answers advance the existing
SM-2-style schedule; misses return in ten minutes. Card edits reset practice
progress and invalidate old revisions.

The UI provides explicit speech playback via browser voices. A managed cloud TTS
provider can be added later when a deployment has credentials and a cost policy;
this release does not claim identical voices across devices.

See [Data Platform](../DATA_PLATFORM.md#personal-flashcard-library) for the command
contract, migration and rollout order.
