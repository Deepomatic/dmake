from django.test import TestCase
from django.test import Client
import json

class FactorialTest(TestCase):
    def test_get(self):
        c = Client()
        response = c.get('/api/factorial', {'n': 4})
        data = json.loads(response.content)
        self.assertEqual('result' in data, True)
        self.assertEqual(data['result'], 24)
