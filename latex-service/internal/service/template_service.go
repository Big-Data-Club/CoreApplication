package service

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"latex-service/internal/compiler"
	"latex-service/internal/dto"
	"latex-service/internal/repository"
)

type TemplateService struct {
	projectRepo *repository.ProjectRepository
	fileService *FileService
	registry    *compiler.PackageRegistry
	templates   map[string]dto.LatexTemplate
	templateDir string
}

func NewTemplateService(projectRepo *repository.ProjectRepository, fileService *FileService, templateDir string) *TemplateService {
	// Initialize registry
	registry := compiler.NewPackageRegistry()

	// Hardcoded metadata for templates
	templates := map[string]dto.LatexTemplate{
		"article": {
			ID:          "article",
			Name:        "Standard Article",
			Description: "A standard single-file LaTeX article template.",
			Category:    "Academic",
			Files:       []string{"main.tex"},
		},
		"report": {
			ID:          "report",
			Name:        "Multi-chapter Report",
			Description: "A report template structured with chapters.",
			Category:    "Academic",
			Files:       []string{"main.tex", "chapters/intro.tex"},
		},
		"beamer": {
			ID:          "beamer",
			Name:        "Presentation Slides (Beamer)",
			Description: "Create beautiful PDF slides for presentations.",
			Category:    "Presentation",
			Files:       []string{"main.tex"},
		},
		"ieeetran": {
			ID:          "ieeetran",
			Name:        "IEEE Conference Paper",
			Description: "Format for IEEE conference submissions.",
			Category:    "Academic",
			Files:       []string{"main.tex", "refs.bib"},
		},
		"bdc-thesis": {
			ID:          "bdc-thesis",
			Name:        "BDC Graduation Thesis",
			Description: "Official BDC thesis template with bdc-thesis.cls class file.",
			Category:    "Thesis",
			Files:       []string{"main.tex", "bdc-thesis.cls", "chapters/chap1.tex", "refs.bib"},
		},
	}

	return &TemplateService{
		projectRepo: projectRepo,
		fileService: fileService,
		registry:    registry,
		templates:   templates,
		templateDir: templateDir,
	}
}

// GetTemplates returns all templates
func (s *TemplateService) GetTemplates() []dto.LatexTemplate {
	var list []dto.LatexTemplate
	for _, t := range s.templates {
		list = append(list, t)
	}
	return list
}

// GetTemplate retrieves a single template
func (s *TemplateService) GetTemplate(id string) (*dto.LatexTemplate, error) {
	t, ok := s.templates[id]
	if !ok {
		return nil, errors.New("template not found")
	}
	return &t, nil
}

// CreateProjectFromTemplate initializes a project with all template files
func (s *TemplateService) CreateProjectFromTemplate(ctx context.Context, userID int64, templateID string, title string) (*dto.ProjectResponse, error) {
	_, ok := s.templates[templateID]
	if !ok {
		return nil, errors.New("template not found")
	}

	// 1. Create the project
	req := dto.CreateProjectRequest{
		Title:      title,
		Compiler:   "pdflatex", // default
		TemplateID: templateID,
	}

	// Adjust default compiler for specific templates if needed
	if templateID == "bdc-thesis" {
		req.Compiler = "xelatex" // BDC Thesis requires xelatex for fonts
	}

	p, err := s.projectRepo.Create(ctx, &req, userID)
	if err != nil {
		return nil, err
	}

	// 2. Walk template directory and upload files
	templateRoot := filepath.Join(s.templateDir, templateID)

	// Check if directory exists
	if _, err := os.Stat(templateRoot); os.IsNotExist(err) {
		return p, nil // Return project anyway, though files are missing
	}

	err = filepath.Walk(templateRoot, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}

		// Skip directories
		if info.IsDir() {
			return nil
		}

		relPath, err := filepath.Rel(templateRoot, path)
		if err != nil {
			return err
		}

		// Open template file
		file, err := os.Open(path)
		if err != nil {
			return err
		}
		defer file.Close()

		// standardizing backslashes to forward slashes
		filename := strings.ReplaceAll(relPath, "\\", "/")

		// Upload file to project
		_, err = s.fileService.UploadFile(ctx, userID, p.ID, filename, file, info.Size(), "text/plain")
		return err
	})

	if err != nil {
		return nil, fmt.Errorf("failed to copy template files: %w", err)
	}

	return p, nil
}

// SearchPackages searches the package registry
func (s *TemplateService) SearchPackages(query string) []dto.TexPackage {
	return s.registry.Search(query)
}
