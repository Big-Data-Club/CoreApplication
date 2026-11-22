package migrations

import _ "embed"

// LearningNotifications is the same additive, forward-only migration operators
// can apply manually. Startup installs it transactionally only if absent.
//
//go:embed releases/2026-11/V021__learning_notifications.sql
var LearningNotifications string

//go:embed releases/2026-11/V023__always_publish_learning_resources.sql
var AlwaysPublishLearningResources string
