"""采购计划单：用浏览器原字段名"""
import json, os, requests, copy
from urllib.parse import quote

API = 'https://yunfan-api.kemai.com.cn'
BASE = '/web/api/purchase/purchasePlanOrder'

def get_headers():
    d = json.load(open(os.environ.get('YF_TOKEN_FILE', os.path.expanduser('~/.yunfan_token.json'))))['data']
    return {
        'token': d['token'],
        'loginName': os.environ.get('YF_ACCOUNT', ''),
        'shopAdminId': os.environ.get('YF_SHOP', ''),
        'merchantName': quote(os.environ.get('YF_MERCHANT', '')),
        'Content-Type': 'application/json'
    }

def create_plan(barcode, qty_pieces):
    H = get_headers()
    
    r = requests.post(API+'/web/api/product/common/getItemByBarcodeOrCode',
                      json={'keyword': barcode}, headers=H, timeout=15).json()
    item = r['data'][0] if isinstance(r['data'], list) else r['data']
    
    r = requests.post(API+BASE+'/doNewEntity', json={}, headers=H, timeout=15).json()
    ent = copy.deepcopy(r['data']['entity'])
    
    q = int(qty_pieces)
    price = int(item['purchasePrice'])
    qty_v = q * 10000
    
    # 用浏览器 payload 里的原字段名
    detail = {
        "itemId": item['itemId'],
        "otherItemId": item['packItemId'],
        "itemCode": item['code'],
        "itemName": item['name'],
        "itemSubno": item['barcode'],
        "qty": str(qty_v),  # 字符串！
        "purchasePackageQty": qty_v,
        "purchaseUnitQty": 10000,
        "basicQty": qty_v,
        "unitQty": 10000,
        "purchasePrice": price,
        "basicPrice": price,
        "packUnitFactor": int(item['unitFactor']),
        "amt": q * price,
        "supplierId": item['supplierId'],
        "supplierName": item['supplierName'],
        "supplierCode": item['supplierCode'],
        "purchaseUnitName": "千克",
        "sequence": 1,
    }
    ent['details'] = [detail]
    ent['receiveBranchId'] = '45050580'
    ent['receiveBranchName'] = '002'
    ent['receiveBranchCode'] = '000002'
    ent['receiveBranchType'] = '2'
    
    r = requests.post(API+BASE+'/doSaveEntity', json=ent, headers=H, timeout=15).json()
    print(f'结果: {r.get("code")} {r.get("msg")}')
    if r.get('code') == 0:
        eid = r['data']['id']
        print(f'✅ 成功! 单号: {r["data"].get("sheetNo")}')
        # 删除
        requests.post(API+BASE+'/doDeleteEntity', json={'ids': eid}, headers=H, timeout=15)
        print('已删除')
        return True
    return False

if __name__ == '__main__':
    create_plan('6900000000014', 10)
