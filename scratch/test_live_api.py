import json
import urllib.request

def test_live():
    # 1. Upload
    with open('tests/real_data/healthcare.csv', 'rb') as f:
        data = f.read()
    boundary = '---boundary123'
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="healthcare.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode('utf-8')
        + data
        + f'\r\n--{boundary}--\r\n'.encode('utf-8')
    )
    req = urllib.request.Request(
        'http://localhost:8000/api/datasets/upload',
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
    )
    res = urllib.request.urlopen(req)
    meta = json.loads(res.read().decode('utf-8'))
    ds_id = meta['dataset_id']
    print('Uploaded dataset ID:', ds_id)

    # 2. Get plan
    plan_res = json.loads(urllib.request.urlopen(f'http://localhost:8000/api/datasets/{ds_id}/cleaning-plan').read().decode('utf-8'))
    safe_ids = [r['recommendation_id'] for r in plan_res['recommendations'] if r['default_selected']]
    print('Plan recommendations:', len(plan_res['recommendations']), 'Safe selected:', len(safe_ids))

    # 3. Preview
    prev_req = urllib.request.Request(
        f'http://localhost:8000/api/datasets/{ds_id}/cleaning/preview',
        data=json.dumps({'selected_recommendation_ids': safe_ids}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    prev_res = json.loads(urllib.request.urlopen(prev_req).read().decode('utf-8'))
    print('Preview result:', prev_res['original_row_count'], '->', prev_res['preview_row_count'], 'Ops:', len(prev_res['operations']))

    # 4. Apply
    apply_req = urllib.request.Request(
        f'http://localhost:8000/api/datasets/{ds_id}/cleaning/apply',
        data=json.dumps({'selected_recommendation_ids': safe_ids}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    apply_res = json.loads(urllib.request.urlopen(apply_req).read().decode('utf-8'))
    print('Apply result:', apply_res['cleaned_row_count'], 'Applied:', apply_res['operations_applied'], 'Validation:', apply_res['validation']['overall_status'])

if __name__ == '__main__':
    test_live()
