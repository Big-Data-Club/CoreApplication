package service

import (
	"testing"

	"lab-service/internal/dto"
)

func TestValidatePublishDefinitionAcceptsCompleteSTEMWorkflow(t *testing.T) {
	definition := validPlantDefinition()

	issues := validatePublishDefinition(definition)
	if hasErrors(issues) {
		t.Fatalf("expected valid definition, got issues: %#v", issues)
	}
}

func TestValidatePublishDefinitionRequiresCoreSTEMSteps(t *testing.T) {
	definition := validPlantDefinition()
	definition.Nodes = definition.Nodes[:2]
	definition.Edges = definition.Edges[:1]

	issues := validatePublishDefinition(definition)
	if !hasIssue(issues, "STEM_STEP_MISSING") {
		t.Fatalf("expected STEM_STEP_MISSING, got: %#v", issues)
	}
}

func TestValidatePublishDefinitionRejectsUnreachableNodes(t *testing.T) {
	definition := validPlantDefinition()
	definition.Edges = definition.Edges[:len(definition.Edges)-1]

	issues := validatePublishDefinition(definition)
	if !hasIssue(issues, "UNREACHABLE_NODE") {
		t.Fatalf("expected UNREACHABLE_NODE, got: %#v", issues)
	}
}

func TestValidateStorageDefinitionRejectsExecutableConditionsInMVP(t *testing.T) {
	definition := validPlantDefinition()
	definition.Edges[0].ConditionExpression = "soil_moisture < 20"

	issues := validateStorageDefinition(definition)
	if !hasIssue(issues, "UNSUPPORTED_CONDITION") {
		t.Fatalf("expected UNSUPPORTED_CONDITION, got: %#v", issues)
	}
}

func TestDefinitionHashIsStableAcrossMapInsertionOrder(t *testing.T) {
	first := validPlantDefinition()
	first.Config = map[string]interface{}{"species": "brassica", "days": float64(21)}
	second := validPlantDefinition()
	second.Config = map[string]interface{}{}
	second.Config["days"] = float64(21)
	second.Config["species"] = "brassica"

	firstHash, err := definitionHash(first)
	if err != nil {
		t.Fatal(err)
	}
	secondHash, err := definitionHash(second)
	if err != nil {
		t.Fatal(err)
	}
	if firstHash != secondHash {
		t.Fatalf("expected stable hashes, got %s and %s", firstHash, secondHash)
	}
}

func TestExperimentSeedPreservesRequestedSeed(t *testing.T) {
	requested := int64(42)
	seed, err := experimentSeed(&requested)
	if err != nil {
		t.Fatal(err)
	}
	if seed != requested {
		t.Fatalf("expected seed %d, got %d", requested, seed)
	}
}

func hasIssue(issues []dto.ValidationIssue, code string) bool {
	for _, issue := range issues {
		if issue.Code == code {
			return true
		}
	}
	return false
}

func validPlantDefinition() dto.ExperimentDefinitionRequest {
	return dto.ExperimentDefinitionRequest{
		Domain:                "PLANT",
		InquiryLevel:          "GUIDED",
		WorkflowSchemaVersion: 1,
		ModelVersion:          "plant-lite-1.0.0",
		LearningObjectives:    []string{"Explain how irrigation affects plant growth"},
		Config:                map[string]interface{}{},
		Nodes: []dto.WorkflowNodeRequest{
			{Key: "predict", Type: "PREDICTION", Title: "Predict", RequiredEvidence: []string{"prediction"}, OrderHint: 0},
			{Key: "run", Type: "RUN", Title: "Run", OrderHint: 1},
			{Key: "analyze", Type: "ANALYZE", Title: "Analyze", RequiredEvidence: []string{"chart"}, OrderHint: 2},
			{Key: "explain", Type: "EXPLAIN", Title: "Explain", RequiredEvidence: []string{"cer"}, OrderHint: 3},
			{Key: "iterate", Type: "ITERATE", Title: "Improve", RequiredEvidence: []string{"change_reason"}, OrderHint: 4},
			{Key: "reflect", Type: "REFLECT", Title: "Reflect", RequiredEvidence: []string{"reflection"}, OrderHint: 5},
		},
		Edges: []dto.WorkflowEdgeRequest{
			{From: "predict", To: "run", ConditionExpression: "always"},
			{From: "run", To: "analyze", ConditionExpression: "always"},
			{From: "analyze", To: "explain", ConditionExpression: "always"},
			{From: "explain", To: "iterate", ConditionExpression: "always"},
			{From: "iterate", To: "reflect", ConditionExpression: "always"},
		},
		Variables: []dto.ExperimentVariableRequest{
			{Key: "irrigation", DisplayName: "Irrigation", Role: "INDEPENDENT", DataType: "NUMBER", Unit: "mL/day", SourceID: "fao56"},
			{Key: "biomass", DisplayName: "Biomass", Role: "DEPENDENT", DataType: "NUMBER", Unit: "g", SourceID: "plant-card"},
			{Key: "temperature", DisplayName: "Temperature", Role: "CONTROLLED", DataType: "NUMBER", Unit: "Cel", SourceID: "plant-card"},
		},
	}
}
