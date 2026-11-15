package kafka

import "context"

type StatusUpdateFunc func(context.Context, ProcessDocumentStatusEvent) error
type NodeMergedFunc func(context.Context, NodeMergedEvent) error
type MicroInteractionFunc func(context.Context, MicroInteractionEvent) error
type AIJobStatusUpdateFunc func(context.Context, AIJobStatusEvent) error

func StartConsumer(ctx context.Context, handler StatusUpdateFunc) {
	runConsumer(ctx, "ai.document.processed.status", "lms-service-group", func(ctx context.Context, event ProcessDocumentStatusEvent) error { return handler(ctx, event) })
}
func StartNodeMergedConsumer(ctx context.Context, handler NodeMergedFunc) {
	runConsumer(ctx, "ai.graph.node_merged", "lms-service-graph-merged-group", func(ctx context.Context, event NodeMergedEvent) error { return handler(ctx, event) })
}
func StartMicroInteractionConsumer(ctx context.Context, handler MicroInteractionFunc) {
	runConsumer(ctx, TopicMicroInteractions, "lms-service-micro-interactions-group", func(ctx context.Context, event MicroInteractionEvent) error { return handler(ctx, event) })
}
func StartAIJobStatusConsumer(ctx context.Context, handler AIJobStatusUpdateFunc) {
	runConsumer(ctx, "ai.job.status", "lms-service-ai-job-status-group", func(ctx context.Context, event AIJobStatusEvent) error { return handler(ctx, event) })
}
