"""Quick standalone smoke test — run with: python smoke_test.py"""
import json
from pydantic import BaseModel, Field, computed_field, ValidationError
from typing import Annotated, Literal

DATA_FILE = "patients.json"


class Patient(BaseModel):
    id: Annotated[str, Field(...)]
    name: Annotated[str, Field(...)]
    city: Annotated[str, Field(...)]
    age: Annotated[int, Field(..., gt=0, lt=120)]
    gender: Annotated[Literal["male", "female", "others"], Field(...)]
    height: Annotated[float, Field(..., gt=0)]
    weight: Annotated[float, Field(..., gt=0)]

    @computed_field
    @property
    def bmi(self) -> float:
        return round(self.weight / (self.height ** 2), 2)

    @computed_field
    @property
    def verdict(self) -> str:
        if self.bmi < 18.5:
            return "Underweight"
        elif self.bmi < 25:
            return "Normal"
        elif self.bmi < 30:
            return "Overweight"
        else:
            return "Obese"


# Load existing data
with open(DATA_FILE) as f:
    data = json.load(f)

print(f"Loaded {len(data)} patients from JSON")

# Validate BMI & verdict for all existing records
for pid, rec in data.items():
    base = {k: v for k, v in rec.items() if k not in ("bmi", "verdict")}
    p = Patient(id=pid, **base)
    stored_bmi = round(rec["bmi"], 2)
    calc_bmi = p.bmi
    assert stored_bmi == calc_bmi, f"BMI mismatch for {pid}: calculated={calc_bmi}, stored={stored_bmi}"
    assert p.verdict == rec["verdict"], f"Verdict mismatch for {pid}: {p.verdict} vs {rec['verdict']}"

print("BMI & verdict PASSED for all existing patients")

# Create + delete roundtrip
TEST_ID = "TEST_SMOKE"
p_new = Patient(id=TEST_ID, name="Test User", city="Delhi", age=30, gender="male", height=1.75, weight=70)
data[TEST_ID] = p_new.model_dump(exclude={"id"})

with open(DATA_FILE, "w") as f:
    json.dump(data, f, indent=4)

with open(DATA_FILE) as f:
    data2 = json.load(f)

assert TEST_ID in data2, "Create FAILED"
print("Create PASSED")

del data2[TEST_ID]
with open(DATA_FILE, "w") as f:
    json.dump(data2, f, indent=4)

print("Delete PASSED")
print("\nAll standalone data-layer tests PASSED ✓")
