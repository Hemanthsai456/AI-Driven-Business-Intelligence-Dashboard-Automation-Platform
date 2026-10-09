import requests
import json

def test_upload():
    url = "http://127.0.0.1:8000/api/datasets/upload"
    with open("tests/real_data/healthcare.csv", "rb") as f:
        files = {"file": ("healthcare.csv", f, "text/csv")}
        res = requests.post(url, files=files, timeout=10)
        print("UPLOAD STATUS CODE:", res.status_code)
        data = res.json()
        print("DATASET ID:", data.get("dataset_id"))
        print("NAME:", data.get("name"))
        print("ROW COUNT:", data.get("row_count"))
        dataset_id = data.get("dataset_id")

    # Test GET /api/datasets
    res = requests.get("http://127.0.0.1:8000/api/datasets", timeout=5)
    print("LIST STATUS CODE:", res.status_code)
    print("DATASETS COUNT:", len(res.json()))

    # Test GET /api/datasets/{dataset_id}/cleaning/plan
    plan_url = f"http://127.0.0.1:8000/api/datasets/{dataset_id}/cleaning/plan"
    res = requests.get(plan_url, timeout=10)
    print("PLAN STATUS CODE:", res.status_code)
    plan_data = res.json()
    print("TOTAL RECS:", plan_data.get("total_recommendations"))
    print("SAFE RECS:", plan_data.get("safe_count"))

if __name__ == "__main__":
    test_upload()
