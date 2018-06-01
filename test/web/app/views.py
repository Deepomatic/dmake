import os
from django.shortcuts import render
from django.http import JsonResponse

import kombu
import struct
import time
import sys

connection = None
exchange = None
producer = None
response_queue = None

def kombu_connect():
    global connection, exchange, producer, response_queue
    if connection is None:
        url = os.getenv('AMQP_URL', None)
        while True:
            count = 0
            try:
                connection = kombu.Connection(url)
                exchange = kombu.Exchange('amq.direct', type = 'direct', channel = connection)
                producer = kombu.Producer(connection, exchange, 'worker')
                break
            except:
                if (count == 3):
                    print("Giving up");
                    sys.exit(1)
                print("Connection failed, AMQP might not be ready. Retrying...");
                time.sleep(10);
                ++count;

        # Cannot rely on generated queues of Kombu because
        # it either bind to default exchange with a routing key or
        # bind to a non default exchange without routing key.
        routing_key = r'api_response'
        response_queue = kombu.Queue(channel = connection,
                                     name = routing_key,
                                     routing_key = routing_key,
                                     exchange = exchange,
                                     passive = False,
                                     durable     = False,
                                     exclusive   = False,
                                     auto_delete = True)
        response_queue.declare()

def template(request):
    return render(request, 'app/index.html', {})

def call_worker(request):
    kombu_connect()

    properties = {}
    properties['reply_to'] = response_queue.name

    # Send message to worker
    producer.publish(struct.pack("I", int(request.GET['n'])), **properties)

    # Get worker response
    t = time.time()
    while(time.time() - t < 10):
        data = response_queue.get(no_ack = True)
        if data is None:
            time.sleep(0.01)
        else:
            break

    # Decode C integer into python
    if data is None:
        raise Exception('Timeout: the worker response took to much time')
    if len(data.body) != 8:
        raise Exception('Bad AMQP message')
    data = struct.unpack("Q", data.body)[0]

    return JsonResponse({"result": data})
