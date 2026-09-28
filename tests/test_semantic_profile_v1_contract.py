"""Semantic Profile V1 Contract Freeze Tests.

Validates that DatasetSemanticProfile serialized output conforms strictly
to schemas/semantic_profile_v1.schema.json, ensuring required fields,
types, and enum values are frozen while allowing optional extensions.
"""

import json
from pathlib import Path
import pytest
import jsonschema
from jsonschema import validate, ValidationError

from ingestion.loaders import CSVLoader
from intelligence.profiler import profile_dataset
from intelligence.semantic_analyzer import analyze_semantics

ROOT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT_DIR / "schemas" / "semantic_profile_v1.schema.json"
GOLDEN_PATH = ROOT_DIR / "tests" / "fixtures" / "semantic_profile_v1_golden.json"


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def golden_profile():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_semantic_profile_v1_golden_fixture_validates(schema, golden_profile):
    """Assert the committed golden fixture passes the frozen JSON Schema."""
    validate(instance=golden_profile, schema=schema)


def test_semantic_profile_v1_live_generation_validates(schema):
    """Assert a freshly generated DatasetSemanticProfile passes the frozen JSON Schema."""
    csv_path = ROOT_DIR / "tests" / "fixtures" / "baseline.csv"
    dataset = CSVLoader().load(str(csv_path))
    profile = profile_dataset(dataset)
    sem_profile = analyze_semantics(dataset, profile)
    serialized = sem_profile.to_dict()

    validate(instance=serialized, schema=schema)


def test_semantic_profile_v1_contract_required_root_fields(schema, golden_profile):
    """Assert omitting required top-level fields fails schema validation."""
    for field in ["dataset_id", "generated_at", "column_evidences"]:
        broken = dict(golden_profile)
        del broken[field]
        with pytest.raises(ValidationError):
            validate(instance=broken, schema=schema)


def test_semantic_profile_v1_contract_required_column_evidence_fields(schema, golden_profile):
    """Assert omitting required fields in ColumnSemanticEvidence fails schema validation."""
    required_evidence_fields = ["column_name", "candidate_role", "confidence", "confidence_level", "evidence"]
    for field in required_evidence_fields:
        broken = json.loads(json.dumps(golden_profile))
        del broken["column_evidences"]["amount"][field]
        with pytest.raises(ValidationError):
            validate(instance=broken, schema=schema)


def test_semantic_profile_v1_contract_frozen_enum_roles(schema, golden_profile):
    """Assert invalid candidate_role values are rejected."""
    broken = json.loads(json.dumps(golden_profile))
    broken["column_evidences"]["amount"]["candidate_role"] = "INVALID_ROLE"
    with pytest.raises(ValidationError):
        validate(instance=broken, schema=schema)


def test_semantic_profile_v1_contract_frozen_confidence_levels(schema, golden_profile):
    """Assert invalid confidence_level values are rejected."""
    broken = json.loads(json.dumps(golden_profile))
    broken["column_evidences"]["amount"]["confidence_level"] = "VERY_HIGH"
    with pytest.raises(ValidationError):
        validate(instance=broken, schema=schema)


def test_semantic_profile_v1_contract_confidence_bounds(schema, golden_profile):
    """Assert confidence scores outside [0.0, 1.0] are rejected."""
    broken_high = json.loads(json.dumps(golden_profile))
    broken_high["column_evidences"]["amount"]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        validate(instance=broken_high, schema=schema)

    broken_low = json.loads(json.dumps(golden_profile))
    broken_low["column_evidences"]["amount"]["confidence"] = -0.1
    with pytest.raises(ValidationError):
        validate(instance=broken_low, schema=schema)


def test_semantic_profile_v1_contract_extra_optional_fields_allowed(schema, golden_profile):
    """Assert additional optional fields are allowed at root and column levels."""
    extended = json.loads(json.dumps(golden_profile))
    extended["future_extension_field"] = {"model_version": "v1.2.0"}
    extended["column_evidences"]["amount"]["domain_tag"] = "financial_kpi"
    extended["column_evidences"]["amount"]["extra_metadata"] = [1, 2, 3]

    # Must validate cleanly without error
    validate(instance=extended, schema=schema)
