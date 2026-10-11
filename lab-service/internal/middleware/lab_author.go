package middleware

import (
	"database/sql"
	"github.com/gin-gonic/gin"
	"net/http"
	"strconv"
)

// Resource identifiers are resolved server-side, never from browser owner IDs.
func LabAuthor(db *sql.DB, resource string) gin.HandlerFunc {
	queries := map[string]string{
		"lab":     "SELECT created_by FROM labs WHERE id=$1",
		"case":    "SELECT l.created_by FROM labs l JOIN lab_test_cases t ON t.lab_id=l.id WHERE t.id=$1",
		"task":    "SELECT l.created_by FROM labs l JOIN lab_runtime_tasks t ON t.lab_id=l.id WHERE t.id=$1",
		"section": "SELECT l.created_by FROM labs l JOIN lab_sections s ON s.lab_id=l.id WHERE s.id=$1",
		"content": "SELECT l.created_by FROM labs l JOIN lab_sections s ON s.lab_id=l.id JOIN lab_section_content c ON c.section_id=s.id WHERE c.id=$1",
	}
	params := map[string]string{"lab": "labId", "case": "id", "task": "taskId", "section": "sectionId", "content": "contentId"}
	return func(c *gin.Context) {
		if c.GetString("user_role") == "ADMIN" {
			c.Next()
			return
		}
		id, err := strconv.ParseInt(c.Param(params[resource]), 10, 64)
		if err != nil || id <= 0 {
			c.AbortWithStatusJSON(400, gin.H{"error": "invalid resource"})
			return
		}
		var owner int64
		err = db.QueryRowContext(c.Request.Context(), queries[resource], id).Scan(&owner)
		if err == sql.ErrNoRows {
			c.AbortWithStatusJSON(404, gin.H{"error": "resource not found"})
			return
		}
		if err != nil {
			c.AbortWithStatusJSON(500, gin.H{"error": "cannot authorize resource"})
			return
		}
		if owner != c.GetInt64("user_id") {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "lab belongs to another author"})
			return
		}
		c.Next()
	}
}
