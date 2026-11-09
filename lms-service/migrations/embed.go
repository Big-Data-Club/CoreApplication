package migrations

import _ "embed"

// LearningNotifications is the same additive, forward-only migration operators
// can apply manually. Startup installs it transactionally only if absent.
//
//go:embed V021__learning_notifications.sql
var LearningNotifications string
