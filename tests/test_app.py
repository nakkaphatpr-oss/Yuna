"""Synthetic-only API tests; TEST_DATABASE_URL opts into a disposable PostgreSQL DB."""
import os
import pathlib
import tempfile
import unittest
import unittest.mock
import datetime
import traceback

temporary = tempfile.TemporaryDirectory()
os.environ['YUNA_DB'] = str(pathlib.Path(temporary.name) / 'test.db')
os.environ.pop('DATABASE_URL', None)
if os.environ.get('TEST_DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ['TEST_DATABASE_URL']
os.environ['APP_ORIGIN'] = 'https://clinic.test'
os.environ['YUNA_SETUP_TOKEN'] = 'test-only-bootstrap-token-not-a-real-secret-12345'
os.environ['YUNA_CLOUD'] = '0'

import server
from app import app
from database import initialize

original_reply = server.Handler.reply
def diagnostic_reply(self, data, status=200, **kwargs):
    if status == 500:
        traceback.print_exc()
    return original_reply(self, data, status, **kwargs)
server.Handler.reply = diagnostic_reply

class ClinicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize()
        server.CLOUD = True
        cls.client = app.test_client()
        cls.csrf = ''

    def request(self, path, data=None, expected=200, client=None, csrf=None):
        client = client or self.client
        headers = {'Origin': 'https://clinic.test', 'X-CSRF-Token': self.csrf if csrf is None else csrf}
        result = client.get('/api/'+path, base_url='https://clinic.test', headers=headers) if data is None else client.post('/api/'+path, base_url='https://clinic.test', headers=headers, json=data)
        self.assertEqual(result.status_code, expected, (path, result.get_json()))
        return result

    def test_complete_cloud_flow(self):
        self.request('patients', expected=401)
        setup = {'name': 'Synthetic Owner', 'username': 'owner', 'password': 'synthetic-password-12345'}
        self.request('setup', setup, 403)
        result = self.request('setup', setup | {'setup_token': os.environ['YUNA_SETUP_TOKEN']})
        self.assertIn('Secure', result.headers['Set-Cookie'])
        self.assertIn('HttpOnly', result.headers['Set-Cookie'])
        self.csrf = self.request('me').get_json()['csrf']
        self.request('setup', setup, 403)
        self.request('patients', {'hn': 'SYN-1', 'name': 'Synthetic Patient'}, 403, csrf='')
        pid = self.request('patients', {'hn': 'SYN-1', 'name': 'Synthetic Patient', 'age': 30}).get_json()['id']
        self.request('clinical/review', {'patient_id': pid, 'allergies': 'ไม่มี', 'conditions': 'ไม่มี'})
        procedure = {'patient_id': pid, 'service': 'Synthetic procedure', 'doctor': 'Test Doctor', 'note': 'Test', 'doctor_fee': 100, 'staff': 'Test Staff', 'commission': 20, 'review_confirmed': True}
        self.request('procedures', procedure, 400)
        self.request('clinical/consent', {'patient_id': pid, 'purpose': 'การรักษา', 'decision': 'ยินยอม', 'signed_by': 'Synthetic Patient', 'version': 'test'})
        product = self.request('inventory/product', {'code': 'SYN-1', 'name': 'Synthetic Product', 'category': 'Test', 'unit': 'unit', 'min_stock': 5}).get_json()['id']
        expiry = (datetime.date.today()+datetime.timedelta(days=30)).isoformat()
        later = (datetime.date.today()+datetime.timedelta(days=60)).isoformat()
        self.request('inventory/receive', {'product_id': product, 'lot': 'late', 'expiry': later, 'qty': 5, 'cost': 10})
        self.request('inventory/receive', {'product_id': product, 'lot': 'early', 'expiry': expiry, 'qty': 2, 'cost': 10})
        self.request('procedures', procedure | {'items': [{'product_id': product, 'qty': 3}]})
        lots = {lot['lot']: lot['qty'] for lot in self.request('inventory').get_json()['lots']}
        self.assertEqual(lots, {'early': 0, 'late': 4})
        self.request('procedures', procedure | {'items': [{'product_id': product, 'qty': 100}]}, 400)
        self.assertEqual(len(self.request('procedures').get_json()), 1)
        appointment = {'patient_id': pid, 'service': 'Test', 'doctor': 'Test Doctor', 'room': 'Room 1', 'start': expiry+'T10:00', 'duration': 30}
        self.request('appointments', appointment)
        self.request('appointments', appointment, 400)
        package = self.request('packages', {'patient_id': pid, 'name': 'Test Course', 'total': 2, 'price': 100, 'expiry': later}).get_json()['id']
        self.request('packages/redeem', {'id': package, 'qty': 1, 'reason': 'Test'})
        self.request('packages/redeem', {'id': package, 'qty': 2, 'reason': 'Test'}, 400)
        self.request('packages/promotion', {'name': 'Test', 'discount': 10, 'start': expiry, 'end': later, 'terms': 'Test'})
        quote = self.request('finance', {'kind': 'quote', 'patient_id': pid, 'description': 'Test', 'amount': 100, 'date': expiry}).get_json()['id']
        self.request('finance/convert', {'id': quote})
        self.request('finance/convert', {'id': quote}, 400)
        self.assertEqual(self.request('fees').get_json()[0]['doctor_fee'], 100)
        for index, role in enumerate(['แพทย์', 'พยาบาล', 'Front', 'คลัง', 'บัญชี']):
            username = 'role'+str(index)
            self.request('users', {'name': role, 'username': username, 'role': role, 'password': 'synthetic-password-12345'})
            client = app.test_client()
            self.request('login', {'username': username, 'password': 'synthetic-password-12345'}, client=client)
            user = self.request('me', client=client).get_json()
            for route, roles in server.ACCESS.items():
                self.request(route, expected=200 if role in roles else 403, client=client)
            if role == 'Front':
                record = self.request('patients?id='+str(pid), client=client).get_json()
                self.assertNotIn('allergies', record)
                self.assertNotIn('photos', record)
                self.request('finance', {'kind': 'expense', 'customer': 'Test', 'description': 'Test', 'amount': 1, 'date': expiry}, 403, client=client, csrf=user['csrf'])
        self.assertTrue(self.request('audit').get_json())
        # A new transport/client sees the same durable records after signing in.
        second = app.test_client()
        self.request('login', {'username': 'owner', 'password': 'synthetic-password-12345'}, client=second)
        self.assertEqual(len(self.request('patients', client=second).get_json()), 1)
        self.request('logout', {})
        self.request('patients', expected=401)
        # Missing remote DB must fail closed, never create ephemeral SQLite in cloud.
        with unittest.mock.patch.dict(os.environ, {'YUNA_CLOUD': '1', 'DATABASE_URL': ''}):
            self.request('status', expected=503)

if __name__ == '__main__':
    import unittest.mock
    unittest.main()
