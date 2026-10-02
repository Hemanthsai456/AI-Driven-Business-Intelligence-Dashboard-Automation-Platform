import urllib.request
import json
import pandas as pd
import numpy as np

def upload(filename, csv_content):
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: text/csv\r\n\r\n'
        f'{csv_content}\r\n'
        f'--{boundary}--\r\n'
    ).encode('utf-8')
    req = urllib.request.Request(
        'http://127.0.0.1:8001/api/datasets/upload',
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )
    res = urllib.request.urlopen(req)
    return json.loads(res.read())

np.random.seed(42)
dates = pd.date_range('2024-01-01', periods=50, freq='D')
sales_df = pd.DataFrame({
    'TransactionID': range(1, 101),
    'Date': np.random.choice(dates, 100),
    'ProductCategory': np.random.choice(['Electronics', 'Apparel', 'HomeGoods', 'Books', 'Toys'], 100),
    'UnitsSold': np.random.randint(1, 15, 100),
    'Revenue': np.random.uniform(20.0, 500.0, 100).round(2),
    'DiscountPct': np.random.choice([0.0, 0.05, 0.1, 0.15, 0.2], 100)
})
sales_csv = sales_df.to_csv(index=False)
res1 = upload('Retail_Sales_2024.csv', sales_csv)
print('Uploaded Dataset 1:', res1['dataset_id'], res1['filename'])

prod_df = pd.DataFrame({
    'SKU': [f'SKU-{i:03d}' for i in range(1, 16)],
    'ProductName': [f'Product_{chr(65+i)}' for i in range(15)],
    'Department': ['Hardware', 'Software', 'Services', 'Support', 'Hardware', 'Software', 'Services', 'Support', 'Hardware', 'Software', 'Hardware', 'Hardware', 'Software', 'Support', 'Services'],
    'InventoryCount': [120, 45, 10, 80, 200, 310, 50, 65, 88, 14, 99, 140, 25, 70, 115],
    'CostPrice': [15.5, 99.0, 450.0, 25.0, 18.0, 120.0, 500.0, 30.0, 14.0, 85.0, 22.0, 19.5, 110.0, 28.0, 480.0]
})
prod_csv = prod_df.to_csv(index=False)
res2 = upload('Inventory_Catalog.csv', prod_csv)
print('Uploaded Dataset 2:', res2['dataset_id'], res2['filename'])
