#include <glog/logging.h>

#include "app.hpp"
#include "amqp_client.hpp"

/*---------------------------------------------------------------------------*/

// Tail recursive version
uint64_t factorial(int n, uint64_t acc = 1)
{
    if (n <= 1) {
        return acc;
    }
    else {
        return factorial(n - 1, acc * n);
    }
}

/*---------------------------------------------------------------------------*/

void run(bool *stop)
{
    AMQPWrapper amqp_client;
    amqp_client.declareQueue(WORKER_QUEUE);

    int n;
    std::string reply_queue;
    while(!*stop)
    {
        LOG(INFO) << "Waiting for a message on queue '" << WORKER_QUEUE << "'";
        if (amqp_client.recv(WORKER_QUEUE, n, reply_queue))
        {
            amqp_client.send(reply_queue, factorial(n));
        }
        else {
            LOG(ERROR) << "Bad message";
        }
    }
}

/*---------------------------------------------------------------------------*/
