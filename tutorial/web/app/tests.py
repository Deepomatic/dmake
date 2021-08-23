import json
import math

from django.test import Client
from django.test import TestCase


class FactorialTest(TestCase):
    def test_slash(self):
        c = Client()
        response = c.get('/')
        self.assertTrue(len(response.content) > 0)

    def test_get(self):
        c = Client()
        response = c.get('/api/factorial', {'n': 4})
        data = json.loads(response.content)
        self.assertEqual('result' in data, True)
        self.assertEqual(data['result'], 24)

    def test_multiple_get(self):
        c = Client()
        for n in range(12):
            response = c.get('/api/factorial', {'n': n})
            data = json.loads(response.content)
            self.assertEqual('result' in data, True)
            self.assertEqual(data['result'], math.factorial(n))
