package logger

import (
	"log"
	"os"
)

var (
	infoLogger  *log.Logger
	warnLogger  *log.Logger
	errorLogger *log.Logger
	fatalLogger *log.Logger
)

// Init initializes the logger based on environment.
func Init(env string) {
	flags := log.Ldate | log.Ltime | log.Lshortfile
	infoLogger = log.New(os.Stdout, "[INFO]  ", flags)
	warnLogger = log.New(os.Stdout, "[WARN]  ", flags)
	errorLogger = log.New(os.Stderr, "[ERROR] ", flags)
	fatalLogger = log.New(os.Stderr, "[FATAL] ", flags)
}

func Info(msg string)                   { infoLogger.Output(2, msg) }
func Warn(msg string)                   { warnLogger.Output(2, msg) }
func Error(msg string, err error)       { errorLogger.Output(2, msg+": "+err.Error()) }
func Fatal(msg string, err error)       { fatalLogger.Output(2, msg+": "+err.Error()); os.Exit(1) }
