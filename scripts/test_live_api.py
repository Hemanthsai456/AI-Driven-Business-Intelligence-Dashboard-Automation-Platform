"""Test live API server endpoint."""

import urllib.request
import json
from pathlib import Path

def main():
    # 1. Check health
    health = json.loads(urllib.request.urlopen('http://localhost:8000/api/health').read().decode('utf-8'))
    print("Health:", health)

    # 2. Upload healthcare.csv
    file_path = Path("tests/real_data/healthcare.csv")
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="healthcare.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        "http://localhost:8000/api/datasets/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    upload_res = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
    ds_id = upload_res["dataset_id"]
    print("Uploaded dataset_id:", ds_id)

    # 3. Request cleaning-plan from running server
    plan_res = json.loads(urllib.request.urlopen(f"http://localhost:8000/api/datasets/{ds_id}/cleaning-plan").read().decode("utf-8"))
    print("\n[+] LIVE API /api/datasets/{id}/cleaning-plan RESULT:")
    print("    Total recommendations:", plan_res.get("total_recommendations"))
    print("    Safe count:", plan_res.get("safe_count"))
    print("    Review required count:", plan_res.get("review_required_count"))
    print("    First recommendation:", plan_res["recommendations"][0]["operation"], "-", plan_res["recommendations"][0]["rationale"])

if __name__ == "__main__":
    main()
