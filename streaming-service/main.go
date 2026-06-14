package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/segmentio/kafka-go"
)

// Define Prometheus metrics
var (
	eventsProcessedCounter = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "clickstream_events_processed_total",
			Help: "Total number of clickstream events successfully processed",
		},
		[]string{"event_type"},
	)
	eventsFailedCounter = prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "clickstream_events_failed_total",
			Help: "Total number of events that failed parsing or ingestion",
		},
	)
	kafkaWriteTimeHistogram = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "clickstream_kafka_write_duration_seconds",
			Help:    "Latency of writing event batches to Kafka",
			Buckets: prometheus.DefBuckets,
		},
	)
)

func init() {
	// Register metrics with Prometheus registry
	prometheus.MustRegister(eventsProcessedCounter)
	prometheus.MustRegister(eventsFailedCounter)
	prometheus.MustRegister(kafkaWriteTimeHistogram)
}

type ClickstreamBatchRequest struct {
	UserID int               `json:"userId"`
	Events []ClickstreamEvent `json:"events"`
}

type ClickstreamEvent struct {
	EventType     string                 `json:"event_type"`
	TargetElement string                 `json:"target_element"`
	PageURL       string                 `json:"page_url"`
	Timestamp     string                 `json:"timestamp"`
	Payload       map[string]interface{} `json:"payload"`
}

func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := c.Request.Header.Get("Origin")
		if origin != "" {
			c.Writer.Header().Set("Access-Control-Allow-Origin", origin)
		} else {
			c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		}
		c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Content-Length, Accept-Encoding, X-CSRF-Token, Authorization, accept, origin, Cache-Control, X-Requested-With")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	}
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8085"
	}

	kafkaBrokersStr := os.Getenv("KAFKA_BROKERS")
	if kafkaBrokersStr == "" {
		kafkaBrokersStr = "kafka:9092"
	}
	brokers := strings.Split(kafkaBrokersStr, ",")

	topic := os.Getenv("KAFKA_TOPIC")
	if topic == "" {
		topic = "clickstream.raw"
	}

	log.Printf("Starting Ingestion Gateway on port %s", port)
	log.Printf("Connecting to Kafka brokers: %v, Topic: %s", brokers, topic)

	// Configure Kafka Writer
	kafkaWriter := &kafka.Writer{
		Addr:         kafka.TCP(brokers...),
		Topic:        topic,
		Balancer:     &kafka.LeastBytes{},
		WriteTimeout: 10 * time.Second,
		RequiredAcks: kafka.RequireOne,
		Async:        true, // Async writing for sub-millisecond API response
	}
	defer kafkaWriter.Close()

	// Setup Gin
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	router.Use(gin.Recovery())
	router.Use(corsMiddleware())

	// Health Check
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "UP", "time": time.Now().Format(time.RFC3339)})
	})

	// Prometheus Metrics Endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Event Post Endpoint
	router.POST("/events/clickstream", func(c *gin.Context) {
		var req ClickstreamBatchRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			eventsFailedCounter.Inc()
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request payload: " + err.Error()})
			return
		}

		if len(req.Events) == 0 {
			c.JSON(http.StatusOK, gin.H{"status": "ignored", "message": "empty events list"})
			return
		}

		kafkaMessages := make([]kafka.Message, 0, len(req.Events))
		now := time.Now()

		for _, event := range req.Events {
			// Construct complete payload matching the Lakehouse ingestion schema
			payload := map[string]interface{}{
				"user_id":        req.UserID,
				"event_type":     event.EventType,
				"target_element": event.TargetElement,
				"page_url":       event.PageURL,
				"timestamp":      event.Timestamp,
				"payload":        event.Payload,
				"ingest_time":    now.Format(time.RFC3339),
			}

			eventBytes, err := json.Marshal(payload)
			if err != nil {
				eventsFailedCounter.Inc()
				log.Printf("Failed to marshal event payload: %v", err)
				continue
			}

			kafkaMessages = append(kafkaMessages, kafka.Message{
				Key:   []byte(fmt.Sprintf("%d", req.UserID)),
				Value: eventBytes,
			})
			
			// Increment event counters
			eventsProcessedCounter.WithLabelValues(event.EventType).Inc()
		}

		// Write to Kafka (Async)
		startKafka := time.Now()
		err := kafkaWriter.WriteMessages(context.Background(), kafkaMessages...)
		kafkaWriteTimeHistogram.Observe(time.Since(startKafka).Seconds())

		if err != nil {
			eventsFailedCounter.Add(float64(len(kafkaMessages)))
			log.Printf("Failed to publish messages to Kafka: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to publish events: " + err.Error()})
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"status": "success",
			"count":  len(kafkaMessages),
		})
	})

	srv := &http.Server{
		Addr:    ":" + port,
		Handler: router,
	}

	// Graceful shutdown setup
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Listen error: %s\n", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Shutting down Ingestion Gateway...")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Fatal("Server forced to shutdown:", err)
	}

	log.Println("Ingestion Gateway stopped cleanly.")
}
