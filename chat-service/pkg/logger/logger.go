package logger

import (
	"fmt"
	"log"
	"os"
	"strings"
)

var (
	infoLogger  = log.New(os.Stdout, "[INFO]  ", log.Ldate|log.Ltime|log.LUTC)
	warnLogger  = log.New(os.Stdout, "[WARN]  ", log.Ldate|log.Ltime|log.LUTC)
	errorLogger = log.New(os.Stderr, "[ERROR] ", log.Ldate|log.Ltime|log.LUTC)
	debugLogger = log.New(os.Stdout, "[DEBUG] ", log.Ldate|log.Ltime|log.LUTC)

	level = "INFO"
)

func SetLevel(l string) {
	level = strings.ToUpper(l)
}

func Info(msg string)  { infoLogger.Println(msg) }
func Warn(msg string)  { warnLogger.Println(msg) }
func Error(msg string) { errorLogger.Println(msg) }
func Debug(msg string) {
	if level == "DEBUG" {
		debugLogger.Println(msg)
	}
}

func Infof(format string, args ...interface{})  { infoLogger.Println(fmt.Sprintf(format, args...)) }
func Warnf(format string, args ...interface{})  { warnLogger.Println(fmt.Sprintf(format, args...)) }
func Errorf(format string, args ...interface{}) { errorLogger.Println(fmt.Sprintf(format, args...)) }
func Debugf(format string, args ...interface{}) {
	if level == "DEBUG" {
		debugLogger.Println(fmt.Sprintf(format, args...))
	}
}
