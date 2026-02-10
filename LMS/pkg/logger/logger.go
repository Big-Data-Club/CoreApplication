package logger

import (
	"fmt"
	"log"
	"os"
)

var (
	infoLogger  *log.Logger
	warnLogger  *log.Logger
	errorLogger *log.Logger
)

// Init initializes the logger
func Init(env string) {
	infoLogger = log.New(os.Stdout, "INFO: ", log.Ldate|log.Ltime|log.Lshortfile)
	warnLogger = log.New(os.Stdout, "WARN: ", log.Ldate|log.Ltime|log.Lshortfile)
	errorLogger = log.New(os.Stderr, "ERROR: ", log.Ldate|log.Ltime|log.Lshortfile)
}

// Info logs informational messages
func Info(message string) {
	if infoLogger != nil {
		infoLogger.Println(message)
	}
}

// InfoWithFields logs informational messages with fields
func InfoWithFields(message string, fields map[string]interface{}) {
	if infoLogger != nil {
		infoLogger.Printf("%s - %v", message, fields)
	}
}

// Warn logs warning messages
func Warn(message string) {
	if warnLogger != nil {
		warnLogger.Println(message)
	}
}

// WarnWithFields logs warning messages with fields
func WarnWithFields(message string, fields map[string]interface{}) {
	if warnLogger != nil {
		warnLogger.Printf("%s - %v", message, fields)
	}
}

// Error logs error messages
func Error(message string, err error) {
	if errorLogger != nil {
		errorLogger.Printf("%s: %v", message, err)
	}
}

// ErrorWithFields logs error messages with fields
func ErrorWithFields(message string, fields map[string]interface{}) {
	if errorLogger != nil {
		errorLogger.Printf("%s - %v", message, fields)
	}
}

// Fatal logs fatal errors and exits
func Fatal(message string, err error) {
	if errorLogger != nil {
		errorLogger.Fatalf("%s: %v", message, err)
	} else {
		log.Fatalf("%s: %v", message, err)
	}
}

// Debug logs debug messages (only in dev mode)
func Debug(message string) {
	if infoLogger != nil {
		infoLogger.Printf("%s", fmt.Sprintf("DEBUG: %s", message))
	}
}