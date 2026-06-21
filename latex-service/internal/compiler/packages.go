package compiler

import (
	"strings"

	"latex-service/internal/dto"
)

type PackageRegistry struct {
	packages []dto.TexPackage
}

func NewPackageRegistry() *PackageRegistry {
	// Standard list of pre-installed packages in TeX Live Full
	pkgs := []string{
		"amsmath", "amsfonts", "amssymb", "amsthm", "geometry", "graphicx",
		"hyperref", "tikz", "pgfplots", "booktabs", "array", "listings",
		"xcolor", "fancyhdr", "caption", "subcaption", "float", "biblatex",
		"natbib", "microtype", "enumitem", "titlesec", "setspace", "multicol",
		"algorithm", "algorithmic", "siunitx", "todonotes", "url", "inputenc",
		"fontenc", "babel", "csquotes", "pdfpages", "geometry", "tcolorbox",
	}

	var registry []dto.TexPackage
	for _, name := range pkgs {
		registry = append(registry, dto.TexPackage{
			Name:        name,
			Description: "Standard LaTeX package included in TeX Live Full",
			Category:    "Utility",
			Installed:   true,
		})
	}

	return &PackageRegistry{packages: registry}
}

// Search returns packages matching the query
func (r *PackageRegistry) Search(query string) []dto.TexPackage {
	if query == "" {
		return r.packages
	}

	query = strings.ToLower(query)
	var matches []dto.TexPackage
	for _, pkg := range r.packages {
		if strings.Contains(strings.ToLower(pkg.Name), query) {
			matches = append(matches, pkg)
		}
	}
	return matches
}

// List returns all packages
func (r *PackageRegistry) List() []dto.TexPackage {
	return r.packages
}
