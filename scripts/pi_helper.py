"""入库单（生鲜验收）极简接口：条码 + 数量"""
import json, os, requests, copy
from urllib.parse import quote

API = 'https://yunfan-api.kemai.com.cn'
BASE = '/web/api/stock/purchaseIn'

def get_headers():
    d = json.load(open(os.environ.get('YF_TOKEN_FILE', os.path.expanduser('~/.yunfan_token.json'))))['data']
    return {
        'token': d['token'],
        'loginName': os.environ.get('YF_ACCOUNT', ''),
        'shopAdminId': os.environ.get('YF_SHOP', ''),
        'merchantName': quote(os.environ.get('YF_MERCHANT', '')),
        'Content-Type': 'application/json'
    }

def create_purchase_in(barcode, qty_pieces):
    """
    创建入库单（测试用，创建后请删除）
    :param barcode: 商品条码
    :param qty_pieces: 数量（件）
    :return: (success, sheet_no, entity_id)
    """
    H = get_headers()
    
    r = requests.post(API+'/web/api/product/common/getItemByBarcodeOrCode',
                      json={'keyword': barcode}, headers=H, timeout=15).json()
    if r.get('code') != 0:
        return False, f"查商品失败: {r.get('msg')}", None
    item = r['data'][0] if isinstance(r['data'], list) else r['data']
    
    r = requests.post(API+BASE+'/doNewEntity', json={}, headers=H, timeout=15).json()
    ent = copy.deepcopy(r['data']['entity'])
    
    # 表头供应商
    ent['supplierId'] = item['supplierId']
    ent['supplierName'] = item['supplierName']
    ent['supplierCode'] = item['supplierCode']
    
    q = int(qty_pieces)
    price = int(item['purchasePrice'])
    qty_v = q * 10000
    amt_v = q * price
    
    # 注意：很多字段是字符串类型！
    detail = {
        "itemId": item['itemId'],
        "otherItemId": item['packItemId'],
        "itemCode": item['code'],
        "itemName": item['name'],
        "itemSubno": item['barcode'],
        "qty": str(qty_v),
        "purchaseQty": str(qty_v),
        "basicQty": str(qty_v),
        "purchaseUnitQty": "10000",
        "unitQty": "10000",
        "price": str(price),
        "purchasePrice": str(price),
        "basicPrice": str(price),
        "amt": str(amt_v),
        "unitName": "千克",
        "stockUnitName": "千克",
        "purchaseUnitName": "千克",
        "sequence": 1,
    }
    ent['details'] = [detail]
    
    r = requests.post(API+BASE+'/doSaveEntity', json=ent, headers=H, timeout=15).json()
    if r.get('code') == 0:
        return True, r['data'].get('sheetNo'), r['data'].get('id')
    else:
        return False, r.get('msg'), None

def delete_pi(entity_id):
    H = get_headers()
    r = requests.post(API+BASE+'/doDeleteEntity', json={'ids': entity_id}, headers=H, timeout=15).json()
    return r.get('code') == 0

if __name__ == '__main__':
    ok, sheet, eid = create_purchase_in('6900000000014', 10)
    print(f'创建: {ok}, 单号: {sheet}')
    if ok and eid:
        if delete_pi(eid):
            print('✅ 已删除测试单')
