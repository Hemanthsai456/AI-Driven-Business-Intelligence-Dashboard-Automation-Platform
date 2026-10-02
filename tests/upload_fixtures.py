import os
import uuid
import json
import urllib.request

def upload_file(path):
    boundary = uuid.uuid4().hex
    filename = os.path.basename(path)
    with open(path, 'rb') as f:
        data = f.read()
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: text/csv\r\n\r\n'
    ).encode('utf-8') + data + f'\r\n--{boundary}--\r\n'.encode('utf-8')
    req = urllib.request.Request(
        'http://127.0.0.1:8001/api/datasets/upload',
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )
    res = urllib.request.urlopen(req)
    return json.loads(res.read())

if __name__ == '__main__':
    r1 = upload_file(r'tests\fixtures\baseline.csv')
    print('Baseline uploaded:', r1['dataset_id'], r1['filename'], r1['row_count'], r1['column_count'])
    r2 = upload_file(r'tests\fixtures\messy_dataset.csv')
    print('Messy uploaded:', r2['dataset_id'], r2['filename'], r2['row_count'], r2['column_count'])
